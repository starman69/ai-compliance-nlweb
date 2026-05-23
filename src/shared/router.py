"""Query router — rules-first intent classification + scope detection.

Pure module (no SDK imports) so it unit-tests with plain pytest. Mirrors the
NLWeb intents in PLAN.md §4:

  implementation — "how do I implement / comply / what records must I keep"
  comparison     — "compare / vs / how does X differ from Y"
  scoping        — "which frameworks apply to ..."
  lookup         — "what is / what are / define ..."  (default for in-scope Qs)
  out_of_scope   — no compliance signal at all -> refuse

It also detects framework/jurisdiction cues and returns scope hints
(jurisdiction tokens + doc_id hints) that the service AND-s into the retrieval
filter. Rules-first keeps the common path LLM-free; the service may add an LLM
fallback later for ambiguous phrasings.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Intent

# --- framework / jurisdiction cues: phrase -> (jurisdiction, doc_id(s)|None) --
# `doc` may be a single doc_id, a tuple of doc_ids (the instrument spans several
# documents — e.g. the EU AI Act + its Annexes), or None (jurisdiction-only).
# Order matters only for readability; all matches are collected.
_CUES: tuple[tuple[str, str, "str | tuple[str, ...] | None"], ...] = (
    # The high-risk *use-case list* lives in Annex III, a separate doc — so any
    # EU-AI-Act / high-risk / annex query hints both the act and its annexes.
    (r"\beu ai act\b|\b2024/1689\b|\bannex\s*iii\b|\bhigh[\s-]?risk\b",
     "eu", ("eu-ai-act-2024-1689", "eu-ai-act-annexes")),
    (r"\bgdpr\b|\b2016/679\b|\barticle 22\b|automated (?:individual )?decision", "eu", "gdpr-2016-679"),
    (r"\bgpai\b|general[\s-]?purpose ai", "eu",
     ("eu-gpai-code-of-practice-2025", "eu-gpai-guidelines-2025")),
    (r"\bdsa\b|digital services act", "eu", "eu-dsa-2022-2065"),
    (r"\bdma\b|digital markets act", "eu", "eu-dma-2022-1925"),
    (r"\biso(?:/iec)?\s*42001\b|\baims\b|management system", "int", "iso-42001-2023"),
    # ISO 23894 = "AI — Guidance on risk management". Don't let bare "AI risk
    # management" grab the NIST AI RMF (whose full name ends in "Framework").
    (r"\biso(?:/iec)?\s*23894\b|\bai risk management\b(?!\s+framework)", "int", "iso-23894-2023"),
    (r"\biso(?:/iec)?\s*22989\b|terminology", "int", "iso-22989-2022"),
    (r"\biso(?:/iec)?\s*38507\b|governance of (?:it|ai)", "int", "iso-38507-2022"),
    (r"\boecd\b", "int", "oecd-ai-principles"),
    (r"\bunesco\b", "int", "unesco-ai-ethics-2021"),
    (r"\bnist\b.*\brmf\b|\bai rmf\b|\bai risk management framework\b|nist.{0,12}risk management|100-1|600-1", "us", "nist-ai-rmf-100-1"),
    (r"\bnist csf\b|cybersecurity framework", "us", "nist-csf-2-0"),
    (r"\b800-53\b", "us", "nist-sp-800-53r5"),
    (r"\bfedramp\b", "us", "fedramp-baseline"),
    (r"\bomb\b|m-24-10|m-25-2", "us", "omb-m-25-21"),
    (r"executive order|\beo \d|removing barriers|action plan", "us", None),
    (r"\bcolorado\b|sb 24-205|\bcoloradan?\b", "us-co", "colorado-ai-act-sb24-205"),
    (r"\btexas\b|traiga|hb 149", "us-tx", "texas-traiga-hb149"),
    (r"\butah\b|sb 149", "us-ut", "utah-ai-policy-act"),
    (r"\bcalifornia\b|sb 53|cppa|admt|ab 2013|\bca\b", "us-ca", "california-sb-53"),
    (r"\bnyc\b|local law 144|\baedt\b|new york city", "us-ny", "nyc-ll144-aedt"),
    (r"\billinois\b|\bbipa\b", "us-il", "illinois-bipa-ai-video"),
    (r"\bcanada\b|\baida\b", "ca", "canada-aida"),
    (r"\bsingapore\b", "sg", "singapore-model-ai-governance"),
    (r"\bbrazil\b|pl 2338", "br", "brazil-pl-2338"),
    (r"\bchina\b|\bcac\b", "cn", "china-genai-measures-2023"),
    (r"\buk\b|united kingdom|\bico\b|information commissioner|pro[\s-]?innovation",
     "uk", ("uk-pro-innovation-ai-2023", "uk-ico-ai-guidance")),
    # Broad jurisdiction cues (collected in addition to the specific ones above)
    # so e.g. "Compare US vs EU AI policy" scopes to both.
    (r"\bunited states\b|\bu\.s\.?\b|\bus\b|\bfederal\b", "us", None),
    (r"\beuropean union\b|\beu\b", "eu", None),
)

_COMPARISON = re.compile(
    r"\b(compare|comparison|versus|vs\.?|differ(?:s|ence)?|stricter|stronger|"
    r"contrast|how does .+ (?:differ|compare)|relate (?:them|it) to)\b",
    re.I,
)
_IMPLEMENTATION = re.compile(
    r"\b(how (?:do|to)(?: i)? (?:implement|comply|adopt|get certif)|implement\b|"
    r"comply with|conformity|certif(?:y|ication)|requirements?\b|"
    r"records?(?: must| to)? .*keep|what (?:must|do) i (?:keep|document|record)|checklist|"
    r"obligations?\b|steps? to)\b",
    re.I,
)
_SCOPING = re.compile(
    r"\b(which (?:frameworks?|laws?|regulations?|standards?|rules?)|"
    r"what (?:frameworks?|laws?|regulations?) (?:apply|cover)|do(?:es)? .* apply\b|"
    r"applies? to|in scope|covered by)\b",
    re.I,
)
_LOOKUP = re.compile(
    r"\b(what is|what are|what'?s|define|definition of|explain|tell me about|"
    r"summari[sz]e|overview of|who (?:is|are|enforces)|when (?:does|is))\b",
    re.I,
)
# A coarse compliance-signal gate: if NONE of these appear, and the query also
# matches no framework cue, we treat it as out_of_scope.
_COMPLIANCE_SIGNAL = re.compile(
    r"\b(ai|a\.i\.|artificial intelligence|machine learning|model|algorithm|"
    r"regulation|complian|govern|risk|standard|framework|act\b|law|policy|"
    r"privacy|data protection|gdpr|iso|nist|audit|high[\s-]?risk|obligation|"
    r"transparency|bias|safety|certif|conformit)\b",
    re.I,
)


@dataclass
class QueryPlan:
    intent: Intent
    jurisdictions: list[str] = field(default_factory=list)
    doc_hints: list[str] = field(default_factory=list)
    confidence: float = 1.0
    fallback_reason: str | None = None


def detect_scope(question: str) -> tuple[list[str], list[str]]:
    """Return (jurisdiction_tokens, doc_id_hints) detected in the question."""
    jurisdictions: list[str] = []
    docs: list[str] = []
    for pattern, juris, doc in _CUES:
        if re.search(pattern, question, re.I):
            if juris not in jurisdictions:
                jurisdictions.append(juris)
            # `doc` may be a single id or a tuple (instrument spanning docs) — flatten.
            for d in (() if doc is None else (doc,) if isinstance(doc, str) else doc):
                if d not in docs:
                    docs.append(d)
    return jurisdictions, docs


def classify(question: str) -> QueryPlan:
    jurisdictions, docs = detect_scope(question)
    has_signal = bool(_COMPLIANCE_SIGNAL.search(question)) or bool(jurisdictions)

    if not has_signal:
        return QueryPlan(
            intent="out_of_scope", confidence=0.9,
            fallback_reason="no-compliance-signal",
        )

    # Comparison wins when present (it changes the whole retrieval shape).
    if _COMPARISON.search(question) and (len(jurisdictions) >= 2 or _COMPARISON.search(question)):
        intent: Intent = "comparison"
    elif _IMPLEMENTATION.search(question):
        intent = "implementation"
    elif _SCOPING.search(question):
        intent = "scoping"
    elif _LOOKUP.search(question):
        intent = "lookup"
    else:
        # In-scope but no clean cue -> treat as a lookup (still retrieves).
        return QueryPlan(
            intent="lookup", jurisdictions=jurisdictions, doc_hints=docs,
            confidence=0.0, fallback_reason="no-intent-cue",
        )

    return QueryPlan(intent=intent, jurisdictions=jurisdictions, doc_hints=docs, confidence=0.95)
