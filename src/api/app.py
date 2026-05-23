"""FastAPI app — the NLWeb core exposed two ways: /ask (humans/UI) and /mcp
(agents), plus /corpus (explorer) and /health (ops). Both /ask and /mcp enforce
token scopes + rate limiting + CORS (ADR 0017) and call the same `service.ask`.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from shared import clients, corpus, profile, security, service
from shared.models import AskRequest, AskResponse

from . import mcp_server

app = FastAPI(title="AI Compliance NLWeb", version="0.1.0")

_origins = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:8088,http://localhost:5173,http://127.0.0.1:8088,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

_limiter = security.RateLimiter(
    rate_per_min=int(os.environ.get("RATE_LIMIT_PER_MIN", "120")),
    burst=int(os.environ.get("RATE_LIMIT_BURST", "60")),
)


def authorize(request: Request, authorization: str | None, required_scope: str) -> security.Principal:
    """Resolve principal, enforce scope + rate limit. Raises HTTPException."""
    try:
        principal = security.principal_for(authorization)
    except security.AuthError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    if not principal.has(required_scope):
        raise HTTPException(status_code=403, detail=f"missing scope {required_scope}")
    client_host = request.client.host if request.client else "?"
    if not _limiter.allow(f"{principal.name}:{client_host}"):
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    return principal


def _probe(url: str, timeout: float = 2.0) -> bool:
    import httpx

    try:
        return httpx.get(url, timeout=timeout).status_code < 500
    except Exception:
        return False


@app.get("/health")
def health() -> dict:
    """Liveness + readiness: reports the active profile/models and probes the
    backing services so ops can see a degraded dependency. Never raises."""
    info = {
        "status": "ok",
        "profile": profile.get_profile().value,
        "backend": clients.backend(),
        "answer_model": clients.answer_model(),
        "embed_model": clients.embed_model(),
        "reranker": clients.reranker_model() if clients.reranker_enabled() else None,
    }
    deps: dict[str, bool] = {}
    if clients.backend() == "real":
        if profile.is_azure():
            deps["azure_openai"] = bool(os.environ.get("OPENAI_ENDPOINT"))
            deps["azure_search"] = bool(os.environ.get("SEARCH_SERVICE_ENDPOINT"))
        else:
            qdrant = os.environ.get("QDRANT_URL", "http://localhost:6333").rstrip("/")
            ollama = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1").replace("/v1", "").rstrip("/")
            deps["qdrant"] = _probe(f"{qdrant}/readyz")
            deps["ollama"] = _probe(f"{ollama}/api/tags")
            if clients.reranker_enabled():
                deps["reranker"] = _probe(
                    os.environ.get("RERANKER_URL", "http://localhost:8081").rstrip("/") + "/health"
                )
    info["dependencies"] = deps
    if deps and not all(deps.values()):
        info["status"] = "degraded"
    return info


@app.get("/corpus")
def get_corpus() -> dict:
    return corpus.grouped()


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request, authorization: str | None = Header(default=None)) -> AskResponse:
    principal = authorize(request, authorization, security.ASK_READ)
    return service.ask(req, principal_name=principal.name)


@app.post(
    "/ask/stream",
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE event stream"}},
)
def ask_stream(
    req: AskRequest, request: Request, authorization: str | None = Header(default=None)
) -> StreamingResponse:
    """Same NLWeb core as `/ask`, streamed as Server-Sent Events for token-by-token
    UIs. Event sequence: `sources` (citations up front) → `delta` (answer text) →
    `done` (the full AskResponse JSON, incl. `item_list` + `token_usage`). The
    `done` payload equals what `POST /ask` returns. Same `ask:read` scope."""
    principal = authorize(request, authorization, security.ASK_READ)
    return StreamingResponse(
        service.ask_stream(req, principal_name=principal.name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy/nginx buffering for SSE
        },
    )


# Mount /mcp (JSON-RPC over HTTP) on the same app, sharing the core + auth.
mcp_server.register(app, authorize)
