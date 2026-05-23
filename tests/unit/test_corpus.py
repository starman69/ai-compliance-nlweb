from shared import corpus


def test_grouped_stats():
    g = corpus.grouped()
    assert g["stats"]["documents"] == 48
    assert g["stats"]["frameworks"] > 0
    assert len(g["tiers"]) == 5
    # every tier carries documents
    assert all("documents" in t for t in g["tiers"])


def test_resolve_scope_filters_unknown():
    assert corpus.resolve_scope(["eu", "xx", "us-co", "EU"]) == ["eu", "us-co"]


def test_doc_by_id():
    d = corpus.doc_by_id("eu-ai-act-2024-1689")
    assert d and d["short_name"] == "EU AI Act"
    assert corpus.doc_by_id("does-not-exist") is None
