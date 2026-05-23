# 05 — Retrieval & ranking

> How the core turns a question into the eight cited chunks an answer is allowed to use.
> Implementation: [`src/shared/service.py`](../../src/shared/service.py) +
> [`src/shared/vector_search.py`](../../src/shared/vector_search.py). Diagram:
> [`10-diagrams` §4](10-diagrams.md). Decisions: [ADR-0003](../adr/0003-embedding-model-per-store.md).

## Pipeline
1. **Decontextualize** — condense an anaphoric follow-up into a standalone query and inherit
   prior scope ([ADR-0010](../adr/0010-multi-turn-condensation.md)).
2. **Route** — classify intent + detect scope (jurisdiction tokens + framework `doc_hints`)
   from the query (`router.py`, rules-first).
3. **Hybrid retrieve** — embed the query and run **dense + sparse** in parallel:
   - dense: `mxbai-embed-large` 1024-d (local) / `text-embedding-3-small` 1536-d (azure);
   - sparse: BM25 (fastembed) — catches exact statute/article numbers dense vectors miss.
4. **Fuse** — Reciprocal-Rank Fusion (RRF) of the two result sets → ~32 candidates
   (`RETRIEVE_CANDIDATES`, capped at the reranker's 32-item batch). Azure uses AI Search's
   native hybrid + semantic ranker.
5. **Rerank** — a cross-encoder (`bge-reranker-base` via TEI, local) scores all candidates;
   the top **`RERANK_TOP=8`** become the cited sources. On by default (`RERANKER_ENABLED`).
6. **Confidence** — derived from the top reranked score (scale-aware: cosine ≤1 for real
   stores, token-overlap for the Mock).

## Scope filtering & doc-hint steering
`site`/explorer jurisdiction tokens are AND-ed into the store filter. When the query **names a
framework** (e.g. "GDPR", "NIST AI Risk Management Framework"), the router emits a `doc_id`
hint and Qdrant **hard-filters to that document** — so "GDPR requirements for AI?" searches the
GDPR, not whichever EU text says "AI" most often. A stale/loose hint falls back to the
jurisdiction-only filter (never an empty result set). The EU AI Act hint covers the act **and**
its Annexes; UK covers both the pro-innovation paper and the ICO guidance.

## Why hybrid + rerank
Dense alone misses exact identifiers; sparse alone misses paraphrase. RRF gets both into the
candidate pool; the cross-encoder then makes the final relevance call, so the eight cited chunks
are the most relevant of the 32 — not just the first eight one index returned. Every stage
**fails safe**: embedding/rerank errors degrade gracefully and never break the answer path.
