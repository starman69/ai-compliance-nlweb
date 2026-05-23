# 0015 — NLWeb contract: `/ask` + `/mcp`, shared payload, `mode`

- **Status:** Accepted
- **Date:** 2026-05-23
- **Deciders:** Dave Patten
- **Related:** [19-nlweb-ask-endpoint](../poc/19-nlweb-ask-endpoint.md) · [20-mcp-server](../poc/20-mcp-server.md) · ADR-0016

## Context
The product is defined by the NLWeb pattern from the blog: every website should offer an
**`/ask`** endpoint for humans and an **`/mcp`** endpoint for agents, over the *same* answer
core. The prior app implemented this; we recreate it. The risk to avoid is two endpoints
drifting into two different behaviors.

## Decision
We will expose **one retrieval+answer core** through two thin adapters:

- **`POST /ask`** — humans/UI. Returns structured JSON shaped as a Schema.org `ItemList`
  (`sources[]`) plus `query_id, answer, mode, confidence, intent, scope, token_usage, model,
  elapsed_ms, retrieval`.
- **`GET|POST /mcp`** — agents. An MCP server (streamable HTTP, same FastAPI app; ADR-0016)
  exposing the same core as tools (`ask_compliance`, `list_frameworks`, `get_framework`) and
  prompts (e.g. `compare_jurisdictions`).

Both accept the **same request payload**; **`query` is the only required field**. Optional:
`prev[]` (multi-turn history), `decontextualized_query` (pre-condensed), `site` (scope →
jurisdiction filter), `mode`.

**`mode` gates LLM use:** `list` = retrieval only, **no LLM call**; `summarize` = one
citation-enforced synthesis pass (UI default); `generate` = a templated artifact. The two
endpoints **must not fork business logic** — they call the same service.

## Consequences
### Positive
- Humans and agents get identical semantics and the same security, scoping, and ledger.
- `mode=list` is cheap and deterministic (no model), good for the explorer and for tests.

### Negative / trade-offs
- The shared response must satisfy both a UI and tool-calling agents; we keep debug fields
  collapsible rather than splitting schemas.

### Follow-ups
- Unit tests: payload validation, `mode` gating (assert no LLM call on `list`), ItemList
  shaping — all against the shared core, then a thin per-endpoint adapter test.
- Guides `19-nlweb-ask-endpoint` and `20-mcp-server`.
