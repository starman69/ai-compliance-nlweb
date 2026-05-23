# Local stack (`infra/compose/`)

Docker Compose stack for AI Compliance NLWeb. Everything groups under the
**`compliance`** project.

## Quick start

```bash
cp .env.example .env            # tweak if needed
docker compose up -d            # qdrant, ollama, reranker, unstructured, api, web
docker compose run --rm bootstrap   # create Qdrant collections + pull Ollama models
# open the workbench:
open http://localhost:8088
```

| Service | Port | Role |
|---|---|---|
| `qdrant` | 6333 | vector store (`compliance_docs`, `compliance_chunks`, 1024-d dense+sparse) |
| `ollama` | 11434 | `qwen3:14b` answers + `mxbai-embed-large` embeddings (`local` profile) |
| `reranker` | 8081 | `bge-reranker-base` (TEI) — env toggle `RERANKER_ENABLED` |
| `unstructured` | 8002→8000 | PDF → structured text (ingestion) |
| `bootstrap` | — | one-shot: create collections + `ollama pull` |
| `api` | 8000 | FastAPI: `/ask` `/mcp` `/corpus` `/health` (src/ live-mounted) |
| `web` | 8088 | React NLWeb client (Vite dev) |

## Profiles

- **`RUNTIME_PROFILE=local`** (default) — runs entirely on this stack.
- **`RUNTIME_PROFILE=azure`** — set `NLWEB_BACKEND=real` + the Azure keys; the `api`
  container talks to **Azure OpenAI + Azure AI Search** (provision those separately,
  `DefaultAzureCredential`). Qdrant/Ollama go unused.

## Offline / no-model demo

`NLWEB_BACKEND=mock` runs the whole API with no model server (Mock retriever +
deterministic cited answers) — handy for UI work and CI. This is how the unit
tests and the screenshots run.

> First run pulls `qwen3:14b` (~9 GB) — give it time. Until then, use
> `NLWEB_BACKEND=mock`.
