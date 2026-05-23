"""Lazy client factories. All profile/backend branching lives here, never in
business logic (PLAN.md §14).

Backends:
- `mock` (default) — fully offline: MockVectorClient + MockChatClient +
  MockEmbedClient. The API and UI run with no Qdrant/Ollama/Azure.
- `real` — uses the active RUNTIME_PROFILE: `local` (Ollama /v1 + Qdrant) or
  `azure` (Azure OpenAI + Azure AI Search).

Set NLWEB_BACKEND=real to exercise the live stack.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from . import profile as _profile
from . import vector_search as _vs


def backend() -> str:
    # Default to real live models; the test suite pins `mock` in tests/conftest.py.
    return (os.environ.get("NLWEB_BACKEND") or "real").lower()


def answer_model() -> str:
    if backend() == "mock":
        return "mock-llm"
    if _profile.is_azure():
        return os.environ.get("OPENAI_DEPLOYMENT_REASONING", "gpt-4.1")
    return os.environ.get("OLLAMA_MODEL_REASONING", "qwen3:14b")


def embed_model() -> str:
    if backend() == "mock":
        return "mock-embed"
    if _profile.is_azure():
        return os.environ.get("OPENAI_DEPLOYMENT_EMBEDDING", "text-embedding-3-small")
    return os.environ.get("OLLAMA_MODEL_EMBEDDING", "mxbai-embed-large")


# --- usage shim so MockClient responses look like OpenAI SDK responses ------
@dataclass
class _Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ChatResult:
    text: str
    usage: _Usage


class ChatStream:
    """Iterable of answer text deltas. After iteration, `.text` is the full
    answer and `.usage` carries token counts (zeros if the backend omitted
    stream usage). Shaped so it can be passed straight to
    `TokenLedger.record_chat` (it exposes `.usage`)."""

    def __init__(self) -> None:
        self.text = ""
        self.usage: Any = _Usage()
        self._iter: Any = iter(())

    def __iter__(self):
        for delta in self._iter:
            if delta:
                self.text += delta
                yield delta


# --------------------------------------------------------------------------
# Vector store
# --------------------------------------------------------------------------
def get_vector_client(which: str = "chunks") -> _vs.VectorSearchClient:
    if backend() == "mock":
        return _vs.MockVectorClient()
    if _profile.is_azure():
        from azure.identity import DefaultAzureCredential

        endpoint = os.environ["SEARCH_SERVICE_ENDPOINT"]
        index = os.environ.get(
            "SEARCH_INDEX_CHUNKS" if which == "chunks" else "SEARCH_INDEX_DOCS",
            f"compliance-{which}-index",
        )
        return _vs.AzureSearchVectorClient(endpoint, index, DefaultAzureCredential())
    url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    return _vs.QdrantVectorClient(url, f"compliance_{which}")


# --------------------------------------------------------------------------
# Chat
# --------------------------------------------------------------------------
def get_chat_client() -> "ChatClient":
    if backend() == "mock":
        return MockChatClient()
    return OpenAIChatClient()


class ChatClient:
    def complete(self, messages: list[dict[str, str]], *, model: str | None = None) -> ChatResult:
        raise NotImplementedError

    def stream(self, messages: list[dict[str, str]], *, model: str | None = None) -> ChatStream:
        raise NotImplementedError


def _make_openai_client():
    """Build the OpenAI-compatible client for the active profile: Azure OpenAI
    (azure) or Ollama's /v1 endpoint (local). Both expose .chat.completions and
    .embeddings with compatible signatures."""
    if _profile.is_azure():
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AzureOpenAI

        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        )
        return AzureOpenAI(
            azure_endpoint=os.environ["OPENAI_ENDPOINT"],
            azure_ad_token_provider=token_provider,
            api_version=os.environ.get("OPENAI_API_VERSION", "2024-10-21"),
            max_retries=3,
            timeout=60.0,
        )
    from openai import OpenAI

    return OpenAI(
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key="ollama",  # required by SDK; ignored by Ollama
        max_retries=3,
        timeout=180.0,  # local inference can be slow
    )


class OpenAIChatClient(ChatClient):
    """OpenAI-compatible client; Ollama /v1 (local) or Azure OpenAI (azure)."""

    def __init__(self) -> None:
        self._client = _make_openai_client()

    def complete(self, messages: list[dict[str, str]], *, model: str | None = None) -> ChatResult:
        resp = self._client.chat.completions.create(
            model=model or answer_model(), messages=messages, temperature=0.1
        )
        return ChatResult(text=resp.choices[0].message.content or "", usage=resp.usage)

    def stream(self, messages: list[dict[str, str]], *, model: str | None = None) -> ChatStream:
        raw = self._client.chat.completions.create(
            model=model or answer_model(), messages=messages, temperature=0.1,
            stream=True, stream_options={"include_usage": True},
        )
        cs = ChatStream()

        def gen():
            got_usage = False
            for chunk in raw:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield delta.content
                u = getattr(chunk, "usage", None)
                if u:  # final chunk carries usage when include_usage is honored
                    cs.usage = u
                    got_usage = True
            if not got_usage:  # backend omitted stream usage — estimate from text
                cs.usage = _Usage(completion_tokens=max(1, len(cs.text) // 4))

        cs._iter = gen()
        return cs


_HEADER_RE = re.compile(r"^\[(\d+)\]\s+(.*)$")


class MockChatClient(ChatClient):
    """Deterministic, offline answer generator. Parses the EVIDENCE blocks in
    the prompt and composes a short, citation-grounded Markdown answer — enough
    to prove the contract and demo the UI without a model server."""

    def complete(self, messages: list[dict[str, str]], *, model: str | None = None) -> ChatResult:
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        is_comparison = "COMPARISON question" in user
        blocks = self._parse_blocks(user)
        if not blocks:
            answer = (
                "I don't have enough evidence in the corpus to answer that "
                "confidently. Try narrowing the question to a specific framework "
                "(e.g. the EU AI Act, ISO/IEC 42001, or the NIST AI RMF)."
            )
        elif is_comparison:
            answer = self._comparison_answer(blocks)
        else:
            answer = self._summary_answer(blocks)
        prompt_tokens = max(1, len(user) // 4)
        completion_tokens = max(1, len(answer) // 4)
        return ChatResult(
            text=answer,
            usage=_Usage(prompt_tokens, completion_tokens, prompt_tokens + completion_tokens),
        )

    def stream(self, messages: list[dict[str, str]], *, model: str | None = None) -> ChatStream:
        # Reuse the deterministic answer, then chunk it so the SSE contract can be
        # exercised offline. Fixed-size chunks guarantee deltas concatenate to the
        # exact answer (parity with the non-streaming path).
        result = self.complete(messages, model=model)
        cs = ChatStream()
        cs.usage = result.usage
        text = result.text

        def gen():
            for i in range(0, len(text), 24):
                yield text[i : i + 24]

        cs._iter = gen()
        return cs

    @staticmethod
    def _parse_blocks(user: str) -> list[dict[str, str]]:
        if "EVIDENCE:" not in user:
            return []
        ev = user.split("EVIDENCE:", 1)[1]
        blocks: list[dict[str, str]] = []
        cite, juris, buf = None, "", []
        for line in ev.splitlines():
            m = _HEADER_RE.match(line.strip())
            if m:
                if cite is not None:
                    blocks.append({"cite": cite, "juris": juris, "text": " ".join(buf).strip()})
                header = m.group(2)
                jm = re.search(r"\(([^)]*)\)\s*$", header)
                juris = jm.group(1) if jm else ""
                cite = re.sub(r"\s*\([^)]*\)\s*$", "", header).strip()
                buf = []
            elif cite is not None and line.strip() and not line.startswith("Write the answer"):
                buf.append(line.strip())
        if cite is not None:
            blocks.append({"cite": cite, "juris": juris, "text": " ".join(buf).strip()})
        return [b for b in blocks if b["text"]]

    @staticmethod
    def _first_sentence(text: str, limit: int = 240) -> str:
        s = re.split(r"(?<=[.;])\s+", text.strip())[0]
        return (s[:limit] + "…") if len(s) > limit else s

    def _summary_answer(self, blocks: list[dict[str, str]]) -> str:
        bullets = "\n".join(
            f"- {self._first_sentence(b['text'])} [{b['cite']}]" for b in blocks[:4]
        )
        return f"Here's what the corpus says:\n\n{bullets}"

    def _comparison_answer(self, blocks: list[dict[str, str]]) -> str:
        by_juris: dict[str, list[dict[str, str]]] = {}
        for b in blocks:
            by_juris.setdefault(b["juris"] or "general", []).append(b)
        shared = (
            "- Both regimes address governance and risk obligations for AI systems "
            f"[{blocks[0]['cite']}]" + (f"; [{blocks[1]['cite']}]" if len(blocks) > 1 else "") + "."
        )
        diffs = "\n".join(
            f"- **{juris}**: {self._first_sentence(bs[0]['text'])} [{bs[0]['cite']}]"
            for juris, bs in by_juris.items()
        )
        stricter = (
            "- On the supplied evidence, the more prescriptive obligations appear in "
            f"[{blocks[0]['cite']}]."
        )
        return (
            f"**Shared requirements**\n\n{shared}\n\n"
            f"**Key differences**\n\n{diffs}\n\n"
            f"**What's stricter**\n\n{stricter}"
        )


# --------------------------------------------------------------------------
# Embeddings
# --------------------------------------------------------------------------
def get_embed_client() -> "EmbedClient":
    if backend() == "mock":
        return MockEmbedClient()
    return OpenAIEmbedClient()


class EmbedClient:
    def embed(self, texts: list[str], *, model: str | None = None) -> tuple[list[list[float]], _Usage]:
        raise NotImplementedError


class MockEmbedClient(EmbedClient):
    def embed(self, texts: list[str], *, model: str | None = None) -> tuple[list[list[float]], _Usage]:
        # No real vectors needed (MockVectorClient ignores them); return empties
        # and a small token count so the ledger shows embedding activity.
        toks = sum(max(1, len(t) // 4) for t in texts)
        return ([[] for _ in texts], _Usage(prompt_tokens=toks, total_tokens=toks))


class OpenAIEmbedClient(EmbedClient):
    def __init__(self) -> None:
        self._client = _make_openai_client()

    def embed(self, texts: list[str], *, model: str | None = None) -> tuple[list[list[float]], _Usage]:
        resp = self._client.embeddings.create(model=model or embed_model(), input=texts)
        return ([d.embedding for d in resp.data], resp.usage)


# --------------------------------------------------------------------------
# Reranker (cross-encoder, profile-gated — PLAN §4)
# --------------------------------------------------------------------------
def reranker_enabled() -> bool:
    return (os.environ.get("RERANKER_ENABLED") or "true").lower() not in ("false", "0", "no")


def reranker_model() -> str:
    return os.environ.get("RERANKER_MODEL", "bge-reranker-base")


def layout_backend() -> dict:
    """Layout / PDF-extraction backend for the active profile (profile branching
    lives here, not in the ingest pipeline). `azure` → Azure AI Document
    Intelligence (prebuilt-layout) via endpoint + Managed Identity; `local`/`mock`
    → the local unstructured.io service. The ingest pipeline reads this descriptor
    to decide how to extract page-tagged text from PDFs."""
    if backend() != "mock" and _profile.is_azure():
        return {
            "kind": "document_intelligence",
            "endpoint": os.environ.get("DOCINTEL_ENDPOINT", ""),
            "model": "prebuilt-layout",
        }
    return {
        "kind": "unstructured",
        "url": os.environ.get("UNSTRUCTURED_URL", "http://localhost:8002"),
    }


def get_reranker() -> "Reranker | None":
    """`local` → TEI cross-encoder (`bge-reranker-base`). `azure` → None (Azure AI
    Search applies its semantic ranker inline). `mock`/disabled → None."""
    if backend() == "mock" or not reranker_enabled() or _profile.is_azure():
        return None
    return TEIReranker(os.environ.get("RERANKER_URL", "http://localhost:8081"))


class Reranker:
    def rerank(self, query: str, texts: list[str]) -> list[tuple[int, float]]:
        """Return [(original_index, score)] sorted best-first."""
        raise NotImplementedError


class TEIReranker(Reranker):
    """Hugging Face Text Embeddings Inference /rerank endpoint."""

    def __init__(self, url: str) -> None:
        self._url = url.rstrip("/")

    def rerank(self, query: str, texts: list[str]) -> list[tuple[int, float]]:
        import httpx

        resp = httpx.post(
            f"{self._url}/rerank",
            json={"query": query, "texts": texts, "raw_scores": False},
            timeout=30.0,
        )
        resp.raise_for_status()
        return [(d["index"], float(d["score"])) for d in resp.json()]
