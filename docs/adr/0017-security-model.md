# 0017 — Security model: token scopes, rate limiting, CORS, audit logging

- **Status:** Accepted
- **Date:** 2026-05-23
- **Deciders:** Dave Patten
- **Related:** [21-security](../poc/21-security.md) · ADR-0012 · ADR-0015

## Context
The blog explicitly calls for securing both endpoints — "token scopes, rate limiting, and
audit logging of both endpoints." Because `/ask` and `/mcp` expose the same core (ADR-0015),
security must be enforced uniformly at the edge, not per-endpoint. We dropped Azure Easy
Auth/roles (ADR-0012), so we need a lightweight, local-friendly model. The system is
single-user locally but should demonstrate a real authorization story.

## Decision
We will enforce, on **both `/ask` and `/mcp`**:

- **Token scopes** — bearer tokens carrying scopes (**`ask:read`**, **`mcp:invoke`**); each
  endpoint checks the required scope. A **dev bearer-token fallback** (a simple
  `X-Reviewer`-style shortcut) lets single-user local dev work with no real token.
- **Rate limiting** — per-token / per-IP limits on both endpoints.
- **CORS** — a locked allow-list for the web origin only.
- **Audit logging** — every call logged (`query_id`, principal/scope, intent, sources, token
  usage, latency) to a **JSONL/SQLite** sink (no SQL Server; ADR-0012), reusing Contract
  Intelligence's `QueryAudit` discipline.

**The audit log and token ledger must never break the answer path** — they swallow their own
errors and log, never raise into the response.

## Consequences
### Positive
- Uniform enforcement across both contracts; agents and humans share the same gate.
- Local dev stays frictionless via the dev token fallback.
- Auditable trail for every query without heavyweight infrastructure.

### Negative / trade-offs
- A real multi-tenant token-issuance system is out of scope; the scope model is
  demonstrative, not a full IdP integration.
- JSONL/SQLite audit is fine for a POC but not a high-volume production sink.

### Follow-ups
- Unit tests for scope checks (deny missing/incorrect scope) and a "ledger/audit failure
  doesn't break the answer" test.
- `21-security` documents the threat model and config (`CORS_ALLOW_ORIGINS`, token format,
  rate-limit knobs).
