# 00 — Overview

> Part of the AI Compliance NLWeb documentation set — see
> [`01-architecture`](01-architecture.md), [`10-diagrams`](10-diagrams.md), and
> [`STATUS.md`](STATUS.md).

## What this is
**AI Compliance NLWeb** is a conversational compliance workbench: an **NLWeb**-style layer
over the world's AI rules and standards — the EU AI Act, ISO/IEC 42001, NIST AI RMF, US
executive orders, sector guidance, and national frameworks (Canada AIDA, Singapore, Brazil,
China). Engineers, security, and compliance teams ask natural-language questions and get
**grounded, cited** answers, exposed at **`/ask`** (humans/JSON) and **`/mcp`** (agents).

It recreates and upgrades a prior project of the same name (the original code was lost),
documented in Dave Patten's Medium write-up — *"NLWeb + MCP: Why Every Website Will Soon
Need an /ask Endpoint"*
(<https://medium.com/@dave-patten/nlweb-mcp-why-every-website-will-soon-need-an-ask-endpoint-92c8bac9d4da>).
The recovered architecture diagram and prior-UI screenshots are in
[`docs/images/reference/`](../images/reference/).

## POC goal
Validate NLWeb's `/ask` and `/mcp` contracts against a *real* corpus of AI-compliance
materials and prove conversational discovery is practical. It runs **fully on Docker,
locally, with a local model + Qdrant**, and switches to Azure OpenAI + Azure AI Search via
one env var.

## Audience
Engineers, security teams, and compliance teams — people who need to understand obligations
across overlapping AI regimes without reading every regulation end-to-end.

## Pillars
1. **NLWeb conversational layer** — one retrieval+answer core, two contracts (`/ask`,
   `/mcp`), shared payload and `mode` semantics, shared security.
2. **Accurate, grounded RAG** — hybrid dense+sparse retrieval, RRF fusion, cross-encoder
   reranking, and citation-enforced answers with a confidence signal. The model only states
   what it can cite.
3. **A reproducible corpus pipeline** — a versioned manifest, a fetch script, and
   structure-aware ingestion into 1024-d embeddings in Qdrant.
4. **A polished NLWeb MCP-client UI** — multi-turn chat, an expandable corpus explorer,
   quick-question chips, light/dark, per-answer confidence + a token-usage status bar.

## The corpus (48 documents, all open-access)
Five tiers — **Global** (ISO/IEC summaries, OECD, UNESCO, G7, Council of Europe) ·
**EU/UK/National** (EU AI Act + digital rulebook, GDPR, UK, Canada AIDA, Singapore, Brazil,
China) · **US Federal** (NIST AI RMF family, OMB memos, the 2025 executive orders, NIST
CSF/800-53, FedRAMP) · **US State** (Colorado, Texas, Utah, California, NYC, Illinois) ·
**Sector/Cloud** (CSA, Microsoft, Google).

**No paywalled content ships in this public repo.** Copyrighted ISO/IEC standards are
represented by **open authored summaries** (`manifest/summaries/`) — non-normative, compiled
from public facts (scope, clause structure, cross-references) — so the corpus is fully
reproducible and the flagship "How do I implement ISO 42001?" use case still works, while
clause-accurate quotes require the licensed standard. See
[`16-responsible-use`](16-responsible-use.md) and [`ADR 0008`](../adr/0008-no-paywalled-content.md).

The manifest [`manifest/corpus.yaml`](../../manifest/corpus.yaml) is the single source of
truth for corpus contents, provenance, and status.

## Signature use cases (drive design + the eval set)
- **Implementation** — *"How do I implement ISO 42001?"*, *"What records must I keep under
  the EU AI Act for a high-risk system?"*, *"GDPR requirements for AI?"*
- **Comparison** — *"Compare US vs EU AI policy."*, *"How does the Colorado AI Act differ
  from the EU AI Act on high-risk systems?"*, *"Summarize the obligations and relate them to
  ISO/IEC 42001 controls."*
- **Scoping / lookup** — *"What is the EU AI Act?"*, *"What are high-risk AI systems?"*,
  *"Which frameworks apply to a cloud SaaS using GenAI in Texas?"*

## Not legal advice
This is a retrieval/summarization aid over public materials, not legal advice; regulatory
text changes, and answers can be stale or incomplete. See [`16-responsible-use`](16-responsible-use.md).

## Where to go next
- [`01-architecture`](01-architecture.md) — system shape, dual-stack, NLWeb contract.
- [`10-diagrams`](10-diagrams.md) — the full Mermaid diagram set.
- [`STATUS.md`](STATUS.md) — phase-by-phase progress.
