# 0016 — FastAPI (Python) over the blog's Express

- **Status:** Accepted
- **Date:** 2026-05-23
- **Deciders:** Dave Patten
- **Related:** ADR-0015 · ADR-0001

## Context
The Medium write-up implemented the NLWeb endpoints in **Express (Node)**. The core we want,
though, is most naturally a **Python** stack: a token ledger, a `vector_search` abstraction
(Qdrant + Azure AI Search), a `clients.py` profile factory, `embedding_text`, `router`,
`prompts`, `pricing`, and `config`. Building this in Python keeps one language across
ingestion, API, and eval, and lets the MCP server share the app.

## Decision
We will build the API in **FastAPI (Python 3.11)**, not Express. The shared modules live
under `src/shared/`, and the MCP server (built with the **MCP Python SDK**, streamable HTTP)
mounts on the **same FastAPI app** (ADR-0015), so `/ask` and `/mcp` share one process and one
core.

## Consequences
### Positive
- Direct reuse of the token ledger, vector-search/hybrid, router, and pricing code.
- One language across ingestion, API, and eval; one dependency story.
- MCP and `/ask` share the FastAPI app — no second server to run for agent testing.

### Negative / trade-offs
- Diverges from the blog's stack, so the write-up's Express snippets are illustrative, not
  literal. We document the mapping in `19`/`20`.
- Python async + the MCP SDK streamable-HTTP mounting needs care to coexist with FastAPI
  routes.

### Follow-ups
- Port `src/shared/` (trimming SQL/HITL/Azure per ADR-0012).
- Verify MCP SDK streamable-HTTP mounts cleanly on FastAPI; document in `20-mcp-server`.
