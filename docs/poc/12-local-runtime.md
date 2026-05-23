# 12 — Local runtime & getting started

How to run AI Compliance NLWeb locally and (re)build the corpus.

## Prerequisites
- **Docker + Docker Compose** (the stack groups under the project name `compliance`).
- **NVIDIA GPU + Container Toolkit** — *optional but recommended*. The `ollama`
  service reserves the GPU; `qwen3:14b` is fast on an RTX-class card (~12 GB VRAM),
  slow on CPU. Comment out the `deploy.resources` block in the compose for CPU-only.
- **Python 3.11+** — for host-side `scripts/` (fetch, ingest) and `eval/` + tests.
- **Node 20+** — only if you run the web app outside Docker.

Two ways to run, depending on whether you want live models.

---

## Path A — Mock backend (instant, offline, no model server)

The fastest way to see the app, and how **tests/CI** run. Grounded, cited answers
come from the committed offline seed (`data/mock_chunks.yaml` + the ISO summaries) —
**no Ollama, Qdrant, fetch, or ingest required**.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

# tests (58; pinned to mock in tests/conftest.py)
python -m pytest

# API + web, Mock backend
NLWEB_BACKEND=mock PYTHONPATH=src uvicorn api.app:app --port 8000   # /ask /mcp /corpus /health /docs
cd src/web && npm install && npm run dev                            # http://localhost:8088
```

`NLWEB_BACKEND` defaults to `real`; set it to `mock` for the offline path.

---

## Path B — Full local stack (real qwen3:14b + Qdrant, GPU)

```bash
cd infra/compose
cp .env.example .env                       # tweak if needed

# 1. bring up the stack (qdrant, ollama, reranker, unstructured, api, web)
docker compose up -d

# 2. pull the models (first time; ~9 GB for qwen3:14b)
docker compose exec ollama ollama pull qwen3:14b
docker compose exec ollama ollama pull mxbai-embed-large

# 3. ingest the committed corpus -> embed -> Qdrant  (run from repo root, host venv)
#    sources/open/ ships in the repo — no fetch needed; EU OJ PDFs route through
#    the unstructured service (~1.5k chunks).
cd ../.. && . .venv/bin/activate
NLWEB_BACKEND=real RUNTIME_PROFILE=local PYTHONPATH=src python scripts/ingest.py

# 4. open the workbench
open http://localhost:8088

# (optional) refresh the corpus from official URLs, then re-ingest:
# NLWEB_BACKEND=real RUNTIME_PROFILE=local python scripts/fetch_corpus.py
```

`/health` shows the active profile/models and probes the dependencies; it reports
`degraded` if Qdrant/Ollama/reranker is down.

### Services & ports (compose project `compliance`)
| Service | Port | Role |
|---|---|---|
| `web` | 8088 | React NLWeb client |
| `api` | 8000 | FastAPI: `/ask` `/mcp` `/corpus` `/health` + **Swagger `/docs`** |
| `qdrant` | 6333 | vector store (1024-d dense + BM25 sparse) |
| `ollama` | 11434 | `qwen3:14b` answers + `mxbai-embed-large` embeddings (GPU) |
| `reranker` | 8081 | `bge-reranker-base` cross-encoder (TEI) |
| `unstructured` | 8002 | PDF → clean structured text (multi-column OJ PDFs) |

---

## Azure profile
Set `RUNTIME_PROFILE=azure` + `NLWEB_BACKEND=real` and the Azure keys in `.env`
(`OPENAI_ENDPOINT`, deployments, `SEARCH_*`; auth via `DefaultAzureCredential`).
Answers use Azure OpenAI `gpt-4.1` + `text-embedding-3-small` into Azure AI Search.
Qdrant/Ollama are unused on this profile.

## Refresh / re-ingest
Re-run `scripts/fetch_corpus.py` (idempotent; changed checksums in
`sources/_index.json` flag re-ingest) then `scripts/ingest.py` (recreates the
chunks collection). Useful flags: `fetch_corpus.py --summaries-only` (no network),
`--only <id> …`, `--dry-run`.

## Evaluation
```bash
python eval/run_eval.py          # retrieval hit-rate + term coverage + intent -> docs/poc/eval-baselines/
```

## Sources & reproducibility (for new developers)
- `sources/open/` **is committed** (~40 MB) — a fresh clone has the **full corpus**, so
  Path B step 3 (ingest) works immediately, no fetch required. Only `sources/manual/` (your
  own licensed PDFs) is gitignored. `sources/_index.json` (fetch provenance) is tracked;
  refresh from official URLs with `fetch_corpus.py`.
- The **offline seed** (`data/mock_chunks.yaml`) and the **ISO summaries**
  (`manifest/summaries/*.md`) are also committed, so a fresh clone runs immediately on
  the Mock backend with grounded, cited answers — no fetch/ingest needed.
- Sources whose live pages are JS-viewers or bot-blocked (UNESCO, CoE, Singapore, ENISA,
  MS Responsible AI, Google SAIF, …) are committed as **open, non-normative authored
  summaries** (each footed as such), so **every manifest doc is backed** and the corpus is
  fully reproducible. See the manifest `notes` and [STATUS.md](STATUS.md).

## Endpoints
- `POST /ask` — humans/UI (Schema.org `ItemList` JSON)
- `GET|POST /mcp` — agents (MCP JSON-RPC: `ask_compliance`, `list_frameworks`, `get_framework`)
- `GET /corpus` — explorer manifest · `GET /health` — ops · **`GET /docs`** — Swagger UI
