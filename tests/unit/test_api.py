import json

from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)


def _parse_sse(text: str) -> list[tuple[str, object]]:
    """Parse an SSE body into [(event, data), ...] (data JSON-decoded)."""
    events: list[tuple[str, object]] = []
    for frame in text.strip().split("\n\n"):
        ev, data = None, None
        for line in frame.splitlines():
            if line.startswith("event:"):
                ev = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
        if ev is not None:
            events.append((ev, data))
    return events


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["backend"] == "mock"


def test_corpus():
    r = client.get("/corpus")
    assert r.status_code == 200
    assert r.json()["stats"]["documents"] == 48


def test_ask_ok():
    r = client.post("/ask", json={"query": "What is the EU AI Act?"})
    assert r.status_code == 200
    body = r.json()
    assert body["query_id"].startswith("q_")
    assert body["sources"]
    assert body["intent"] in {"lookup", "scoping", "implementation", "comparison"}


def test_ask_validation_error_on_empty_query():
    r = client.post("/ask", json={"query": ""})
    assert r.status_code == 422


def test_mcp_tools_list():
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 200
    names = [t["name"] for t in r.json()["result"]["tools"]]
    assert "ask_compliance" in names


def test_mcp_tools_call_ask_compliance():
    r = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "ask_compliance", "arguments": {"query": "What is the EU AI Act?", "mode": "list"}},
        },
    )
    assert r.status_code == 200
    assert "content" in r.json()["result"]


def test_ask_stream_summarize_sse_sequence():
    r = client.post("/ask/stream", json={"query": "What is the EU AI Act?", "mode": "summarize"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(r.text)
    kinds = [e for e, _ in events]
    # sources first, deltas in the middle, done last
    assert kinds[0] == "sources"
    assert kinds[-1] == "done"
    assert kinds.count("done") == 1
    deltas = [d["text"] for e, d in events if e == "delta"]
    assert deltas, "summarize mode should stream answer deltas"
    done = next(d for e, d in events if e == "done")
    # deltas concatenate to the final answer (parity with non-streaming)
    assert "".join(deltas) == done["answer"]
    # done carries the full AskResponse contract
    assert done["sources"]
    assert done["item_list"]["@type"] == "ItemList"
    assert "token_usage" in done and "completion_tokens" in done["token_usage"]


def test_ask_stream_list_mode_no_deltas():
    r = client.post("/ask/stream", json={"query": "What is the EU AI Act?", "mode": "list"})
    assert r.status_code == 200
    events = _parse_sse(r.text)
    kinds = [e for e, _ in events]
    assert kinds[0] == "sources" and kinds[-1] == "done"
    assert "delta" not in kinds, "list mode must not invoke the LLM"
    done = next(d for e, d in events if e == "done")
    assert done["model"] == "none"
    assert done["sources"]


def test_ask_stream_requires_scope_when_auth_enabled(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_TOKENS", "")
    r = client.post("/ask/stream", json={"query": "hi"})
    assert r.status_code == 401


def test_auth_enforced_when_enabled(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_TOKENS", "")
    r = client.post("/ask", json={"query": "hi"})
    assert r.status_code == 401
