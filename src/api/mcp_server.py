"""/mcp — Model Context Protocol over HTTP (JSON-RPC 2.0), sharing the same
NLWeb core as /ask. Exposes tools (`ask_compliance`, `list_frameworks`,
`get_framework`) and prompts (`compare_jurisdictions`) over the corpus.

This is a dependency-free JSON-RPC implementation of the MCP wire methods
(`initialize`, `tools/list`, `tools/call`, `prompts/list`, `prompts/get`) so the
contract runs offline. The official MCP Python SDK (streamable HTTP) can be
swapped in later without changing the core. Enforces the `mcp:invoke` scope.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from fastapi import Header, Request
from fastapi.responses import JSONResponse

from shared import corpus, security, service
from shared.models import AskRequest

# Latest finalized MCP spec revision (2026-07-28 is a release candidate, not stable).
PROTOCOL_VERSION = "2025-11-25"

_TOOLS = [
    {
        "name": "ask_compliance",
        "description": "Ask a grounded, cited question about the AI-compliance corpus.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The question (required)."},
                "site": {"type": "string", "description": "Comma-separated jurisdiction scope, e.g. 'eu,us-co'."},
                "mode": {"type": "string", "enum": ["list", "summarize", "generate"], "default": "summarize"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_frameworks",
        "description": "List the frameworks/documents in the corpus, grouped by tier.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_framework",
        "description": "Get manifest metadata for one framework by doc_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"doc_id": {"type": "string"}},
            "required": ["doc_id"],
        },
    },
]

_PROMPTS = [
    {
        "name": "compare_jurisdictions",
        "description": "Compare how two jurisdictions regulate a topic.",
        "arguments": [
            {"name": "topic", "description": "e.g. high-risk AI systems", "required": True},
            {"name": "a", "description": "First jurisdiction/framework", "required": True},
            {"name": "b", "description": "Second jurisdiction/framework", "required": True},
        ],
    }
]


def _text_result(payload: Any) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


def _call_tool(name: str, args: dict, principal_name: str) -> dict:
    if name == "ask_compliance":
        req = AskRequest(
            query=args["query"], site=args.get("site"), mode=args.get("mode", "summarize")
        )
        resp = service.ask(req, principal_name=principal_name)
        return _text_result(resp.model_dump())
    if name == "list_frameworks":
        return _text_result(corpus.grouped())
    if name == "get_framework":
        doc = corpus.doc_by_id(args.get("doc_id", ""))
        if not doc:
            raise KeyError(f"unknown doc_id {args.get('doc_id')!r}")
        return _text_result(doc)
    raise KeyError(f"unknown tool {name!r}")


def _handle(method: str, params: dict, principal_name: str) -> Any:
    if method == "initialize":
        # Per spec, respond with the client's requested version when we support it
        # (we're a thin JSON-RPC pass-through), else advertise our latest.
        version = params.get("protocolVersion") or PROTOCOL_VERSION
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {}, "prompts": {}},
            "serverInfo": {"name": "ai-compliance-nlweb", "version": "0.1.0"},
        }
    if method in ("notifications/initialized", "ping"):
        return {}
    if method == "tools/list":
        return {"tools": _TOOLS}
    if method == "tools/call":
        return _call_tool(params.get("name", ""), params.get("arguments", {}) or {}, principal_name)
    if method == "prompts/list":
        return {"prompts": _PROMPTS}
    if method == "prompts/get":
        topic = params.get("arguments", {}).get("topic", "the topic")
        a = params.get("arguments", {}).get("a", "A")
        b = params.get("arguments", {}).get("b", "B")
        return {
            "description": "Compare jurisdictions",
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": f"Compare how {a} and {b} regulate {topic}."},
                }
            ],
        }
    raise ValueError(f"method not found: {method}")


def register(app, authorize: Callable) -> None:
    @app.get("/mcp")
    def mcp_info() -> dict:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo": {"name": "ai-compliance-nlweb", "version": "0.1.0"},
            "transport": "http-jsonrpc",
            "tools": [{"name": t["name"], "description": t["description"]} for t in _TOOLS],
            "prompts": [{"name": p["name"], "description": p["description"]} for p in _PROMPTS],
        }

    @app.post("/mcp")
    async def mcp_rpc(request: Request, authorization: str | None = Header(default=None)) -> JSONResponse:
        principal = authorize(request, authorization, security.MCP_INVOKE)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
            )
        rpc_id = body.get("id")
        method = body.get("method", "")
        params = body.get("params", {}) or {}
        try:
            result = _handle(method, params, principal.name)
            return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result})
        except KeyError as exc:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32602, "message": str(exc)}}
            )
        except ValueError as exc:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": str(exc)}}
            )
        except Exception as exc:  # pragma: no cover - defensive
            return JSONResponse(
                {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32603, "message": str(exc)}}
            )
