# 0001 — Dual runtime profile: `local` (Ollama + Qdrant) ↔ `azure` (Azure OpenAI + AI Search)

- **Status:** Accepted
- **Date:** 2026-05-23
- **Deciders:** Dave Patten
- **Related:** ADR-0003 (embedding per store) · ADR-0012 · ADR-0016
- **History:** An earlier draft proposed `local` (Ollama) ↔ `cloud` (Claude) over a *single* shared Qdrant store. That was reversed in favor of two profiles with **separate per-profile stores** and Azure OpenAI in place of Claude (below).

## Context
The POC must run **fully locally** (Docker + a local model + a local vector store) for
zero-cost, offline-capable development, and also offer a more capable hosted profile for
accuracy work and the showcase. We want one codebase that serves both via a factory seam,
with profile differences confined to client construction. Anthropic/Claude is **not** used —
the hosted profile is Azure OpenAI, which also provides embeddings (Claude does not), so a
single managed provider covers chat + embeddings on that profile.

## Decision
We will support two runtime profiles selected by **`RUNTIME_PROFILE`**, with these names and
semantics:

- **`local`** — Ollama **`qwen3:14b`** answers + **`mxbai-embed-large`** (1024-d) embeddings;
  vector store **Qdrant** (hybrid dense+sparse + RRF); reranker `bge-reranker-base`. Runs
  entirely on Docker, $0.
- **`azure`** — Azure OpenAI **`gpt-4.1`** answers + **`text-embedding-3-small`** (1536-d)
  embeddings; vector store **Azure AI Search** (vector + semantic ranker); auth via
  `DefaultAzureCredential`. Reaches managed Azure resources by endpoint (no Bicep in this
  repo; provision separately).

Each profile is a **matched {store, embedder, answer-model} triple** — the two profiles use
**separate vector stores** that are populated independently. **All profile branching lives in
the `clients.py` factories**, never in business logic.

## Consequences
### Positive
- One implementation serves both profiles: the `clients.py` factory (both branches), the
  `vector_search` abstraction (`QdrantVectorClient` + `AzureSearchVectorClient`), `pricing.py`,
  and `token_ledger.py` are all profile-agnostic above the factory.
- One language and one eval harness across profiles; clean model-vs-model comparison
  (`qwen3:14b` vs `gpt-4.1`) per ADR-0009.
- `local` keeps the "local-first, free, offline" story intact as the default.

### Negative / trade-offs
- Two stores must each be ingested (no single shared collection); embedding dim differs by
  store (1024 vs 1536) — see ADR-0003.
- The `azure` profile requires real Azure resources (Azure OpenAI deployments + an AI Search
  service), so it is not free or offline.

### Follow-ups
- Implement `clients.py` with `local|azure` branches; no SQL/HITL/blob/DI (ADR-0012).
- Bootstrap creates Qdrant collections (`local`) and Azure AI Search indexes at 1536-d (`azure`).
- Compose↔app contract test asserts model/deployment names + dims stay in sync per profile.
