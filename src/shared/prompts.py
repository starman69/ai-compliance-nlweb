"""Citation-enforced prompts for answer generation. Pure module.

The model answers ONLY from supplied evidence and cites every claim as
`[short_name §section, p.N]`. Insufficient evidence -> say so. Comparison mode
asks for shared-requirements / key-differences / what's-stricter. The static
SYSTEM prompt is ordered first so the azure profile's prompt cache can reuse it.
"""
from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """\
You are AI Compliance NLWeb, a grounded assistant over a curated corpus of AI
rules and standards (EU AI Act, ISO/IEC 42001, NIST AI RMF, GDPR, US state laws,
and more).

Rules you must follow:
1. Answer ONLY from the EVIDENCE blocks provided. Do not use outside knowledge.
2. Cite every factual claim inline as [short_name §section, p.N] using the
   evidence block labels. If a block has no section/page, cite [short_name].
3. If the evidence is insufficient to answer, say so plainly — do not guess.
4. Quotes must be reproduced as plain text, not invented or paraphrased as if
   quoted.
5. Be concise and well-structured (Markdown). This is not legal advice.
"""

_COMPARISON_GUIDE = """\
This is a COMPARISON question. Structure the answer as:
- **Shared requirements** — what the frameworks have in common.
- **Key differences** — where they diverge.
- **What's stricter** — which is more demanding and why.
Cite each framework's evidence inline.
"""

_GENERATE_GUIDE = """\
This is a GENERATE question. Produce a practical, structured artifact (e.g. an
implementation checklist or step list) grounded in and cited to the evidence.
"""


def format_evidence(evidence: list[dict[str, Any]]) -> str:
    """Render numbered evidence blocks for the prompt."""
    lines: list[str] = []
    for i, e in enumerate(evidence, start=1):
        label = e.get("short_name") or e.get("doc_id") or "source"
        sec = e.get("section_path")
        page = e.get("page")
        cite = label
        if sec:
            cite += f" §{sec}"
        if page:
            cite += f", p.{page}"
        header = f"[{i}] {cite} ({e.get('jurisdiction','')})".rstrip()
        lines.append(f"{header}\n{e.get('text','').strip()}")
    return "\n\n".join(lines) if lines else "(no evidence retrieved)"


def build_messages(
    *,
    query: str,
    evidence: list[dict[str, Any]],
    intent: str,
    mode: str,
) -> list[dict[str, str]]:
    guide = ""
    if intent == "comparison":
        guide = _COMPARISON_GUIDE
    elif mode == "generate":
        guide = _GENERATE_GUIDE

    user = (
        f"{guide}\nQUESTION:\n{query}\n\n"
        f"EVIDENCE:\n{format_evidence(evidence)}\n\n"
        "Write the answer now, citing each claim inline as "
        "[short_name §section, p.N]. If the evidence does not support an answer, "
        "say what is missing."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
