"""Vector-search abstraction with three implementations (PLAN.md §4):

- MockVectorClient        — offline; token-overlap scoring over seed chunks
                            (the 4 ISO summaries + a curated mock-chunk set).
                            Lets the API + UI run with no Qdrant/Ollama/Azure.
- QdrantVectorClient       — `local` profile: dense (+sparse) vector search + payload filter.
- AzureSearchVectorClient  — `azure` profile: hybrid + semantic ranker.

All return `list[dict]` chunk payloads carrying a `score` float. Heavy SDK
imports are lazy so this module parses without qdrant/azure installed.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]

_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "what", "how", "do", "i", "my", "we", "with", "under", "must", "does", "be",
    "that", "this", "it", "as", "by", "at", "from", "about", "which", "their",
}


def tokenize(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    # keep short but meaningful tokens (numbers, article refs) + words >=3
    return [t for t in raw if (t not in _STOPWORDS and (len(t) >= 3 or t.isdigit()))]


class VectorSearchClient(Protocol):
    def search(
        self,
        *,
        query_text: str,
        vector: list[float] | None = None,
        top: int = 40,
        jurisdictions: list[str] | None = None,
        doc_hints: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...


# --------------------------------------------------------------------------
# Mock implementation (offline)
# --------------------------------------------------------------------------
def _parse_summary_chunks(md_path: Path, doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Split an authored ISO summary (## headings) into chunks."""
    if not md_path.exists():
        return []
    text = md_path.read_text(encoding="utf-8")
    chunks: list[dict[str, Any]] = []
    current_section = "Overview"
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if len(body) < 40:
            return
        chunks.append(
            {
                "chunk_id": f"{doc['id']}::{current_section[:40]}",
                "doc_id": doc["id"],
                "short_name": doc["short_name"],
                "title": doc["title"],
                "jurisdiction": doc["jurisdiction"],
                "framework_family": doc.get("framework_family"),
                "section_path": current_section,
                "page": None,
                "url": doc.get("official_url"),
                "status": doc.get("status"),
                "text": body,
            }
        )

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            current_section = line[3:].strip()
            buf = []
        elif line.startswith("#") or line.startswith(">"):
            continue
        else:
            buf.append(line)
    flush()
    return chunks


@lru_cache(maxsize=1)
def _load_mock_chunks() -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    # 1) curated mock chunks
    seed = _REPO_ROOT / "data" / "mock_chunks.yaml"
    if seed.exists():
        data = yaml.safe_load(seed.read_text(encoding="utf-8")) or {}
        chunks.extend(data.get("chunks", []))
    # 2) ISO authored summaries (real text) -> chunks
    try:
        from . import corpus

        for doc in corpus.documents():
            if doc.get("source_type") == "authored_summary" and doc.get("path"):
                md = _REPO_ROOT / "manifest" / doc["path"]
                chunks.extend(_parse_summary_chunks(md, doc))
    except Exception:  # pragma: no cover - manifest optional in some tests
        pass
    return chunks


class MockVectorClient:
    """Offline retriever: token-overlap scoring + jurisdiction/doc filters."""

    def __init__(self, chunks: list[dict[str, Any]] | None = None) -> None:
        self._chunks = chunks if chunks is not None else _load_mock_chunks()

    def search(
        self,
        *,
        query_text: str,
        vector: list[float] | None = None,
        top: int = 40,
        jurisdictions: list[str] | None = None,
        doc_hints: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        q_terms = set(tokenize(query_text))
        juris = set(jurisdictions or [])
        hints = set(doc_hints or [])
        scored: list[tuple[float, dict[str, Any]]] = []
        for ch in self._chunks:
            if juris and ch.get("jurisdiction") not in juris:
                continue
            title_terms = set(tokenize(f"{ch.get('short_name','')} {ch.get('title','')} {ch.get('section_path','')}"))
            body_terms = set(tokenize(ch.get("text", "")))
            score = 3.0 * len(q_terms & title_terms) + 1.0 * len(q_terms & body_terms)
            if not score and not (juris or hints):
                continue
            if ch.get("doc_id") in hints:
                score += 6.0
            if score <= 0:
                continue
            out = dict(ch)
            out["score"] = round(score, 3)
            scored.append((score, out))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [c for _, c in scored[:top]]


# --------------------------------------------------------------------------
# Qdrant implementation (local profile)
# --------------------------------------------------------------------------
class QdrantVectorClient:
    """Dense (+ optional sparse) vector search with a payload filter."""

    DENSE = "dense"

    def __init__(self, url: str, collection: str) -> None:
        from qdrant_client import QdrantClient

        self._qc = QdrantClient(url=url, check_compatibility=False)
        self._collection = collection

    def ensure_collection(self, dim: int, *, recreate: bool = False) -> None:
        """Create the collection (named dense + sparse vectors). If recreate,
        drop an existing collection first for a clean ingest."""
        from qdrant_client.models import Distance, SparseVectorParams, VectorParams

        names = {c.name for c in self._qc.get_collections().collections}
        if self._collection in names:
            if not recreate:
                return
            self._qc.delete_collection(self._collection)
        self._qc.create_collection(
            collection_name=self._collection,
            vectors_config={self.DENSE: VectorParams(size=dim, distance=Distance.COSINE)},
            sparse_vectors_config={"sparse": SparseVectorParams()},
        )

    def upsert(self, chunks: list[dict[str, Any]], vectors: list[list[float]]) -> int:
        import uuid

        from qdrant_client.models import PointStruct, SparseVector

        # BM25 sparse vectors for hybrid retrieval (best-effort).
        sparses: list[tuple[list[int], list[float]]] | None = None
        try:
            from . import sparse as _sparse

            sparses = _sparse.embed_documents([c.get("text", "") for c in chunks])
        except Exception:
            sparses = None

        points = []
        for i, (c, v) in enumerate(zip(chunks, vectors)):
            if not v:
                continue
            named: dict[str, Any] = {self.DENSE: list(v)}
            if sparses and sparses[i][0]:
                idx, val = sparses[i]
                named["sparse"] = SparseVector(indices=idx, values=val)
            key = c.get("chunk_id") or f"{c.get('doc_id')}:{c.get('section_path')}"
            points.append(
                PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, key)), vector=named, payload=c)
            )
        # Upsert in batches — a single huge request can exceed Qdrant's payload limit.
        batch = 128
        for i in range(0, len(points), batch):
            self._qc.upsert(collection_name=self._collection, points=points[i : i + batch])
        return len(points)

    def search(
        self,
        *,
        query_text: str,
        vector: list[float] | None = None,
        top: int = 40,
        jurisdictions: list[str] | None = None,
        doc_hints: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not vector:
            raise ValueError("QdrantVectorClient.search requires a dense vector")

        # When the query names a specific framework, AND its doc_id into the
        # filter (router contract) so retrieval is steered to that document —
        # e.g. "GDPR requirements for AI" must search GDPR, not let the AI Act
        # (which is lexically far denser in "AI") drown it out. Fall back to the
        # jurisdiction-only filter if the hint yields nothing (a stale/loose hint
        # must never return an empty result set).
        out = self._query(query_text, vector, top, self._filter(jurisdictions, doc_hints))
        if doc_hints and not out:
            out = self._query(query_text, vector, top, self._filter(jurisdictions, None))
        return out

    @staticmethod
    def _filter(jurisdictions: list[str] | None, doc_hints: list[str] | None):
        from qdrant_client.models import FieldCondition, Filter, MatchAny

        must = []
        if jurisdictions:
            must.append(FieldCondition(key="jurisdiction", match=MatchAny(any=jurisdictions)))
        if doc_hints:
            must.append(FieldCondition(key="doc_id", match=MatchAny(any=doc_hints)))
        return Filter(must=must) if must else None

    def _query(self, query_text: str, vector: list[float], top: int, qfilter) -> list[dict[str, Any]]:
        # Hybrid: prefetch dense + sparse, fuse with RRF. Falls back to dense-only
        # if the sparse encoder/collection isn't available (never breaks the path).
        response = None
        try:
            from qdrant_client.models import Fusion, FusionQuery, Prefetch, SparseVector

            from . import sparse as _sparse

            sidx, sval = _sparse.embed_query(query_text)
            response = self._qc.query_points(
                collection_name=self._collection,
                prefetch=[
                    Prefetch(query=list(vector), using=self.DENSE, limit=top, filter=qfilter),
                    Prefetch(
                        query=SparseVector(indices=sidx, values=sval),
                        using="sparse", limit=top, filter=qfilter,
                    ),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=top,
                with_payload=True,
            )
        except Exception:
            response = None
        if response is None:
            response = self._qc.query_points(
                collection_name=self._collection, query=list(vector), using=self.DENSE,
                limit=top, query_filter=qfilter, with_payload=True,
            )

        out: list[dict[str, Any]] = []
        for r in response.points:
            payload = dict(r.payload or {})
            payload["score"] = float(r.score)
            out.append(payload)
        return out


# --------------------------------------------------------------------------
# Azure AI Search implementation (azure profile)
# --------------------------------------------------------------------------
class AzureSearchVectorClient:
    """Hybrid (vector + keyword) + semantic ranker."""

    def __init__(self, endpoint: str, index_name: str, credential: Any) -> None:
        from azure.search.documents import SearchClient

        self._sc = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)

    def search(
        self,
        *,
        query_text: str,
        vector: list[float] | None = None,
        top: int = 40,
        jurisdictions: list[str] | None = None,
        doc_hints: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        from azure.search.documents.models import VectorizedQuery

        vqs = []
        if vector:
            vqs = [VectorizedQuery(vector=vector, k_nearest_neighbors=top, fields="embedding")]
        odata = None
        if jurisdictions:
            ids = ",".join(jurisdictions)
            odata = f"search.in(jurisdiction, '{ids}', ',')"
        results = self._sc.search(
            search_text=query_text,
            vector_queries=vqs or None,
            query_type="semantic" if os.environ.get("RERANKER_ENABLED", "true") != "false" else "simple",
            semantic_configuration_name="default",
            top=top,
            filter=odata,
        )
        out: list[dict[str, Any]] = []
        for r in results:
            d = dict(r)
            d["score"] = float(d.get("@search.reranker_score") or d.get("@search.score") or 0.0)
            out.append(d)
        return out
