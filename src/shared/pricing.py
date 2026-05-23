"""Per-model pricing in USD per 1M tokens, used by the token ledger.

Local Ollama models cost $0 (compute on the dev box, not a metered API).
Azure OpenAI rates are public-list snapshots (treat as ±10% indicative).
Lookup is lowercase-contains so deployment IDs that embed a model name
(e.g. `gpt-4.1-prod-eastus2`) still resolve. No match -> $0 (logged), never raises.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ModelRate:
    input_per_m: float = 0.0
    output_per_m: float = 0.0


# Longest/most-specific keys first (so "gpt-4.1-mini" wins over "gpt-4.1").
_RATES: tuple[tuple[str, _ModelRate], ...] = (
    # Azure OpenAI (public list, 2025 snapshot)
    ("gpt-4.1-mini",            _ModelRate(0.40, 1.60)),
    ("gpt-4.1",                 _ModelRate(2.00, 8.00)),
    ("gpt-4o-mini",             _ModelRate(0.15, 0.60)),
    ("gpt-4o",                  _ModelRate(2.50, 10.00)),
    ("text-embedding-3-small",  _ModelRate(0.02, 0.0)),
    ("text-embedding-3-large",  _ModelRate(0.13, 0.0)),
    # Local Ollama models — free at the API level
    ("qwen3",                   _ModelRate(0.0, 0.0)),
    ("qwen2.5",                 _ModelRate(0.0, 0.0)),
    ("mxbai-embed-large",       _ModelRate(0.0, 0.0)),
    ("bge-reranker",            _ModelRate(0.0, 0.0)),
    ("mock",                    _ModelRate(0.0, 0.0)),
)


def _rate_for(model: str | None) -> _ModelRate:
    if not model:
        return _ModelRate()
    m = model.lower()
    for key, rate in _RATES:
        if key in m:
            return rate
    LOG.warning("pricing: no rate for model=%r; charging $0", model)
    return _ModelRate()


def cost_for(
    model: str | None,
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    embedding_tokens: int = 0,
) -> float:
    """USD cost for a single call. Embedding calls pass `embedding_tokens`."""
    r = _rate_for(model)
    cost = (
        prompt_tokens * r.input_per_m / 1_000_000
        + completion_tokens * r.output_per_m / 1_000_000
        + embedding_tokens * r.input_per_m / 1_000_000
    )
    return round(cost, 8)
