# 0012 — RAG-only scope (drop SQL / HITL / event-driven infra; keep Azure AI services + Bicep IaC)

- **Status:** Accepted
- **Date:** 2026-05-23
- **Deciders:** Dave Patten
- **Related:** ADR-0016 · ADR-0017

## Context
A full enterprise system in this space would carry a lot we don't need: SQL Server
reporting, a human-in-the-loop (HITL) review workflow with a 3-axis state machine and audit
triggers, Azure Functions / Event Grid, Easy Auth and role-based access, and Azure Blob
storage. AI Compliance NLWeb is a **retrieval-augmented Q&A
workbench** — none of that persistence/workflow/event-driven layer is needed. Note this is
about *persistence/event-driven* infra, **not** the Azure AI services and **not** the
deploy-time IaC: the `azure` runtime profile (ADR-0001) deliberately keeps **Azure OpenAI**
and **Azure AI Search** as managed backends, and ships **Bicep IaC** (`infra/bicep/`) to
provision them alongside Container Apps + a Static Web App — the cloud half of the dual
runtime, paired with the `local` Docker stack in `infra/compose/`.

The kickoff also settled a **lean env**: no unused SQL/blob keys.

## Decision
We will keep the project **RAG-only**. We drop, from the reused base:

- SQL Server, reporting, and `sql_builder.py`.
- HITL review, the 3-axis state machine, and audit triggers.
- Azure Functions, Event Grid (event-driven infra — the app is a single FastAPI service).
- Easy Auth / Azure roles (replaced by the lightweight token-scope model, ADR-0017).
- Azure Blob / Azurite.

**We keep** (for the `azure` profile, ADR-0001): **Azure OpenAI** (chat + embeddings),
**Azure AI Search** (vector store), and **Azure AI Document Intelligence** (prebuilt-layout
PDF/layout extraction at ingest — the cloud analogue of the local `unstructured.io` service),
all accessed via endpoint + `DefaultAzureCredential`. *(Document Intelligence was originally
dropped as "deployment infra"; it was re-added once the corpus's PDFs warranted real layout
extraction in the cloud profile — the layout backend is selected by `clients.layout_backend()`.)*
A **Bicep IaC** layer (`infra/bicep/`) provisions all three plus Container Apps (the FastAPI
service), a Static Web App (the React client), observability, and managed-identity RBAC. A
pure-parsing contract test (`tests/unit/test_bicep_app_contract.py`) keeps the Bicep,
the AI Search index schemas, and `clients.py` in sync.

The `.env` is **lean** — no `MSSQL_SA_PASSWORD` / `AZURITE_CONN_STRING`. Audit logging is a
**JSONL/SQLite** sink, not SQL Server.

## Consequences
### Positive
- Far smaller surface area, faster to build and reason about, cheaper to run locally.
- The env and compose stack only contain what RAG needs.

### Negative / trade-offs
- No durable persistence layer; if a future feature needs durable state beyond the audit
  log, it must be reintroduced deliberately.
- `clients.py` keeps only the factory functions RAG needs (no SQL/blob/DI).

### Follow-ups
- During the `src/shared/` port, strip SQL/HITL/blob/DI code paths; **keep** the Azure
  OpenAI + Azure AI Search factory branches.
- Audit sink (ADR-0017) implemented as JSONL/SQLite.
