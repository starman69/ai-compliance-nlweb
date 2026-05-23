"""Per-request token-usage ledger.

Each /ask (and each ingest job) starts a fresh ``TokenLedger`` bound to a
contextvar, so every chat/embedding/rerank call site can record usage without
threading a parameter everywhere. The ledger accumulates totals + a per-call
breakdown; ``to_summary()`` feeds the API response's `token_usage` and the UI
status bar.

The OpenAI SDK returns ``response.usage`` on chat + embedding calls (Azure
OpenAI and Ollama 0.5+ both populate it). Missing usage -> zeros; the ledger
never raises (it must not break the answer path).
"""
from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass, field
from typing import Any

from .pricing import cost_for

LOG = logging.getLogger(__name__)


@dataclass
class _Entry:
    kind: str  # "chat" | "embedding" | "rerank"
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embedding_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class TokenLedger:
    """Accumulator for a single query / ingest job."""

    entries: list[_Entry] = field(default_factory=list)

    def record_chat(self, response: Any, *, model: str) -> None:
        usage = getattr(response, "usage", None)
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        cost = cost_for(model, prompt_tokens=prompt, completion_tokens=completion)
        self.entries.append(
            _Entry("chat", model, prompt_tokens=prompt, completion_tokens=completion, cost_usd=cost)
        )

    def record_embedding(self, response: Any, *, model: str) -> None:
        usage = getattr(response, "usage", None)
        toks = int(getattr(usage, "prompt_tokens", 0) or getattr(usage, "total_tokens", 0) or 0)
        cost = cost_for(model, embedding_tokens=toks)
        self.entries.append(_Entry("embedding", model, embedding_tokens=toks, cost_usd=cost))

    def record_manual(
        self, *, kind: str, model: str, prompt_tokens: int = 0,
        completion_tokens: int = 0, embedding_tokens: int = 0,
    ) -> None:
        """Record usage when the call site has raw counts rather than an SDK
        response object (e.g. the Mock LLM, or a reranker HTTP call)."""
        cost = cost_for(
            model, prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens, embedding_tokens=embedding_tokens,
        )
        self.entries.append(
            _Entry(kind, model, prompt_tokens=prompt_tokens,
                   completion_tokens=completion_tokens, embedding_tokens=embedding_tokens, cost_usd=cost)
        )

    @property
    def prompt_tokens(self) -> int:
        return sum(e.prompt_tokens for e in self.entries)

    @property
    def completion_tokens(self) -> int:
        return sum(e.completion_tokens for e in self.entries)

    @property
    def embedding_tokens(self) -> int:
        return sum(e.embedding_tokens for e in self.entries)

    @property
    def total_cost_usd(self) -> float:
        return round(sum(e.cost_usd for e in self.entries), 8)

    def to_summary(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "embedding_tokens": self.embedding_tokens,
            "estimated_cost_usd": self.total_cost_usd,
            "calls": [
                {
                    "kind": e.kind, "model": e.model,
                    "prompt_tokens": e.prompt_tokens,
                    "completion_tokens": e.completion_tokens,
                    "embedding_tokens": e.embedding_tokens,
                    "cost_usd": e.cost_usd,
                }
                for e in self.entries
            ],
        }


_LEDGER: contextvars.ContextVar[TokenLedger | None] = contextvars.ContextVar(
    "token_ledger", default=None
)


def start_ledger() -> TokenLedger:
    ledger = TokenLedger()
    _LEDGER.set(ledger)
    return ledger


def current() -> TokenLedger | None:
    return _LEDGER.get()


def record_chat(response: Any, *, model: str) -> None:
    led = current()
    if led is not None:
        led.record_chat(response, model=model)


def record_embedding(response: Any, *, model: str) -> None:
    led = current()
    if led is not None:
        led.record_embedding(response, model=model)
