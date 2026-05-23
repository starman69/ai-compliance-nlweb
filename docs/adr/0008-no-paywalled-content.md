# 0008 — No paywalled content; ISO/IEC standards as open authored summaries

- **Status:** Accepted
- **Date:** 2026-05-23
- **Deciders:** Dave Patten
- **Related:** [16-responsible-use](../poc/16-responsible-use.md) · ADR-0014 (corpus currency)
- **Supersedes:** the original "paywalled ISO via manual drop" approach in the planning Q&A.

## Context
The corpus's most authoritative global standards — the ISO/IEC 42001 family — are
**copyrighted** and sold per-copy by ISO/IEC. The original plan marked them
`access: paywalled`, had the fetch script skip them, and expected the user to drop licensed
PDFs into `sources/manual/`.

This repository will be **public on GitHub**. We do not want the corpus to contain, or even
*depend on*, paywalled material: it complicates licensing, makes the build non-reproducible
for anyone without a license, and risks committing copyrighted text. At the same time, a
flagship use case — *"How do I implement ISO 42001?"* — must still work.

## Decision
The corpus is **100% open-access**. No paywalled content ships in the repo.

Copyrighted ISO/IEC standards are represented by **open authored summaries**
(`source_type: authored_summary` in `manifest/corpus.yaml`), stored under
`manifest/summaries/<id>.md`. These are **non-normative** — compiled from public facts
(scope, the Harmonized-Structure clauses 4–10, Annex A *themes*, cross-references) — and
explicitly **not** the standard's normative text. We ship summaries for **ISO/IEC 42001,
23894, 22989, and 38507** (the rest are dropped to keep the set lean; add later if needed).

`sources/manual/` remains only as an **optional, gitignored** local path where a user *with a
license* may drop the real PDFs to enrich their own instance. The corpus is fully
reproducible without it.

## Consequences
### Positive
- The repo is clean, public-safe, and reproducible from open sources with no licenses.
- The flagship ISO 42001 use case still answers (routing + high-level guidance + cross-refs).
- Clear provenance and an honest "not the normative text" disclaimer in every summary.

### Negative / trade-offs
- Answers grounded in the ISO summaries are **coarser** than clause-accurate quotes; they
  cannot reproduce exact control text. Confidence/citations must reflect this.
- The summaries are authored content to maintain as standards revise (tracked via the
  manifest `version_date`).

### Follow-ups
- Fetch script: treat `authored_summary` docs by copying `manifest/summaries/<id>.md` →
  `sources/open/` (no network).
- Ingestion: tag summary-derived chunks so the answer layer can signal "summary, not
  normative" in the UI/confidence.
- `16-responsible-use` documents the licensing stance and staleness caveats.
