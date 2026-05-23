import pytest
from pydantic import ValidationError

from shared.models import AskRequest, AskResponse, RetrievalDebug, Scope, Source


def test_query_required_nonempty():
    with pytest.raises(ValidationError):
        AskRequest(query="")


def test_defaults():
    r = AskRequest(query="hi")
    assert r.mode == "summarize"
    assert r.prev == []
    assert r.scope_tokens() == []


def test_scope_tokens_parsing():
    r = AskRequest(query="x", site="eu, us-co ,, int")
    assert r.scope_tokens() == ["eu", "us-co", "int"]


def _resp(sources):
    return AskResponse(
        query_id="q1", answer="a", mode="summarize", confidence="high", intent="lookup",
        sources=sources, scope=Scope(), token_usage={}, model="m", elapsed_ms=1,
        retrieval=RetrievalDebug(),
    )


def test_item_list_is_schema_org_itemlist():
    src = Source(
        position=1, doc_id="eu-ai-act", title="EU AI Act", short_name="EU AI Act",
        section_path="Art. 6", page=12, url="https://x/y", quote="high-risk systems",
    )
    out = _resp([src]).model_dump()
    il = out["item_list"]
    assert il["@context"] == "https://schema.org"
    assert il["@type"] == "ItemList"
    assert il["numberOfItems"] == 1
    el = il["itemListElement"][0]
    assert el["@type"] == "ListItem" and el["position"] == 1
    assert el["item"]["@type"] == "CreativeWork"
    assert el["item"]["name"] == "EU AI Act — Art. 6"
    assert el["item"]["identifier"] == "eu-ai-act"
    assert el["item"]["url"] == "https://x/y"


def test_item_list_empty_when_no_sources():
    il = _resp([]).model_dump()["item_list"]
    assert il["@type"] == "ItemList" and il["numberOfItems"] == 0
    assert il["itemListElement"] == []
