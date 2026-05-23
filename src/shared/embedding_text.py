"""Embedding-text builders. Pure module — no SDK imports.

Contextual retrieval (prepend a chunk-context header before embedding): the
header carries framework/jurisdiction/section context into the vector so that
"Article 9" from the EU AI Act and "Article 9" from the GDPR land in distinct
neighborhoods. The stored chunk text is unchanged; only the embedding input is
augmented.
"""
from __future__ import annotations

from typing import Any


def chunk_embedding_text(
    text: str,
    *,
    framework: str,
    jurisdiction: str | None = None,
    section_path: str | None = None,
) -> str:
    parts = [f"Framework: {framework}"]
    if jurisdiction:
        parts.append(f"Jurisdiction: {jurisdiction}")
    if section_path:
        parts.append(f"Section: {section_path}")
    ctx = "[" + "; ".join(parts) + "]"
    return f"{ctx} {text or ''}".strip()


def doc_embedding_text(doc: dict[str, Any]) -> str:
    """Summary-level embedding text for the compliance_docs collection."""
    parts = [
        doc.get("title"),
        doc.get("short_name"),
        doc.get("framework_family"),
        doc.get("summary"),
    ]
    return " | ".join(p for p in parts if p)
