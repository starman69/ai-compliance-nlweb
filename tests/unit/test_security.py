import pytest

from shared import security
from shared.security import ASK_READ, MCP_INVOKE, AuthError, RateLimiter, principal_for


def test_dev_fallback_when_auth_disabled(monkeypatch):
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    p = principal_for(None)
    assert p.name == "dev"
    assert p.has(ASK_READ) and p.has(MCP_INVOKE)


def test_auth_enabled_requires_token(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    with pytest.raises(AuthError) as exc:
        principal_for(None)
    assert exc.value.status == 401


def test_dev_token_accepted(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_DEV_TOKEN", "secret-dev")
    p = principal_for("Bearer secret-dev")
    assert p.has(ASK_READ)


def test_configured_token_scopes(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_TOKENS", "abc123:ask:read")
    p = principal_for("Bearer abc123")
    assert p.has(ASK_READ)
    assert not p.has(MCP_INVOKE)


def test_invalid_token_rejected(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_TOKENS", "")
    with pytest.raises(AuthError) as exc:
        principal_for("Bearer nope")
    assert exc.value.status == 401


def test_rate_limiter_allows_then_blocks():
    rl = RateLimiter(rate_per_min=60, burst=3)
    now = 1000.0
    assert rl.allow("k", now=now)
    assert rl.allow("k", now=now)
    assert rl.allow("k", now=now)
    assert not rl.allow("k", now=now)  # burst exhausted, no time elapsed
    assert rl.allow("k", now=now + 2.0)  # ~1 token refilled after 2s @ 1/s
