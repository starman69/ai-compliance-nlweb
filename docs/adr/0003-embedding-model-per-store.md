# 0003 — Embedding model is fixed per store (immutable dimension)

- **Status:** Accepted
- **Date:** 2026-05-23
- **Deciders:** Dave Patten
- **Related:** ADR-0001 (dual runtime) · [05-retrieval-and-ranking](../poc/05-retrieval-and-ranking.md) · [08-data-model](../poc/08-data-model.md)

## Context
A vector store's dimensionality is fixed when the collection/index is created. The two runtime
profiles use different embedders with different output dims: `local` Ollama
`mxbai-embed-large` (1024-d) and `azure` Azure OpenAI `text-embedding-3-small` (1536-d).
Mixing — e.g. querying a 1024-d Qdrant collection with a 1536-d vector — is a silent
correctness bug.

## Decision
The embedding model is **matched to the store and immutable per store**. Each profile owns a
separate, independently-ingested store:

| Profile | Embedder | Dim | Store |
|---|---|---|---|
| `local` | `mxbai-embed-large` | 1024 | Qdrant (`compliance_chunks`, `compliance_docs`) |
| `azure` | `text-embedding-3-small` | 1536 | Azure AI Search (`compliance-chunks-index`, `compliance-docs-index`) |

The active triple `{store, embedder, answer-model}` is selected entirely in the `clients.py`
factories; business logic never chooses an embedder. You **never** embed one store with the
other profile's model. Switching profiles means ingesting into that profile's store.

## Consequences
### Positive
- No dimension-mismatch class of bugs; each store is internally consistent.
- The contract test (`tests/unit/test_bicep_app_contract.py`) pins 1536 across the Azure index
  JSON + Bicep + `clients.py`; the compose contract test pins 1024 for local.

### Negative / trade-offs
- The corpus must be ingested once per profile (no shared embedding layer).

### Follow-ups
- Keep the dim assertions in the contract tests in sync with the embedder choice.
