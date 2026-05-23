# STATUS

Phase-by-phase build status for AI Compliance NLWeb.

_Last updated: 2026-05-23_

## Legend
✅ done · 🚧 in progress · ⬜ not started

## Phases
| # | Phase | Status | Notes |
|---|---|---|---|
| 1 | Scaffold + manifest + docs skeleton | ✅ | Skeleton, manifest (48 open docs + 4 ISO summaries), CLAUDE.md, docs 00/01, ADRs. |
| 2 | Fetch pipeline (`scripts/fetch_corpus.py`) | ✅ | Open auto-fetch (PDF + HTML→MD + EUR-Lex PDF rendering w/ 202-retry + CELEX + browser UA), `authored_summary` copy, `_index.json`. ~41 fetched + 4 summaries; recovered NYC/OSTP/OMB-25-22/Illinois (browser UA + correct URLs + Wayback). Remaining gaps: CoE (bot-blocked), UNESCO (JS viewer), Texas (transient) — seed-covered where it matters. |
| 3 | Local stack up (`infra/compose/`, project `compliance`) | ✅ | `docker compose up` — qdrant + **GPU Ollama (RTX 3080 Ti)** + api + web running under project `compliance`; `/health` green with `backend: real, qwen3:14b`. |
| 4 | Ingestion + retrieval | ✅ | `scripts/ingest.py` + `src/ingest/chunking.py`; **~1044 chunks** from 33 real docs in Qdrant (1024-d dense **+ BM25 sparse**). **Hybrid dense+sparse RRF fusion + cross-encoder rerank (`bge-reranker-base`)** — `fusion: rrf+rerank`. Jurisdiction scope filter wired (explorer `site` → vector filter). EU OJ PDFs gated (pypdf-garbled) → clean seed; `unstructured` service would unlock real EU text. |
| 5 | NLWeb API (TDD): `/ask` + `/mcp` | ✅ | One shared core, two contracts; mode engine, router, citations, security, audit. **57 unit/API tests green.** NLWeb conformance: `/ask` emits an additive Schema.org `ItemList` (`item_list`) beside native `sources`; `/mcp` JSON-RPC (proto `2025-11-25`, version echo) exposes tool **descriptions** in `GET /mcp` + `tools/list`. **`POST /ask/stream` (SSE)** streams the same core (`sources`→`delta`→`done`); usage accurate via `stream_options.include_usage` (qwen3 verified). Guides [19](19-nlweb-ask-endpoint.md)/[20](20-mcp-server.md) done; 21 TODO. |
| 6 | Frontend + automated UI validation | ✅ | React UI (explorer, multi-turn, Sources, confidence/token bar, scope, modes, light/dark). **Token-by-token streaming** via `/ask/stream` SSE (progressive markdown + `▍` cursor, sources/metabar on `done`). Validated live via Chrome DevTools MCP; canonical light-mode showcase screenshots in `site/images/` (empty · answer+sources · comparison · explorer · multi-turn · Swagger). |
| 7 | Accuracy pass | ✅ | `eval/golden_qa.yaml` (**36 Q&A** across all 5 tiers + every intent + `generate` mode) + `eval/run_eval.py`; with hybrid+rerank+doc-hint steering: **36/36 · retrieval hit-rate 36/36 · mean term coverage 97% · intent 100%** (`docs/poc/eval-baselines/2026-05-23-local-golden-qa-qwen3-14b.md`). Got there by fixing router doc-hint routing (NIST AI RMF spelled-out cue vs ISO 23894; EU AI Act hints act **+ annexes**; UK hints pro-innovation **+ ICO**), making Qdrant honor `doc_hints` as a hard filter, and giving the curated GDPR Art. 22 chunk an explicit "Article 22" label. Now covers the recovered international/national/sector docs (UNESCO, CoE, Singapore, China, Brazil, UK ICO, FedRAMP, ENISA, MS Responsible AI). |
| 8 | Azure profile | 🚧 | Code-complete (clients/vector_search/compose). **Full Bicep IaC in [`infra/bicep/`](../../infra/bicep/)** (Azure OpenAI + AI Search + Container Apps + Static Web App + observability + MI RBAC) — `bicep build` clean; bicep↔app contract test green. Not run live (no Azure creds). |
| 9 | Polish + showcase | 🚧 | Docs/ADRs done for built parts incl. [`10-diagrams`](10-diagrams.md) (7 Mermaid: NLWeb core, container, /ask sequence, retrieval, dual runtime, ingestion, deployment). Screenshots need regenerating after final UI (light-mode, curated) — task tracked. `site/` GitHub Pages TODO. |

## What runs right now
**Live local stack (the app default — real models on GPU):**
```bash
cd infra/compose && docker compose up -d          # qdrant + GPU ollama + api + web (project: compliance)
docker compose exec ollama ollama pull qwen3:14b && docker compose exec ollama ollama pull mxbai-embed-large
NLWEB_BACKEND=real RUNTIME_PROFILE=local PYTHONPATH=src python scripts/ingest.py   # embed corpus -> Qdrant
open http://localhost:8088                          # answers from real qwen3:14b + mxbai + Qdrant
```
`NLWEB_BACKEND` defaults to **`real`**. The UI uses real local models (qwen3:14b answers,
mxbai-embed-large embeddings, Qdrant hybrid retrieval).

**Mock backend = tests/CI only** (pinned in `tests/conftest.py`): grounded deterministic
answers from a curated offline seed, no model server.
```bash
python -m pytest          # 54 passed (Mock)
```

## Phase 1 checklist
- [x] Kickoff questions settled (recorded in `CLAUDE.md`).
- [x] Directory skeleton (`manifest/`, `sources/`, `scripts/`, `src/`, `eval/`, `docs/`, `infra/compose/`, `site/`, `tests/`).
- [x] `manifest/corpus.yaml` — 48 open-access documents (8/16/13/8/3 by tier); validated.
- [x] `manifest/summaries/` — 4 open ISO authored summaries (42001, 23894, 22989, 38507).
- [x] `CLAUDE.md` — context, settled decisions, correctness rules, reuse map.
- [x] No-paywalled / open-corpus decision reconciled across CLAUDE.md + ADRs.
- [x] `docs/poc/` set: 00-overview, 01-architecture, 05-retrieval-and-ranking, 08-data-model, 09-api-reference, 10-diagrams, 12-local-runtime, 16-responsible-use, 19-nlweb-ask-endpoint, 20-mcp-server, 21-security, STATUS.
- [x] `docs/adr/0000-template.md` + ADRs 0001, 0003, 0008, 0009, 0010, 0012, 0014, 0015, 0016, 0017.

## Decision log pointers
- Settled kickoff answers → [`CLAUDE.md`](../../CLAUDE.md) (§ "Settled at build start").
- ADRs → [`docs/adr/`](../adr/).
