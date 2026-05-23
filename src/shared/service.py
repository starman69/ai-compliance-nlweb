"""The NLWeb core: one retrieve+answer pipeline, shared by /ask and /mcp.

Flow (PLAN.md §4–§5): decontextualize -> classify intent -> resolve scope ->
retrieve (hybrid) -> rerank -> mode(list/summarize/generate) -> ItemList shape
-> token ledger -> audit. `mode` gates LLM use: `list` does NO model call.

Logic must not fork between /ask and /mcp — both call `ask()`.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

LOG = logging.getLogger(__name__)

# A follow-up is anaphoric if it's short or opens with a connective/pronoun —
# then we prepend the previous user turn so retrieval keeps the topic.
_FOLLOWUP_RE = re.compile(
    r"^\s*(and\b|but\b|what about|how about|compare\b|versus\b|vs\.?\b|also\b|then\b|"
    r"(does|do|is|are|can|should|would)\s+(it|that|they|those|this)\b|"
    r"(it|that|they|those|this|these)\b)",
    re.I,
)

from . import audit, clients, corpus, prompts, token_ledger
from . import router as _router
from .models import AskRequest, AskResponse, RetrievalDebug, Scope, Source

# Cap at 32: the TEI reranker's max client batch is 32, so a larger pool would
# error and silently fall back to dense. 32 candidates -> rerank -> top-k is plenty.
_CANDIDATES = int(os.environ.get("RETRIEVE_CANDIDATES", "32"))
_RERANK_TOP = int(os.environ.get("RERANK_TOP", "8"))

_OUT_OF_SCOPE_MSG = (
    "That question is outside the scope of this AI-compliance corpus. Ask about "
    "AI regulations, standards, or governance — for example the EU AI Act, "
    "ISO/IEC 42001, the NIST AI RMF, GDPR, or US state AI laws."
)
_NO_EVIDENCE_MSG = (
    "I couldn't find supporting evidence in the corpus for that question. "
    "Try naming a specific framework or jurisdiction."
)
_MODEL_DOWN_MSG = (
    "The answer model is temporarily unavailable — showing the most relevant "
    "sources below. Please try again shortly."
)


def _decontextualize(req: AskRequest) -> str:
    """Condense an anaphoric follow-up into a standalone retrieval query by
    prepending the previous user turn. Short OR connective/pronoun-led follow-ups
    qualify (e.g. 'and what about California?', 'how does that compare?')."""
    if req.decontextualized_query:
        return req.decontextualized_query
    if not req.prev:
        return req.query
    last_user = next((t.content for t in reversed(req.prev) if t.role == "user"), "")
    if last_user and (len(req.query.split()) <= 7 or _FOLLOWUP_RE.search(req.query)):
        return f"{last_user} — {req.query}".strip()
    return req.query


def _inherited_scope(req: AskRequest) -> tuple[list[str], list[str]]:
    """Scope/framework carried from the most recent prior user turn that named one
    — so a follow-up that mentions no framework stays on the same topic."""
    for t in reversed(req.prev):
        if t.role == "user":
            juris, docs = _router.detect_scope(t.content)
            if juris or docs:
                return juris, docs
    return [], []


def _confidence(hits: list[dict], used_llm: bool) -> str:
    """Confidence from the top retrieval score. Scale-aware: real vector search
    returns cosine similarity (0–1); the Mock returns token-overlap counts (>1)."""
    if not hits:
        return "low"
    top = max(float(h.get("score", 0)) for h in hits)
    if top <= 1.0:  # cosine similarity (Qdrant / Azure AI Search)
        if top >= 0.68 and len(hits) >= 2:
            return "high"
        return "medium" if top >= 0.45 else "low"
    # token-overlap (Mock)
    if top >= 8 and len(hits) >= 2:
        return "high"
    return "medium" if top >= 4 else "low"


@dataclass
class _Prep:
    """Everything the retrieve+rank pipeline produces, up to (but not including)
    the LLM call. Shared by the non-streaming `ask` and the streaming
    `ask_stream` so the two never fork. `early` is set for the out-of-scope
    short-circuit (no retrieval/LLM)."""

    qid: str
    t0: float
    ledger: token_ledger.TokenLedger
    standalone: str
    interpreted: str | None
    intent: str
    scope_tokens: list[str]
    candidates: list = field(default_factory=list)
    reranked: list = field(default_factory=list)
    fusion: str = "none"
    sources: list[Source] = field(default_factory=list)
    early: AskResponse | None = None


def _shape_sources(reranked: list[dict]) -> list[Source]:
    return [
        Source(
            position=i + 1, doc_id=h.get("doc_id", ""), title=h.get("title", ""),
            short_name=h.get("short_name", ""), section_path=h.get("section_path"),
            page=h.get("page"), url=h.get("url"), quote=(h.get("text") or "").strip(),
            score=float(h.get("score", 0.0)),
        )
        for i, h in enumerate(reranked)
    ]


def _prepare(req: AskRequest) -> _Prep:
    """Decontextualize → classify → scope → retrieve (hybrid) → rerank. The
    ledger is threaded explicitly (not via the contextvar) so the streaming
    generator stays correct even if Starlette iterates it across threads."""
    t0 = time.perf_counter()
    ledger = token_ledger.start_ledger()
    qid = f"q_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"

    standalone = _decontextualize(req)
    interpreted = standalone if standalone != req.query else None
    plan = _router.classify(standalone)
    scope_tokens = corpus.resolve_scope(req.scope_tokens()) or plan.jurisdictions
    doc_hints = list(plan.doc_hints)
    # Multi-turn: if this turn names no framework/jurisdiction, inherit the prior topic.
    if req.prev and not scope_tokens and not doc_hints:
        scope_tokens, doc_hints = _inherited_scope(req)

    if plan.intent == "out_of_scope":
        elapsed = int((time.perf_counter() - t0) * 1000)
        early = AskResponse(
            query_id=qid, answer=_OUT_OF_SCOPE_MSG, mode=req.mode, confidence="low",
            intent="out_of_scope", decontextualized_query=interpreted, sources=[],
            scope=Scope(jurisdictions=scope_tokens),
            token_usage=ledger.to_summary(), model="none", elapsed_ms=elapsed,
            retrieval=RetrievalDebug(candidates=0, reranked=0, fusion="none"),
        )
        return _Prep(qid, t0, ledger, standalone, interpreted, "out_of_scope",
                     scope_tokens, early=early)

    # --- retrieve (embed the query so the token bar shows embedding activity) ---
    vector = None
    try:
        emb = clients.get_embed_client()
        vecs, usage = emb.embed([standalone], model=clients.embed_model())
        ledger.record_manual(
            kind="embedding", model=clients.embed_model(),
            embedding_tokens=int(getattr(usage, "total_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0),
        )
        vector = vecs[0] if vecs and vecs[0] else None
    except Exception:  # embedding failure must not break the answer path
        vector = None

    store = clients.get_vector_client("chunks")
    candidates = store.search(
        query_text=standalone, vector=vector, top=_CANDIDATES,
        jurisdictions=scope_tokens or None, doc_hints=doc_hints or None,
    )

    # Cross-encoder rerank the candidates -> top-k (keeps each chunk's dense
    # cosine score for the confidence signal; the reranker only reorders).
    # Never break the answer path if the reranker is unreachable.
    reranked = candidates[:_RERANK_TOP]
    fusion = "rrf" if clients.backend() != "mock" else "mock"
    reranker = clients.get_reranker()
    if candidates and reranker is not None:
        try:
            order = reranker.rerank(standalone, [c.get("text", "") for c in candidates])
            # Set the chunk score to the cross-encoder relevance (0–1) — meaningful
            # for the confidence signal (RRF fusion scores are tiny by comparison).
            reranked = [
                {**candidates[i], "score": float(s)}
                for i, s in order[:_RERANK_TOP]
                if i < len(candidates)
            ]
            ledger.record_manual(kind="rerank", model=clients.reranker_model())
            fusion = "rrf+rerank"
        except Exception:
            reranked = candidates[:_RERANK_TOP]

    return _Prep(
        qid, t0, ledger, standalone, interpreted, plan.intent, scope_tokens,
        candidates=candidates, reranked=reranked, fusion=fusion,
        sources=_shape_sources(reranked),
    )


def _build_response(req: AskRequest, prep: _Prep, *, answer: str, model_used: str) -> AskResponse:
    elapsed = int((time.perf_counter() - prep.t0) * 1000)
    return AskResponse(
        query_id=prep.qid, answer=answer, mode=req.mode,
        confidence=_confidence(prep.reranked, model_used != "none"), intent=prep.intent,
        decontextualized_query=prep.interpreted,
        sources=prep.sources, scope=Scope(jurisdictions=prep.scope_tokens),
        token_usage=prep.ledger.to_summary(), model=model_used, elapsed_ms=elapsed,
        retrieval=RetrievalDebug(
            candidates=len(prep.candidates), reranked=len(prep.reranked), fusion=prep.fusion,
        ),
    )


def ask(req: AskRequest, *, principal_name: str = "dev") -> AskResponse:
    prep = _prepare(req)
    if prep.early is not None:
        _audit(prep.early, principal_name, prep.standalone)
        return prep.early

    # --- mode gates LLM use (list = retrieval only, no model call) ---
    answer, model_used = "", "none"
    if req.mode != "list" and prep.reranked:
        try:
            chat = clients.get_chat_client()
            messages = prompts.build_messages(
                query=prep.standalone, evidence=prep.reranked, intent=prep.intent, mode=req.mode
            )
            result = chat.complete(messages, model=clients.answer_model())
            prep.ledger.record_chat(result, model=clients.answer_model())
            answer, model_used = result.text, clients.answer_model()
        except Exception:
            LOG.exception("answer model failed; returning retrieval only")
            answer = _MODEL_DOWN_MSG
    elif req.mode != "list" and not prep.reranked:
        answer = _NO_EVIDENCE_MSG

    resp = _build_response(req, prep, answer=answer, model_used=model_used)
    _audit(resp, principal_name, prep.standalone)
    return resp


def _sse(event: str, data) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def ask_stream(req: AskRequest, *, principal_name: str = "dev") -> Iterator[str]:
    """SSE generator for POST /ask/stream. Same core as `ask`, emitted as a
    typed event sequence: `sources` (citations up front) → `delta` (answer
    tokens) → `done` (the full AskResponse, incl. item_list + token_usage).
    The `done` payload is identical to what `ask` would return."""
    prep = _prepare(req)
    if prep.early is not None:
        yield _sse("sources", [])
        _audit(prep.early, principal_name, prep.standalone)
        yield _sse("done", prep.early.model_dump())
        return

    yield _sse("sources", [s.model_dump() for s in prep.sources])

    answer, model_used = "", "none"
    if req.mode != "list" and prep.reranked:
        try:
            chat = clients.get_chat_client()
            messages = prompts.build_messages(
                query=prep.standalone, evidence=prep.reranked, intent=prep.intent, mode=req.mode
            )
            stream = chat.stream(messages, model=clients.answer_model())
            for delta in stream:
                answer += delta
                yield _sse("delta", {"text": delta})
            prep.ledger.record_chat(stream, model=clients.answer_model())  # ChatStream exposes .usage
            model_used = clients.answer_model()
        except Exception:
            LOG.exception("answer model failed mid-stream; degrading to sources")
            if not answer:  # keep any partial output; otherwise show the fallback
                answer = _MODEL_DOWN_MSG
                yield _sse("delta", {"text": answer})
    elif req.mode != "list" and not prep.reranked:
        answer = _NO_EVIDENCE_MSG
        yield _sse("delta", {"text": answer})

    resp = _build_response(req, prep, answer=answer, model_used=model_used)
    _audit(resp, principal_name, prep.standalone)
    yield _sse("done", resp.model_dump())


def _audit(resp: AskResponse, principal_name: str, standalone_query: str) -> None:
    audit.write(
        {
            "query_id": resp.query_id,
            "principal": principal_name,
            "intent": resp.intent,
            "mode": resp.mode,
            "scope": resp.scope.jurisdictions,
            "n_sources": len(resp.sources),
            "source_ids": [s.doc_id for s in resp.sources],
            "confidence": resp.confidence,
            "model": resp.model,
            "token_usage": resp.token_usage,
            "elapsed_ms": resp.elapsed_ms,
            "decontextualized_query": standalone_query,
        }
    )
