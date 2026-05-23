"""Structure-aware parsing + chunking (PLAN.md §4).

Pure functions (pypdf lazy-imported) so the chunking logic is unit-testable:
- split_markdown: split on heading hierarchy -> (section_path, body)
- chunk_words: ~480-word windows with overlap, sentence-aware-ish, never empty
- pdf_pages: per-page text via pypdf
- chunks_for_doc: assemble chunk dicts (section_path, page, text + doc metadata)
"""
from __future__ import annotations

import io
import re
from typing import Any

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")
# Article/section-ish lead lines used as a section label inside PDF page text.
_SECTION_LEAD = re.compile(
    r"^\s*(Article|Art\.|Section|Sec\.|Clause|Annex|Chapter|Part)\s+[\dIVXLA-Z][\w.\-]*", re.I
)


def clean(text: str) -> str:
    text = _WS.sub(" ", text or "")
    text = _BLANKS.sub("\n\n", text)
    return text.strip()


def split_markdown(md: str) -> list[tuple[str, str]]:
    """Split markdown into [(section_path, body)] on `#`..`######` headings."""
    sections: list[tuple[str, str]] = []
    current = "Overview"
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append((current, body))

    for line in md.splitlines():
        m = _HEADING_RE.match(line.strip())
        if m:
            flush()
            current = m.group(2).strip()
            buf = []
        else:
            buf.append(line)
    flush()
    return sections


def chunk_words(text: str, *, max_words: int = 480, overlap: int = 60) -> list[str]:
    """Split into overlapping word windows. Returns [] for empty text."""
    words = (text or "").split()
    if not words:
        return []
    if len(words) <= max_words:
        return [" ".join(words)]
    step = max(1, max_words - overlap)
    out: list[str] = []
    for i in range(0, len(words), step):
        out.append(" ".join(words[i : i + max_words]))
        if i + max_words >= len(words):
            break
    return out


def pdf_pages(data: bytes) -> list[tuple[int, str]]:
    """Per-page (page_no, text) via pypdf. Returns [] if the bytes aren't a real
    PDF (e.g. a fetch returned an HTML error page) or can't be parsed."""
    if not data[:5].startswith(b"%PDF"):
        return []
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        page_iter = list(enumerate(reader.pages, start=1))
    except Exception:
        return []
    pages: list[tuple[int, str]] = []
    for n, page in page_iter:
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        if txt.strip():
            pages.append((n, txt))
    return pages


def _base(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": doc.get("id"),
        "short_name": doc.get("short_name"),
        "title": doc.get("title"),
        "jurisdiction": doc.get("jurisdiction"),
        "framework_family": doc.get("framework_family"),
        "status": doc.get("status"),
        "url": doc.get("official_url"),
    }


def chunks_for_markdown(doc: dict[str, Any], text: str, *, max_words: int = 480) -> list[dict[str, Any]]:
    base = _base(doc)
    out: list[dict[str, Any]] = []
    sections = split_markdown(text) or [("Overview", clean(text))]
    for sec, body in sections:
        for j, piece in enumerate(chunk_words(clean(body), max_words=max_words)):
            out.append(
                {
                    **base,
                    "chunk_id": f"{doc.get('id')}::{sec[:40]}#{j}",
                    "section_path": sec,
                    "page": None,
                    "text": piece,
                }
            )
    return out


def _chunks_from_pages(
    doc: dict[str, Any], pages: list[tuple[int, str]], max_words: int
) -> list[dict[str, Any]]:
    base = _base(doc)
    out: list[dict[str, Any]] = []
    for page, txt in pages:
        lines = txt.strip().splitlines()
        first = lines[0].strip() if lines else ""
        # Use a detected Article/Section lead as the section_path; otherwise leave
        # it None (the page number is captured separately) to avoid "§p.2, p.2".
        sec = first[:60] if _SECTION_LEAD.match(first) else None
        for j, piece in enumerate(chunk_words(clean(txt), max_words=max_words)):
            out.append(
                {
                    **base,
                    "chunk_id": f"{doc.get('id')}::p{page}#{j}",
                    "section_path": sec,
                    "page": page,
                    "text": piece,
                }
            )
    return out


def chunks_for_pdf(doc: dict[str, Any], data: bytes, *, max_words: int = 480) -> list[dict[str, Any]]:
    return _chunks_from_pages(doc, pdf_pages(data), max_words)


def pdf_pages_unstructured(
    data: bytes, *, endpoint: str, strategy: str = "fast", timeout: float = 300.0
) -> list[tuple[int, str]]:
    """Per-page text via the unstructured-api /general/v0/general endpoint.
    Handles multi-column/justified PDFs (e.g. the EUR-Lex OJ) cleanly where
    pypdf splits words ('syste m'). Groups element text by page_number."""
    import httpx

    resp = httpx.post(
        endpoint,
        files={"files": ("doc.pdf", data, "application/pdf")},
        data={"strategy": strategy, "languages": "eng"},
        timeout=timeout,
    )
    resp.raise_for_status()
    pages: dict[int, list[str]] = {}
    for e in resp.json():
        text = (e.get("text") or "").strip()
        if not text:
            continue
        pg = int((e.get("metadata") or {}).get("page_number") or 0)
        pages.setdefault(pg, []).append(text)
    return [(pg, " ".join(parts)) for pg, parts in sorted(pages.items()) if pg]


def chunks_for_pdf_unstructured(
    doc: dict[str, Any], data: bytes, *, endpoint: str, max_words: int = 480
) -> list[dict[str, Any]]:
    return _chunks_from_pages(doc, pdf_pages_unstructured(data, endpoint=endpoint), max_words)
