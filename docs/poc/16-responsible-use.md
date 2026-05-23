# 16 — Responsible use

> What this tool is — and is not — for. Related: [ADR-0008](../adr/0008-no-paywalled-content.md)
> (no paywalled content), [ADR-0014](../adr/0014-corpus-currency-provenance.md) (currency/provenance).

## Not legal advice
AI Compliance NLWeb is a **research and discovery aid** over public AI-governance materials. Its
answers are **not legal advice** and do not create a lawyer–client relationship. For decisions
with legal consequence, consult qualified counsel and the **primary source** — the answer's
citations link you to it.

## Grounded, or it says so
The system is RAG-only and accuracy-first: the model **only explains what it can cite**, every
claim carries a `[framework §section, p.N]` citation, and when the corpus lacks supporting
evidence it **says so rather than guessing**. `mode = list` returns sources with no model
involvement at all. Treat citations as the authority, not the prose.

## Corpus limitations
- **Curated, not exhaustive** — 48 open-access documents across five tiers; it does not cover
  every jurisdiction or instrument, and currency depends on manifest upkeep
  ([ADR-0014](../adr/0014-corpus-currency-provenance.md)).
- **Non-normative summaries** — ISO/IEC standards (copyrighted) and some hard-to-fetch sources
  are represented by **open authored summaries** of public facts, clearly footed as
  non-normative; they are not the verbatim instrument.
- **Scope** — questions outside AI compliance are refused (`out_of_scope`); the corpus skews to
  the EU, US (federal + state), and selected national/international frameworks.

## Operational guardrails
Token scopes, rate limiting, a locked CORS allow-list, and per-query audit logging apply to
both endpoints ([`21-security`](21-security.md)). The token ledger and audit sink never block
the answer path — they log and move on.
