# 0010 — Multi-turn via history-aware condensation (NLWeb `prev`)

- **Status:** Accepted
- **Date:** 2026-05-23
- **Deciders:** Dave Patten
- **Related:** ADR-0015 (NLWeb contract) · [19-nlweb-ask-endpoint](../poc/19-nlweb-ask-endpoint.md) · [05-retrieval-and-ranking](../poc/05-retrieval-and-ranking.md)

## Context
Follow-up questions ("how does that compare in the US?", "what about California?") are
anaphoric — they only make sense against the prior turn. Retrieval embeds the *current* query,
so a bare follow-up retrieves the wrong thing. NLWeb's payload carries `prev[]` (prior turns)
and an optional `decontextualized_query` for exactly this.

## Decision
Before retrieval, the service **condenses** an anaphoric follow-up into a standalone query
(`service._decontextualize`): if the caller supplied `decontextualized_query`, use it;
otherwise, when the turn is short (≤7 words) or opens with a connective/pronoun
("and…", "what about…", "compare…", "does it…"), prepend the previous user turn —
`"<prev> — <follow-up>"`. The condensed query is what gets embedded/retrieved, and it is
returned as `decontextualized_query` so the UI can show **"↳ interpreted as …"**.

Scope is also **inherited**: if a follow-up names no framework/jurisdiction, the most recent
prior turn that did supplies the scope (`service._inherited_scope`), keeping retrieval on-topic.
This is rules-first (no extra LLM call); an LLM condenser can be swapped in later.

## Consequences
### Positive
- Multi-turn works without forking the core or adding latency; the interpretation is transparent
  to the user.

### Negative / trade-offs
- Heuristic condensation can occasionally over/under-trigger; the `decontextualized_query` field
  lets a client override it explicitly.

### Follow-ups
- Consider an LLM-based condenser for ambiguous phrasings if the heuristic misses.
