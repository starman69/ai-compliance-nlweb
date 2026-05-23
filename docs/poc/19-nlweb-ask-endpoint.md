# 19 — `/ask` (NLWeb HTTP endpoint)

> The request/response models live in
> [`src/shared/models.py`](../../src/shared/models.py); the core is
> [`src/shared/service.py`](../../src/shared/service.py). `/ask` and
> [`/mcp`](20-mcp-server.md) are thin adapters over the **same** `service.ask` — logic
> never forks between them.

`/ask` is the human/UI contract. It follows the NLWeb pattern: one natural-language
`query` in, a grounded + cited answer out, with retrieval results projected as a
Schema.org `ItemList`.

## Request
`POST /ask` · `Content-Type: application/json` · `Authorization: Bearer <token>` (scope
`ask:read`, ADR-0017). The payload is **identical** to `/mcp`'s `ask_compliance` args.

| Field | Type | Req | Meaning |
|---|---|---|---|
| `query` | string | ✓ | The natural-language question. |
| `prev` | `[{role, content}]` | | Prior turns — enables history-aware condensation (ADR-0010). |
| `decontextualized_query` | string | | Pre-condensed standalone query; skips server-side condensation. |
| `site` | string | | Comma-separated jurisdiction scope tokens, e.g. `eu,us-co`. Empty = whole corpus. |
| `mode` | `list \| summarize \| generate` | | LLM gate (default `summarize`). `list` = retrieval only (no LLM); `summarize` = grounded synthesis; `generate` = longer comparative answer. |

```bash
curl -s localhost:8000/ask -H 'Authorization: Bearer dev-ask' \
  -H 'Content-Type: application/json' \
  -d '{"query":"What are the obligations for high-risk AI systems?","site":"eu","mode":"summarize"}'
```

## Response (`AskResponse`)
Our native envelope **plus** the additive Schema.org projection:

| Field | Meaning |
|---|---|
| `query_id` | Audit/correlation id. |
| `answer` | Grounded, citation-bearing answer (markdown). Empty `list` mode → falls back to sources. |
| `mode` | Echoes the resolved mode. |
| `confidence` | `high \| medium \| low` (scale-aware; cosine vs token-overlap). |
| `intent` | `implementation \| comparison \| scoping \| lookup \| out_of_scope`. |
| `decontextualized_query` | Present when a follow-up was condensed (so the UI can show "↳ interpreted as"). |
| `sources` | Native array — `position, doc_id, title, short_name, section_path, page, url, quote, score`. |
| `item_list` | **Schema.org `ItemList`** projection of `sources` (see below). |
| `scope` | Resolved `{jurisdictions: [...]}`. |
| `token_usage`, `model`, `elapsed_ms`, `retrieval` | Cost/telemetry + retrieval debug (`candidates, reranked, fusion`). |

### NLWeb / Schema.org conformance — `item_list`
NLWeb shapes retrieval results as a Schema.org `ItemList`. We keep `sources` for the UI and
emit `item_list` as a parallel, standards-conformant JSON-LD view (always present, empty when
there are no sources). Each cited excerpt is a `ListItem` → `CreativeWork`:

```json
{
  "@context": "https://schema.org",
  "@type": "ItemList",
  "numberOfItems": 1,
  "itemListElement": [
    {
      "@type": "ListItem",
      "position": 1,
      "item": {
        "@type": "CreativeWork",
        "name": "EU AI Act — Art. 6",
        "headline": "Regulation (EU) 2024/1689 (AI Act)",
        "identifier": "eu-ai-act",
        "url": "https://eur-lex.europa.eu/...",
        "text": "High-risk AI systems shall…"
      }
    }
  ]
}
```

`position` matches the inline citation markers in `answer`, so a client can resolve `[1]` →
`item_list.itemListElement[0]` (or the parallel `sources[0]`).

## Why two views
`sources` is ergonomic for the React client (flat, typed, scored). `item_list` is the
interoperable contract for NLWeb-aware consumers. Both derive from the same retrieval result,
so they can never disagree — `item_list` is a computed projection of `sources`.

See the live shapes at `/docs` (Swagger) · `/openapi.json`.

## Streaming — `POST /ask/stream` (SSE)
For token-by-token UIs, `/ask/stream` runs the **same core** (`service.ask_stream`) and emits
**Server-Sent Events** (`text/event-stream`). Same `ask:read` scope + payload as `/ask`.
The non-streaming `/ask` JSON contract is unchanged; this is an additive, parallel endpoint.

Event sequence:

| Event | Payload | When |
|---|---|---|
| `sources` | the `sources[]` array | once, up front — render citations before the answer arrives |
| `delta` | `{"text": "…"}` | repeatedly — answer fragments (none in `list` mode) |
| `done` | the **full `AskResponse`** (answer, `sources`, `item_list`, confidence, `token_usage`, …) | once, last |

The concatenation of all `delta.text` equals `done.answer`, and `done` is byte-for-byte what
`POST /ask` would have returned — so a client can stream for UX *and* keep the authoritative
object. Token usage stays accurate: the answer model is called with
`stream_options.include_usage`, so `done.token_usage` carries real prompt/completion counts.

```bash
curl -N localhost:8000/ask/stream -H 'Authorization: Bearer dev-local-token' \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is the EU AI Act?","mode":"summarize"}'
# event: sources\n data: [...]
# event: delta\n   data: {"text":"The EU "}
# event: delta\n   data: {"text":"AI Act ..."}
# event: done\n    data: {"query_id":...,"answer":...,"item_list":{...},"token_usage":{...}}
```
