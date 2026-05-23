# 20 — `/mcp` (Model Context Protocol server)

> Implementation:
> [`src/api/mcp_server.py`](../../src/api/mcp_server.py). Shares the **same** `service.ask`
> core as [`/ask`](19-nlweb-ask-endpoint.md) — agents and humans hit identical logic.

`/mcp` is the agent contract: a dependency-free **JSON-RPC 2.0 over HTTP** implementation of
the MCP wire methods, mounted on the same FastAPI app. The official MCP Python SDK
(streamable HTTP) can be swapped in later without touching the core. Enforces the
`mcp:invoke` scope (ADR-0017).

**Protocol version:** `2025-11-25` (latest finalized MCP revision). On `initialize` we echo
the client's requested `protocolVersion` when present, else advertise ours.

## Discovery — `GET /mcp`
Unauthenticated metadata for humans/tools browsing the server. Lists tools **and prompts with
their descriptions** (not just names):

```json
{
  "protocolVersion": "2025-11-25",
  "serverInfo": {"name": "ai-compliance-nlweb", "version": "0.1.0"},
  "transport": "http-jsonrpc",
  "tools": [
    {"name": "ask_compliance", "description": "Ask a grounded, cited question about the AI-compliance corpus."},
    {"name": "list_frameworks", "description": "List the frameworks/documents in the corpus, grouped by tier."},
    {"name": "get_framework", "description": "Get manifest metadata for one framework by doc_id."}
  ],
  "prompts": [
    {"name": "compare_jurisdictions", "description": "Compare how two jurisdictions regulate a topic."}
  ]
}
```

## JSON-RPC — `POST /mcp`
`Authorization: Bearer <token>` (scope `mcp:invoke`). Standard envelope: requests carry
`{jsonrpc:"2.0", id, method, params}`; responses return `result` or a JSON-RPC `error`
(`-32700` parse, `-32601` method not found, `-32602` invalid params, `-32603` internal).

### Methods
| Method | Result |
|---|---|
| `initialize` | `{protocolVersion, capabilities:{tools,prompts}, serverInfo}` (echoes client version). |
| `notifications/initialized`, `ping` | `{}` |
| `tools/list` | `{tools: [...]}` — full tool objects incl. `description` + `inputSchema`. |
| `tools/call` | Invokes a tool; returns `{content:[{type:"text", text:"<json>"}]}`. |
| `prompts/list` | `{prompts: [...]}` with `arguments`. |
| `prompts/get` | `{description, messages:[...]}` rendered from `arguments`. |

### Tools
- **`ask_compliance`** — `{query (req), site?, mode?}`. Builds an `AskRequest` and returns the
  full `AskResponse` (incl. `sources` **and** the Schema.org `item_list`, see
  [19](19-nlweb-ask-endpoint.md)) JSON-encoded as MCP text content.
- **`list_frameworks`** — the corpus grouped by tier.
- **`get_framework`** — `{doc_id (req)}` → manifest metadata; unknown id → `-32602`.

### Example — `tools/call`
```bash
curl -s localhost:8000/mcp -H 'Authorization: Bearer dev-mcp' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
        "name":"ask_compliance",
        "arguments":{"query":"high-risk obligations","site":"eu","mode":"summarize"}}}'
```
```json
{"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"{\"query_id\":...,\"answer\":...,\"sources\":[...],\"item_list\":{...}}"}]}}
```

The `text` payload is the same `AskResponse` JSON `/ask` returns — one core, two contracts.
