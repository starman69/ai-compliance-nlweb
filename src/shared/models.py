"""Pydantic models for the NLWeb contract (shared by /ask and /mcp).

The request payload is identical for both endpoints; `query` is the only
required field. The response carries a native `sources` array (ergonomic for the
UI) and an additive Schema.org `ItemList` projection (`item_list`, the NLWeb
convention), plus our extras (confidence, token_usage, retrieval debug).
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, computed_field

Mode = Literal["list", "summarize", "generate"]
Confidence = Literal["high", "medium", "low"]
Intent = Literal["implementation", "comparison", "scoping", "lookup", "out_of_scope"]


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AskRequest(BaseModel):
    query: str = Field(min_length=1, description="The natural-language question (required).")
    prev: list[Turn] = Field(default_factory=list, description="Prior turns for multi-turn.")
    decontextualized_query: Optional[str] = Field(
        default=None, description="Pre-condensed standalone query (optional)."
    )
    site: Optional[str] = Field(
        default=None, description="Comma-separated jurisdiction scope tokens, e.g. 'eu,us-co'."
    )
    mode: Mode = "summarize"

    def scope_tokens(self) -> list[str]:
        if not self.site:
            return []
        return [s.strip() for s in self.site.split(",") if s.strip()]


class Source(BaseModel):
    position: int
    doc_id: str
    title: str
    short_name: str
    section_path: Optional[str] = None
    page: Optional[int] = None
    url: Optional[str] = None
    quote: Optional[str] = None
    score: float = 0.0


class Scope(BaseModel):
    jurisdictions: list[str] = Field(default_factory=list)


class RetrievalDebug(BaseModel):
    candidates: int = 0
    reranked: int = 0
    fusion: str = "rrf"


class AskResponse(BaseModel):
    query_id: str
    answer: str
    mode: Mode
    confidence: Confidence
    intent: Intent
    decontextualized_query: Optional[str] = None  # set when a follow-up was condensed
    sources: list[Source]
    scope: Scope
    token_usage: dict
    model: str
    elapsed_ms: int
    retrieval: RetrievalDebug

    @computed_field  # type: ignore[prop-decorator]
    @property
    def item_list(self) -> dict[str, Any]:
        """Additive Schema.org JSON-LD view of `sources` (NLWeb convention).

        NLWeb shapes retrieval results as a Schema.org `ItemList`; we keep our
        native `sources` array for the UI and emit this as a parallel,
        standards-conformant projection. Each cited excerpt becomes a
        `ListItem` → `CreativeWork`. Always present (empty when no sources)."""
        return {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "numberOfItems": len(self.sources),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": s.position,
                    "item": {
                        "@type": "CreativeWork",
                        "name": s.short_name + (f" — {s.section_path}" if s.section_path else ""),
                        "headline": s.title,
                        "identifier": s.doc_id,
                        **({"url": s.url} if s.url else {}),
                        **({"text": s.quote} if s.quote else {}),
                    },
                }
                for s in self.sources
            ],
        }
