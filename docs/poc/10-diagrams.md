# 10 — Diagrams

> The canonical Mermaid diagram set. The working mental
> model + prose is in [`01-architecture`](01-architecture.md); endpoint contracts in
> [`19`](19-nlweb-ask-endpoint.md)/[`20`](20-mcp-server.md). These recreate (and supersede)
> the prior `blog-architecture.png` lineage image as living, version-controlled diagrams.

Live API reference: **`/docs`** (Swagger UI) · **`/redoc`** · **`/openapi.json`** — generated
from the FastAPI models, so it never drifts from the code.

---

## 1. NLWeb — one core, two contracts
The whole system is a single retrieval+answer core, exposed two ways. Logic never forks
between `/ask` and `/mcp`; they are thin adapters.

```mermaid
flowchart LR
    human([Human / UI]) -->|POST /ask| ask["/ask<br/>(JSON: sources + item_list)"]
    agent([AI agent / MCP client]) -->|JSON-RPC POST /mcp| mcp["/mcp<br/>(tools · prompts)"]
    ask --> core
    mcp --> core
    subgraph core_box[Shared NLWeb core — service.ask]
      core["router → condense → retrieve → rerank → mode → shape"]
    end
    core --> resp["AskResponse<br/>answer · sources · item_list (Schema.org)<br/>confidence · intent · token_usage"]
```

## 2. Container view (recreates `blog-architecture.png`)
The orchestrator seam: the `vector_search` abstraction is chosen by the `clients.py` factory,
so the same core runs over **Qdrant** (local), **Azure AI Search** (azure), or a **Mock**
(tests / offline UI) — without business logic knowing which.

```mermaid
flowchart TB
    web["Web UI<br/>React + Vite + TS"] --> client["NLWeb client<br/>fetch + mcpClient.ts"]
    client -->|/ask · /mcp · /corpus| api["FastAPI app<br/>app.py · mcp_server.py"]
    api --> sec["Security<br/>scopes · rate-limit · CORS"]
    api --> svc["service.ask<br/>router · condense · mode engine"]
    svc --> orch{{"vector_search<br/>abstraction"}}
    orch --> qdrant[("Qdrant impl<br/>dense + sparse · RRF")]
    orch --> azsearch[("Azure AI Search impl<br/>vector + semantic")]
    orch --> mock[("Mock impl<br/>curated seed")]
    svc --> llm["clients.py factory<br/>Ollama qwen3:14b / Azure gpt-4.1"]
    svc --> rerank["Reranker<br/>bge-reranker-base / AI Search semantic"]
    llm --> ledger["Token ledger"]
    api --> audit[("Audit log<br/>JSONL/SQLite")]
```

## 3. `/ask` request flow (sequence)

```mermaid
sequenceDiagram
    participant C as Client (UI / agent)
    participant A as API (auth + scopes)
    participant S as service.ask
    participant V as vector_search
    participant R as Reranker
    participant L as Answer model
    C->>A: POST /ask {query, prev?, site?, mode}
    A->>A: authorize (ask:read / mcp:invoke) + rate-limit
    A->>S: AskRequest
    S->>S: route intent + condense multi-turn (prev → decontextualized_query)
    S->>V: hybrid retrieve (dense+sparse RRF, site filter)
    V-->>S: ~32 candidates
    S->>R: rerank candidates
    R-->>S: top-k reranked
    alt mode = list
        S-->>A: sources only (no LLM)
    else summarize / generate
        S->>L: citation-enforced synthesis
        L-->>S: grounded answer + token usage
    end
    S->>S: shape sources + item_list + confidence, then audit + ledger
    S-->>A: AskResponse
    A-->>C: 200 JSON
```

## 4. Retrieval & ranking pipeline

```mermaid
flowchart LR
    q["query<br/>(decontextualized)"] --> dense["Dense<br/>mxbai 1024-d / 3-small 1536-d"]
    q --> sparse["Sparse<br/>BM25 (fastembed)"]
    filter["site / explorer scope<br/>→ jurisdiction filter"] --> dense
    filter --> sparse
    dense --> rrf["RRF fusion<br/>(Query API prefetch)"]
    sparse --> rrf
    rrf --> cand["~32 candidates"]
    cand --> ce["Cross-encoder rerank<br/>bge-reranker-base (TEI)"]
    ce --> topk["top-k cited sources<br/>score = rerank score"]
```

## 5. Dual runtime profiles
`RUNTIME_PROFILE` selects a matched {vector store, embedder, answer model} triple. Stores are
**separate** because embedding dimension is immutable once written — never embed one store
with the other's model.

```mermaid
flowchart TB
    subgraph local["RUNTIME_PROFILE=local — Docker (infra/compose/)"]
      lq[("Qdrant<br/>1024-d")] --- le["Ollama<br/>mxbai-embed-large"] --- la["Ollama<br/>qwen3:14b"] --- lr["TEI<br/>bge-reranker-base"]
    end
    subgraph azure["RUNTIME_PROFILE=azure — Bicep (infra/bicep/)"]
      aq[("Azure AI Search<br/>1536-d")] --- ae["Azure OpenAI<br/>text-embedding-3-small"] --- aa["Azure OpenAI<br/>gpt-4.1 (prompt cache)"] --- ar["AI Search<br/>semantic ranker"]
    end
    app["Same app code<br/>(clients.py factory branches)"] --> local
    app --> azure
```

## 6. Ingestion pipeline

```mermaid
flowchart LR
    man["manifest/corpus.yaml<br/>(48 open docs + ISO summaries)"] --> fetch["fetch_corpus.py<br/>PDF / HTML→MD / EUR-Lex OJ"]
    fetch --> src["sources/open/"]
    src --> chunk["chunking.py<br/>structure-aware (200 words)<br/>pypdf · unstructured (garble-gate)"]
    chunk --> embed["embed (batched, 900-char cap)<br/>mxbai 1024-d / 3-small 1536-d"]
    embed --> upsert["upsert (batched @128)"]
    upsert --> store[("compliance_docs<br/>compliance_chunks")]
```

## 7. Deployment topology

```mermaid
flowchart TB
    subgraph dev["local — one host, project 'compliance'"]
      d1["docker compose up"] --> d2["qdrant · ollama (GPU) · reranker · unstructured · api · web"]
    end
    subgraph cloud["azure — Bicep (infra/bicep/)"]
      c1["Container Apps env"] --> capi["api (FastAPI, system MI)"]
      cswa["Static Web App (React)"] --> capi
      capi -->|DefaultAzureCredential| caoai["Azure OpenAI"]
      capi -->|MI RBAC| casearch["Azure AI Search"]
      capi --> cobs["Log Analytics + App Insights"]
    end
```

See [`infra/bicep/README.md`](../../infra/bicep/README.md) for the cloud half and
[`12-local-runtime`](12-local-runtime.md) for the local half.
