# 21 — Security

> Both endpoints (`/ask`, `/ask/stream`, `/mcp`) enforce the same controls. Implementation:
> [`src/shared/security.py`](../../src/shared/security.py) + [`src/shared/audit.py`](../../src/shared/audit.py),
> wired in [`src/api/app.py`](../../src/api/app.py). Decision: [ADR-0017](../adr/0017-security-model.md).

## Token scopes
Bearer-token auth with two scopes, checked per request before the core runs:
- **`ask:read`** — `/ask` and `/ask/stream`;
- **`mcp:invoke`** — `/mcp`.

`AUTH_TOKENS` maps tokens → scopes. For solo local dev there's a **dev bearer-token fallback**
(`AUTH_DEV_TOKEN`, default `dev-local-token`) — a simple `X-Reviewer`-style shortcut so one user
needs no real token. With `AUTH_ENABLED=true` (the azure default) a valid token is required;
missing → 401, wrong scope → 403.

## Rate limiting
A per-`{principal}:{client-ip}` token-bucket limiter (`RATE_LIMIT_PER_MIN`, `RATE_LIMIT_BURST`);
over budget → 429. Cheap in-process; protects the model/vector backends.

## CORS
A **locked allow-list** (`CORS_ALLOW_ORIGINS`) — localhost dev origins locally, the Static Web
App origin on azure. Methods limited to `GET`/`POST`/`OPTIONS`.

## Audit logging
Every call writes one audit record (JSONL/SQLite sink, `audit.write`): `query_id`, principal,
intent, mode, scope, source `doc_id`s, confidence, model, token usage, latency, and the
decontextualized query. **Audit and the token ledger never break the answer path** — they
swallow their own errors and only log (correctness rule).

## Azure profile
No keys in app settings: the api authenticates to Azure OpenAI, AI Search, and Document
Intelligence via its **managed identity** (`DefaultAzureCredential`) with least-privilege RBAC
(Cognitive Services / Search Index Data roles), provisioned by Bicep
([`infra/bicep/`](../../infra/bicep/)).

## Out of scope (deliberately)
No Easy Auth / Azure roles for end users (replaced by the lightweight token-scope model),
no durable user store — this is a RAG workbench, not an identity provider
([ADR-0012](../adr/0012-rag-only-scope.md)).
