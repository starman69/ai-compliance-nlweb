# 0009 — Answer model per profile + the eval method

- **Status:** Accepted
- **Date:** 2026-05-23
- **Deciders:** Dave Patten
- **Related:** ADR-0001 (dual runtime) · [05-retrieval-and-ranking](../poc/05-retrieval-and-ranking.md) · [19-nlweb-ask-endpoint](../poc/19-nlweb-ask-endpoint.md)

## Context
RAG answers need a generation model. The two profiles must produce comparable, grounded,
cited answers, and we need a way to measure whether they hold up — accuracy is the bar because
the domain is regulatory.

## Decision
The answer model is **per profile**, selected in `clients.answer_model()`:
- `local` → Ollama **`qwen3:14b`** (GPU);
- `azure` → Azure OpenAI **`gpt-4.1`** (with prompt caching on the static system prompt/framing).

There is **no Claude/Anthropic** anywhere in the build. `mode` gates the model: `list` makes
**no** model call; `summarize`/`generate` invoke it under a citation-enforced prompt
(`prompts.build_messages`).

**Eval method:** `eval/golden_qa.yaml` (a curated Q&A set spanning all five tiers + every
intent + `generate` mode) scored by `eval/run_eval.py` against a running API. Each item checks
retrieval hit (expected doc cited), term coverage (key facts present), and router intent. A
dated, model-tagged baseline lands in `docs/poc/eval-baselines/`.

## Consequences
### Positive
- Profiles are swappable without touching business logic; the eval makes accuracy measurable
  and regression-checkable (current local baseline: 36/36 · 100% retrieval/intent · 97% coverage).

### Negative / trade-offs
- Two models to keep prompts compatible with; phrasing variance means term-coverage is a soft
  metric (pass-rate / hit-rate / intent are the hard ones).

### Follow-ups
- Re-run the eval after retrieval/router/corpus changes; record a fresh baseline.
