from ingest.chunking import (
    chunk_words,
    chunks_for_markdown,
    clean,
    split_markdown,
)


def test_split_markdown_by_headings():
    md = "intro text\n\n## Scope\nscope body\n\n## Structure\nstructure body"
    secs = split_markdown(md)
    paths = [s for s, _ in secs]
    assert "Scope" in paths and "Structure" in paths
    assert dict(secs)["Scope"].strip() == "scope body"


def test_split_markdown_empty_sections_dropped():
    assert split_markdown("# Heading only\n\n## Another\n") == []


def test_chunk_words_windows_with_overlap():
    text = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk_words(text, max_words=400, overlap=50)
    assert len(chunks) >= 2
    assert all(len(c.split()) <= 400 for c in chunks)
    # overlap: last 50 words of chunk 0 reappear at the start of chunk 1
    assert chunks[0].split()[-50:] == chunks[1].split()[:50]


def test_chunk_words_short_text_single_chunk():
    assert chunk_words("a short sentence") == ["a short sentence"]
    assert chunk_words("   ") == []


def test_chunks_for_markdown_carries_metadata():
    doc = {
        "id": "iso-42001-2023", "short_name": "ISO/IEC 42001", "title": "ISO 42001",
        "jurisdiction": "int", "framework_family": "ISO/IEC 42001", "status": "voluntary",
        "official_url": "https://example.org",
    }
    out = chunks_for_markdown(doc, "## Scope\nbody text here", max_words=480)
    assert out and out[0]["doc_id"] == "iso-42001-2023"
    assert out[0]["section_path"] == "Scope"
    assert out[0]["jurisdiction"] == "int"
    assert out[0]["chunk_id"].startswith("iso-42001-2023::")


def test_clean_collapses_whitespace():
    assert clean("a   b\n\n\n\nc") == "a b\n\nc"
