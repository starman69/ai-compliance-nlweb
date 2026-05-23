# CLAUDE.md — AI Compliance NLWeb

Project context for Claude Code sessions. This file is the source of truth for settled
decisions, correctness rules, and the reuse map. Architecture lives in [`docs/poc/`](docs/poc/)
(overview, architecture, diagrams), decisions in [`docs/adr/`](docs/adr/), and live status in
[`docs/poc/STATUS.md`](docs/poc/STATUS.md).

## Mission
A conversational compliance workbench: an **NLWeb**-style layer over the world's AI rules
and standards. One retrieval+answer core exposed two ways — **`/ask`** (humans/UI →
structured JSON, Schema.org `ItemList`) and **`/mcp`** (agents → MCP tools) — over a
curated, **100% open-access** corpus of AI-compliance documents. Dual runtime profile —
**`local`** (Docker: Ollama + Qdrant) ↔ **`azure`** (Azure OpenAI + Azure AI Search).
RAG-only; accuracy is the bar because the domain is regulatory. Recreates a lost prior app
(see the Medium write-up and `docs/images/reference/`).

## Settled at build start
| Item | Decision |
|---|---|
| `local` profile | Ollama **`qwen3:14b`** answers + **`mxbai-embed-large`** (1024-d) → **Qdrant** (hybrid dense+sparse) |
| `azure` profile (the "cloud") | Azure OpenAI **`gpt-4.1`** answers + **`text-embedding-3-small`** (1536-d) → **Azure AI Search**. Full contract-app parity; **replaces Claude** |
| Reranker | **On by default**; `local` `bge-reranker-base`, `azure` AI Search semantic ranker; env toggle `RERANKER_ENABLED` |
| National frameworks (Tier 2) | AIDA **+ Singapore + Brazil + China** |
| Tier 5 sector/cloud | **Open-only**: CSA, MS Responsible AI v2, Google SAIF |
| Corpus size | **48 documents, all open-access** (8/16/13/8/3 by tier) |
| **Paywalled content** | **None in the public repo.** ISO/IEC standards → **open authored summaries** in `manifest/summaries/` (`source_type: authored_summary`), non-normative |
| Dual-stack env | **Lean** — no MSSQL/Azurite keys (RAG-only) |
| `/mcp` transport | Streamable HTTP on the same FastAPI app |
| Local-dev auth | Dev bearer-token fallback (a simple `X-Reviewer`-style shortcut) |
| Repo / Pages | `ai-compliance-nlweb` → `starman69.github.io/ai-compliance-nlweb` |

## Correctness rules (do not violate)
- **Embedding model is fixed per store** — `local`: `mxbai-embed-large` 1024-d → Qdrant;
  `azure`: `text-embedding-3-small` 1536-d → Azure AI Search. A store's dim is immutable;
  the profile selects the matched **{store, embedder, answer-model}** triple — never embed
  one store with the other's model. *(Decision history: we briefly considered one shared
  Qdrant + Claude, then settled on full contract-app parity — separate stores per profile,
  Azure replacing Claude. So the two profiles are independently ingested.)*
- **`/ask` and `/mcp` share one core** — same payload, `query` the only required field;
  logic must not fork between the two endpoints.
- **`mode` gates LLM use** — `list` = retrieval only, **no LLM**; only `summarize` and
  `generate` invoke the model.
- **Profile branching lives in `clients.py` factories**, not business logic.
- **Token ledger + audit must never break the answer path** — swallow own errors, log only.
- **Citations are load-bearing** — every claim cites `[short_name §section, p.N]`;
  insufficient evidence → say so; quotes render as **plain text**.
- **Security on both endpoints** — token scopes, rate limiting, CORS, audit logging.
- **No paywalled content in the repo** — ISO/IEC standards are open authored summaries
  (public facts only, non-normative). `sources/manual/` is an optional local-only path
  (gitignored); the corpus is fully reproducible from open sources.
- **Manifest (`manifest/corpus.yaml`) is the source of truth** for corpus contents/status.
- **Compose / Docker project name is `compliance`** — never `local` (that's Contract
  Intelligence). Set `name: compliance` in the compose file + `COMPOSE_PROJECT_NAME=compliance`.
- **`azure` profile** = Azure OpenAI prompt caching — order the static system prompt/framing
  first so gpt-4.1 caches the prefix. No Anthropic/Claude anywhere in this build.

## NLWeb contract (quick reference)
- Shared request payload: `query` (required), `prev[]` (multi-turn), `decontextualized_query`,
  `site` (scope → jurisdiction filter), `mode` (`list|summarize|generate`).
- `/ask` → `ItemList`-shaped JSON: `query_id, answer, mode, confidence, intent, sources[],
  scope, token_usage, model, elapsed_ms, retrieval`.
- Endpoints: `POST /ask`, `GET|POST /mcp`, `GET /corpus`, `GET /health`.
- Two collections/indexes per store: **`compliance_docs`** (1 point/doc, summary embedding)
  and **`compliance_chunks`** (1 point/section, citations). `local`: Qdrant, 1024-d, named
  dense+sparse + RRF. `azure`: Azure AI Search indexes, 1536-d, vector + semantic ranker.

## Core modules (`src/shared/`)
`clients.py` (the `local`/`azure` factory branches — Ollama↔Azure OpenAI, Qdrant↔Azure AI
Search), `token_ledger.py`, `pricing.py`, `vector_search.py` (Qdrant **+ Azure AI Search**
clients + sparse/hybrid + **Mock**), `embedding_text.py`, `prompts.py`, `router.py`,
`config.py`. **No** SQL/HITL/Functions/Event-Grid/blob — **but keep Azure OpenAI + Azure AI
Search + Azure AI Document Intelligence** (`azure`-layout extraction; `clients.layout_backend()`)
as the `azure` profile's managed backends (endpoint + `DefaultAzureCredential`), provisioned by
**Bicep IaC** (`infra/bicep/`).
Design system: OKLCH cool-paper + ink-navy, Fraunces/General Sans, Tailwind v4, light/dark.
`.mcp.json` (Playwright + Chrome DevTools) for UI automation.

> `RUNTIME_PROFILE` is **`local|azure`**; the `azure` profile is the "cloud" option. All
> profile branching lives in the `clients.py` factories.

## Build phases — status
Nine phases: scaffold → fetch pipeline → local stack → ingestion+retrieval → NLWeb API
(`/ask`+`/mcp`) → frontend+UI validation → accuracy pass → azure profile → polish+showcase.
**Live, per-phase status lives in [`docs/poc/STATUS.md`](docs/poc/STATUS.md)** (the source of
truth — don't duplicate phase status here, it drifts).

## Conventions
- **TDD**: write `tests/unit` first for pure modules (router, mode engine, payload
  validation, condense, ItemList/citation shaping, chunking, embedding header, scope
  checks). Add a **compose↔app contract test** (env vars, collection names,
  `EMBEDDING_DIM=1024`, `/ask`+`/mcp` routes, model names in sync).
- **Agent team / sub-agents** for parallelizable code slices (backend slices, UI
  validation). Doc/manifest authoring stays single-author for coherence.
- **Docs are first-class** — each phase lands its `docs/poc/NN-*.md` and any ADR
  (`docs/adr/NNNN-*.md`, Status/Date/Context/Decision/Consequences).
- Python 3.11; FastAPI; React + Vite + TS + Tailwind v4.
- **`NLWEB_BACKEND` defaults to `real`** (live local models) — the UI/app uses real
  Ollama `qwen3:14b` + `mxbai`. **`mock` is tests/CI only** (pinned in `tests/conftest.py`):
  deterministic cited answers from `data/mock_chunks.yaml` + the ISO summaries, no model server.
- Local stack runs on **GPU** — the compose `ollama` service reserves the NVIDIA device
  (`deploy.resources.reservations.devices`); verified on an RTX 3080 Ti (12 GB).
- Ingest before answering on a fresh store: `scripts/ingest.py` (chunk → embed → upsert).
- Start build sessions from this folder (`~/mygit/ai-compliance-nlweb`).
