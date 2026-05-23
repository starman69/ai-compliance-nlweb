# 0014 — Corpus currency & provenance

- **Status:** Accepted
- **Date:** 2026-05-23
- **Deciders:** Dave Patten
- **Related:** ADR-0008 (no paywalled content) · [16-responsible-use](../poc/16-responsible-use.md)

## Context
A compliance corpus is only trustworthy if its provenance and currency are explicit: which
version of a law/standard, fetched from where, when, and whether the text is the real document
or a summary. Some sources are also genuinely hard to fetch reliably (JS-viewer pages,
bot-blocked sites, HTML mislabeled as PDF).

## Decision
- **`manifest/corpus.yaml` is the source of truth** for the corpus: every doc carries
  `official_url`, `version_date`, `status` (`in_force`/`voluntary`/etc.), `framework_family`,
  `jurisdiction`, and `source_type`.
- **`source_type` is honest about provenance:** `fetch` (real fetched text) vs
  `authored_summary` (a concise, non-normative summary of public facts, each file footed with
  *"Open summary … non-normative"*). ISO/IEC standards are authored summaries (ADR-0008); a
  doc whose live source can't be fetched cleanly is recovered as an authored summary rather than
  shipping scraped navigation/junk.
- **Provenance trail:** `scripts/fetch_corpus.py` emits `sources/_index.json` (URL, checksum,
  fetch date) for audit; the corpus is fully reproducible from open sources.
- Answers cite `[short_name §section, p.N]`, and version/status come from the manifest, so a
  reader can always trace a claim to a dated, identified instrument.

## Consequences
### Positive
- The "48 documents / 32 frameworks" claim is genuinely backed; nothing is hollow or scraped junk.
- Currency is visible (version_date/status) and citations are traceable.

### Negative / trade-offs
- Authored summaries are non-normative (public facts, not verbatim law) — clearly labelled as such.
- Currency requires manual manifest upkeep as instruments change.

### Follow-ups
- When a previously-unfetchable source becomes cleanly fetchable, replace its summary with the
  real text and flip `source_type` back to `fetch`.
