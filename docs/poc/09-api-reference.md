# 09 — API reference

> The live, always-current reference is **Swagger** at `/docs` (· `/redoc` · `/openapi.json`),
> generated from the FastAPI models so it never drifts. This page is the at-a-glance map.
> Deep dives: [`19-nlweb-ask-endpoint`](19-nlweb-ask-endpoint.md),
> [`20-mcp-server`](20-mcp-server.md). Security: [`21-security`](21-security.md).

## Endpoints
| Method | Path | Scope | Purpose |
|---|---|---|---|
| `POST` | `/ask` | `ask:read` | Grounded, cited answer as JSON (`AskResponse`: `answer`, `sources[]`, `item_list`, confidence, intent, scope, `token_usage`, …). |
| `POST` | `/ask/stream` | `ask:read` | Same core, streamed as SSE: `sources` → `delta` → `done` (full `AskResponse`). |
| `GET` / `POST` | `/mcp` | `mcp:invoke` | MCP server. `GET` = discovery (tools/prompts + descriptions); `POST` = JSON-RPC (`initialize`, `tools/list`, `tools/call`, `prompts/list`, `prompts/get`). |
| `GET` | `/corpus` | — | The corpus grouped by tier (powers the explorer). |
| `GET` | `/health` | — | Liveness/readiness: active profile, models, dependency probes (→ `degraded`). |

## Shared request payload (`/ask`, `/ask/stream`, and `/mcp`'s `ask_compliance`)
`query` (required) · `prev[]` (multi-turn) · `decontextualized_query` · `site` (jurisdiction
scope) · `mode` (`list | summarize | generate`). One core serves all three —
[logic never forks](01-architecture.md).

## Auth
Bearer token; scopes `ask:read` / `mcp:invoke`; a dev bearer-token fallback for local dev.
Both endpoints enforce scopes + per-token/IP rate limiting + a locked CORS allow-list + audit
logging — see [`21-security`](21-security.md) and [ADR-0017](../adr/0017-security-model.md).
