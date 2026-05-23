"""The `mode` engine: list = retrieval only (NO LLM); summarize/generate call
the model. This is a load-bearing correctness rule (PLAN.md §14)."""
import shared.clients as clients
from shared.models import AskRequest
from shared.service import ask


def test_list_mode_does_not_call_llm(monkeypatch):
    def boom():
        raise AssertionError("LLM must not be invoked in list mode")

    monkeypatch.setattr(clients, "get_chat_client", boom)
    r = ask(AskRequest(query="What is the EU AI Act?", mode="list"))
    assert r.mode == "list"
    assert r.model == "none"
    assert r.answer == ""
    assert r.token_usage["completion_tokens"] == 0
    assert r.sources, "list mode should still retrieve sources"


def test_summarize_mode_calls_llm_and_cites():
    r = ask(AskRequest(query="What records must I keep under the EU AI Act?", mode="summarize"))
    assert r.model == "mock-llm"
    assert r.token_usage["completion_tokens"] > 0
    assert r.answer
    assert "[" in r.answer and "]" in r.answer  # inline citations present
    assert r.sources[0].section_path


def test_llm_failure_degrades_to_sources(monkeypatch):
    """A model hiccup must not 500 — degrade to retrieval + a graceful note."""
    class _Boom:
        def complete(self, *a, **k):
            raise RuntimeError("model down")

    monkeypatch.setattr(clients, "get_chat_client", lambda: _Boom())
    r = ask(AskRequest(query="What records must I keep under the EU AI Act?", mode="summarize"))
    assert r.sources, "retrieval should still return sources on model failure"
    assert r.model == "none"
    assert "temporarily unavailable" in r.answer.lower()


def test_out_of_scope_refuses_without_retrieval():
    r = ask(AskRequest(query="What's the weather tomorrow?"))
    assert r.intent == "out_of_scope"
    assert r.sources == []
    assert r.model == "none"


def test_scope_filter_restricts_jurisdiction():
    r = ask(AskRequest(query="What are high-risk AI systems?", site="eu"))
    assert r.scope.jurisdictions == ["eu"]
    assert all(s.doc_id.startswith(("eu-", "gdpr")) or "eu" in s.doc_id for s in r.sources)
