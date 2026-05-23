# Azure infrastructure (`azure` runtime profile)

Bicep IaC for the **`azure`** half of the dual runtime (ADR 0001). The **`local`**
half is the Docker stack in [`infra/compose/`](../compose/) — same application,
two runtimes selected by `RUNTIME_PROFILE`.

## What it deploys
| Module | Resource | Role |
|---|---|---|
| `openAi.bicep` | Azure OpenAI | `gpt-4.1` (answers) + `text-embedding-3-small` (1536-d embeddings) |
| `aiSearch.bicep` | Azure AI Search (basic, semantic) | `compliance-docs-index` + `compliance-chunks-index` (hybrid + semantic ranker) |
| `containerApps.bicep` | Container Apps env + **api** | FastAPI `/ask` `/mcp` `/corpus` `/health` `/docs`; system MI; azure env settings |
| `staticWebApp.bicep` | Static Web App | the React NLWeb client |
| `observability.bicep` | Log Analytics + App Insights | logs/metrics |
| `roleAssignments.bicep` | RBAC | api MI → Cognitive Services OpenAI User + Search Index Data Contributor/Service Contributor |

No keys in app settings — the api authenticates to Azure OpenAI + AI Search via its
**managed identity** (`DefaultAzureCredential`).

## Prerequisites
- Azure CLI + Bicep (`az bicep install`), an Azure subscription.
- A region with `gpt-4.1` + `text-embedding-3-small` capacity (e.g. `eastus2`).
- An **ACR** (or registry) with the api image built from
  [`infra/compose/Dockerfile.api`](../compose/Dockerfile.api) — set `apiImage` in
  `env/dev.bicepparam`.

## Deploy
```bash
az login
RG=compliance-rg LOCATION=eastus2 ./infra/bicep/deploy.sh
```
Then create the two AI Search indexes from `scripts/aisearch/*.json` and run
`scripts/ingest.py` with `RUNTIME_PROFILE=azure NLWEB_BACKEND=real` (see the
deploy.sh footer + [`12-local-runtime.md`](../../docs/poc/12-local-runtime.md)).

## Contract test
[`tests/unit/test_bicep_app_contract.py`](../../tests/unit/test_bicep_app_contract.py)
asserts (pure parsing, no Azure) that the OpenAI deployment names, the AI Search
index names, the embedding dimension (1536), and the api container app's env vars
stay in sync across Bicep, the index JSON schemas, and `src/shared/clients.py`.
