"""compose <-> app contract: the docker-compose stack, .env.example, and the
code must agree on project name, embedding dim, collection names, model names,
and the registered routes. Mirrors the contract-test discipline from PLAN.md §11.
"""
import importlib.util
import inspect
from pathlib import Path

import pytest

from shared import clients

REPO = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO / "infra" / "compose" / ".env.example"
COMPOSE = REPO / "infra" / "compose" / "docker-compose.yml"
BOOTSTRAP = REPO / "infra" / "compose" / "bootstrap.py"


def _parse_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.split("#")[0].strip()
    return env


@pytest.fixture(scope="module")
def env() -> dict[str, str]:
    return _parse_env(ENV_EXAMPLE)


def test_compose_project_name_is_compliance(env):
    assert env["COMPOSE_PROJECT_NAME"] == "compliance"
    assert "name: compliance" in COMPOSE.read_text()


def test_embedding_dim_is_1024(env):
    assert env["EMBEDDING_DIM"] == "1024"


def test_answer_and_embed_models_sync_with_code(env, monkeypatch):
    monkeypatch.setenv("NLWEB_BACKEND", "real")
    monkeypatch.setenv("RUNTIME_PROFILE", "local")
    monkeypatch.setenv("OLLAMA_MODEL_REASONING", env["OLLAMA_MODEL_REASONING"])
    monkeypatch.setenv("OLLAMA_MODEL_EMBEDDING", env["OLLAMA_MODEL_EMBEDDING"])
    assert clients.answer_model() == env["OLLAMA_MODEL_REASONING"] == "qwen3:14b"
    assert clients.embed_model() == env["OLLAMA_MODEL_EMBEDDING"] == "mxbai-embed-large"


def test_collection_names_sync():
    # bootstrap defines the collections; clients builds f"compliance_{which}".
    spec = importlib.util.spec_from_file_location("bootstrap", BOOTSTRAP)
    boot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boot)
    assert boot.COLLECTIONS == ("compliance_docs", "compliance_chunks")
    src = inspect.getsource(clients.get_vector_client)
    assert 'f"compliance_{which}"' in src


def test_routes_registered():
    from api.app import app

    paths = {r.path for r in app.routes}
    assert {"/ask", "/mcp", "/corpus", "/health"}.issubset(paths)


def test_azure_models_documented_in_env():
    text = ENV_EXAMPLE.read_text()
    assert "gpt-4.1" in text
    assert "text-embedding-3-small" in text
