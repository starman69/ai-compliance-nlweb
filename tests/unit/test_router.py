from shared.router import classify, detect_scope


def test_implementation_intent_and_scope():
    p = classify("How do I implement ISO 42001?")
    assert p.intent == "implementation"
    assert "int" in p.jurisdictions
    assert "iso-42001-2023" in p.doc_hints


def test_comparison_intent_two_jurisdictions():
    p = classify("Compare the Colorado AI Act and the EU AI Act on high-risk systems")
    assert p.intent == "comparison"
    assert "us-co" in p.jurisdictions
    assert "eu" in p.jurisdictions


def test_lookup_intent():
    assert classify("What is the EU AI Act?").intent == "lookup"


def test_scoping_intent():
    p = classify("Which frameworks apply to a cloud SaaS using GenAI in Texas?")
    assert p.intent == "scoping"
    assert "us-tx" in p.jurisdictions


def test_out_of_scope():
    assert classify("What's the weather in Paris tomorrow?").intent == "out_of_scope"


def test_detect_scope_gdpr():
    juris, docs = detect_scope("What are the GDPR requirements for AI?")
    assert "eu" in juris
    assert "gdpr-2016-679" in docs
