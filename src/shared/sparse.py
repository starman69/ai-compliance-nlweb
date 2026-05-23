"""BM25 sparse vectors via fastembed (`Qdrant/bm25`) for hybrid retrieval.

Pure-ish (fastembed lazy-imported + cached). BM25 is stateless/IDF-based — no
neural model, no GPU — so it's cheap to run at ingest and query time. Documents
and queries are encoded slightly differently (`embed` vs `query_embed`).
Returns (indices, values) ready for a Qdrant SparseVector.
"""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _model():
    from fastembed import SparseTextEmbedding

    return SparseTextEmbedding("Qdrant/bm25")


def embed_documents(texts: list[str]) -> list[tuple[list[int], list[float]]]:
    return [
        ([int(i) for i in s.indices], [float(v) for v in s.values])
        for s in _model().embed(list(texts))
    ]


def embed_query(text: str) -> tuple[list[int], list[float]]:
    s = next(iter(_model().query_embed([text])))
    return ([int(i) for i in s.indices], [float(v) for v in s.values])
