"""Token scopes + rate limiting for /ask and /mcp (ADR 0017).

Pure logic (parse principal, scope check, rate-limit bucket) is unit-testable
without FastAPI; a thin dependency wrapper lives in `require_scope`.

Scopes: `ask:read` (POST /ask), `mcp:invoke` (/mcp). Local dev uses a dev
bearer-token fallback so a single user needs no real token: when AUTH_ENABLED
is false (default), every request is the `dev` principal with all scopes; when
true, a Bearer token must match AUTH_TOKENS or the AUTH_DEV_TOKEN value.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

ASK_READ = "ask:read"
MCP_INVOKE = "mcp:invoke"
ALL_SCOPES = frozenset({ASK_READ, MCP_INVOKE})


@dataclass(frozen=True)
class Principal:
    name: str
    scopes: frozenset[str]

    def has(self, scope: str) -> bool:
        return scope in self.scopes


def _auth_enabled() -> bool:
    return (os.environ.get("AUTH_ENABLED") or "false").lower() in {"1", "true", "yes"}


def _dev_token() -> str:
    return os.environ.get("AUTH_DEV_TOKEN") or "dev-local-token"


def _token_table() -> dict[str, frozenset[str]]:
    """Parse AUTH_TOKENS = 'tok1:ask:read,mcp:invoke;tok2:ask:read'."""
    raw = os.environ.get("AUTH_TOKENS", "")
    table: dict[str, frozenset[str]] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        tok, _, scopes = entry.partition(":")
        table[tok.strip()] = frozenset(s.strip() for s in scopes.split(",") if s.strip())
    return table


def parse_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip() or None


class AuthError(Exception):
    """Raised on missing/invalid token. status: 401 missing, 403 wrong scope."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def principal_for(authorization: str | None) -> Principal:
    """Resolve the caller's principal. Dev fallback when auth disabled."""
    token = parse_bearer(authorization)
    if not _auth_enabled():
        return Principal(name="dev", scopes=ALL_SCOPES)
    if not token:
        raise AuthError(401, "missing bearer token")
    if token == _dev_token():
        return Principal(name="dev", scopes=ALL_SCOPES)
    scopes = _token_table().get(token)
    if scopes is None:
        raise AuthError(401, "invalid token")
    return Principal(name=f"token:{token[:6]}…", scopes=scopes)


# --- rate limiting: simple per-key token bucket ----------------------------
@dataclass
class _Bucket:
    tokens: float
    updated: float


@dataclass
class RateLimiter:
    rate_per_min: int = 60
    burst: int = 30
    _buckets: dict[str, _Bucket] = field(default_factory=dict)

    def allow(self, key: str, *, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        per_sec = self.rate_per_min / 60.0
        b = self._buckets.get(key)
        if b is None:
            self._buckets[key] = _Bucket(tokens=self.burst - 1, updated=now)
            return True
        elapsed = max(0.0, now - b.updated)
        b.tokens = min(float(self.burst), b.tokens + elapsed * per_sec)
        b.updated = now
        if b.tokens >= 1.0:
            b.tokens -= 1.0
            return True
        return False
