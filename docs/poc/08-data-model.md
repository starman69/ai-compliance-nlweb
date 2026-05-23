# 08 — Data model (two collections)

> The vector store holds **two collections/indexes per profile**. Implementation:
> [`src/shared/vector_search.py`](../../src/shared/vector_search.py),
> index schemas in [`scripts/aisearch/`](../../scripts/aisearch/). Decisions:
> [ADR-0003](../adr/0003-embedding-model-per-store.md). Diagram: [`10-diagrams` §6](10-diagrams.md).

## The two collections
| Collection / index | Granularity | Role |
|---|---|---|
| **`compliance_docs`** | 1 point per document (summary embedding) | corpus explorer, framework routing, coarse recall |
| **`compliance_chunks`** | 1 point per section (structure-aware chunk) | detailed retrieval + **citations** |

`local` → Qdrant collections (`compliance_docs`, `compliance_chunks`); `azure` → Azure AI
Search indexes (`compliance-docs-index`, `compliance-chunks-index`).

## Chunk fields (`compliance_chunks`)
`chunk_id`, `doc_id`, `short_name`, `title`, `jurisdiction`, `framework_family`,
`section_path` (e.g. "Art. 9 §2" — drives the citation), `page`, `url`, `status`, `text`,
and the **`embedding`** vector. These payload fields back the inline citation
`[short_name §section, p.N]` and the jurisdiction/doc-hint filters (see
[05-retrieval-and-ranking](05-retrieval-and-ranking.md)).

## Vectors
- **`local` (Qdrant):** named **`dense`** (1024-d, cosine) **+ `sparse`** (BM25) per point →
  hybrid search fused with RRF.
- **`azure` (AI Search):** a 1536-d `embedding` field (HNSW) + searchable text for keyword/BM25
  → hybrid + the semantic ranker.

A store's embedding **dimension is immutable** once created, so the two profiles are ingested
independently into their own matched stores ([ADR-0003](../adr/0003-embedding-model-per-store.md)).

## Ingestion
`manifest/corpus.yaml` → fetch → structure-aware chunk (≈200 words, 900-char embed cap) →
embed (batched) → upsert (batched at 128). Real-parsed chunks union with curated seed chunks
(`data/mock_chunks.yaml`) so high-value provisions stay retrievable even where PDF extraction
is noisy. A `MockVectorClient` mirrors the same interface for offline tests/UI.
