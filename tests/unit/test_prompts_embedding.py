from shared.embedding_text import chunk_embedding_text, doc_embedding_text
from shared.prompts import SYSTEM_PROMPT, build_messages, format_evidence


def test_chunk_embedding_header():
    out = chunk_embedding_text(
        "providers must keep logs", framework="EU AI Act", jurisdiction="eu",
        section_path="Art. 12",
    )
    assert out == "[Framework: EU AI Act; Jurisdiction: eu; Section: Art. 12] providers must keep logs"


def test_doc_embedding_text_joins_present_fields():
    txt = doc_embedding_text({"title": "T", "short_name": "S", "summary": "Sum"})
    assert "T" in txt and "S" in txt and "Sum" in txt


def test_format_evidence_numbering_and_citation():
    ev = [{"short_name": "EU AI Act", "section_path": "Art. 9", "page": 52,
           "jurisdiction": "eu", "text": "risk management system"}]
    rendered = format_evidence(ev)
    assert rendered.startswith("[1] EU AI Act §Art. 9, p.52")
    assert "risk management system" in rendered


def test_build_messages_system_and_user():
    msgs = build_messages(query="q", evidence=[], intent="lookup", mode="summarize")
    assert msgs[0]["role"] == "system"
    assert "ONLY from the EVIDENCE" in SYSTEM_PROMPT
    assert msgs[1]["role"] == "user"
    assert "QUESTION:" in msgs[1]["content"]


def test_comparison_guide_present():
    msgs = build_messages(query="q", evidence=[], intent="comparison", mode="summarize")
    assert "COMPARISON question" in msgs[1]["content"]
