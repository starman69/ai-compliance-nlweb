"""Bicep <-> app contract tests (azure profile). Pure file parsing — no Azure,
no bicep CLI. Catches drift that would only surface at deploy time:

- api container app missing an env var the azure profile needs
- OpenAI deployment name in containerApps.bicep not declared in openAi.bicep
- Search index name mismatch between Bicep app setting, the index JSON, and the
  shared.clients default
- embedding model swapped without updating the index dimensions (1536)

Mirrors the bicep-contract discipline (PLAN.md §11).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BICEP = ROOT / "infra" / "bicep"
AISEARCH = ROOT / "scripts" / "aisearch"
CLIENTS = ROOT / "src" / "shared" / "clients.py"


def _read(p: Path) -> str:
    return p.read_text()


def _container_env(text: str) -> dict[str, str]:
    """Parse `{ name: 'KEY', value: <literal|param> }` env entries (UPPERCASE keys)."""
    out: dict[str, str] = {}
    for k, v in re.findall(r"\{\s*name:\s*'([A-Z_0-9]+)'\s*,\s*value:\s*([^}]+?)\s*\}", text):
        v = v.strip()
        out[k] = v[1:-1] if v.startswith("'") and v.endswith("'") else v
    return out


def _openai_deployments(text: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r"deployments@[^']+'\s*=\s*\{", text):
        seg = text[m.end() : m.end() + 400]
        nm = re.search(r"name:\s*'([^']+)'", seg)
        if nm:
            names.add(nm.group(1))
    return names


def _clients_default(text: str, key: str) -> str | None:
    m = re.search(rf'os\.environ\.get\(\s*"{key}"\s*,\s*"([^"]+)"', text)
    return m.group(1) if m else None


def test_openai_deployments_match_app_and_settings() -> None:
    openai = _read(BICEP / "modules" / "openAi.bicep")
    capp = _container_env(_read(BICEP / "modules" / "containerApps.bicep"))
    clients = _read(CLIENTS)
    declared = _openai_deployments(openai)

    assert {"gpt-4.1", "text-embedding-3-small"} <= declared, f"openAi.bicep deployments={declared}"
    assert capp["OPENAI_DEPLOYMENT_REASONING"] == "gpt-4.1" == _clients_default(clients, "OPENAI_DEPLOYMENT_REASONING")
    assert capp["OPENAI_DEPLOYMENT_EMBEDDING"] == "text-embedding-3-small" == _clients_default(clients, "OPENAI_DEPLOYMENT_EMBEDDING")
    assert capp["OPENAI_DEPLOYMENT_REASONING"] in declared
    assert capp["OPENAI_DEPLOYMENT_EMBEDDING"] in declared


def test_search_index_names_match_json_and_clients() -> None:
    capp = _container_env(_read(BICEP / "modules" / "containerApps.bicep"))
    docs = json.loads(_read(AISEARCH / "compliance-docs-index.json"))
    chunks = json.loads(_read(AISEARCH / "compliance-chunks-index.json"))
    assert capp["SEARCH_INDEX_DOCS"] == docs["name"] == "compliance-docs-index"
    assert capp["SEARCH_INDEX_CHUNKS"] == chunks["name"] == "compliance-chunks-index"
    # clients builds the default index name as f"compliance-{which}-index"
    assert 'compliance-{which}-index' in _read(CLIENTS)


def test_embedding_dim_1536_matches_text_embedding_3_small() -> None:
    openai = _read(BICEP / "modules" / "openAi.bicep")
    assert "text-embedding-3-small" in openai, "openAi.bicep must declare text-embedding-3-small"
    for fname in ("compliance-docs-index.json", "compliance-chunks-index.json"):
        idx = json.loads(_read(AISEARCH / fname))
        emb = next((f for f in idx["fields"] if f["name"] == "embedding"), None)
        assert emb is not None, f"{fname} missing embedding field"
        assert emb["dimensions"] == 1536, f"{fname} embedding dim {emb['dimensions']} != 1536"


def test_required_azure_settings_injected() -> None:
    capp = _container_env(_read(BICEP / "modules" / "containerApps.bicep"))
    for key in (
        "RUNTIME_PROFILE", "NLWEB_BACKEND", "OPENAI_ENDPOINT", "OPENAI_API_VERSION",
        "SEARCH_SERVICE_ENDPOINT", "SEARCH_INDEX_DOCS", "SEARCH_INDEX_CHUNKS", "DOCINTEL_ENDPOINT",
    ):
        assert key in capp, f"containerApps.bicep api missing env var {key}"
    assert capp["RUNTIME_PROFILE"] == "azure"
    assert capp["NLWEB_BACKEND"] == "real"


def test_main_wires_all_modules() -> None:
    main = _read(BICEP / "main.bicep")
    for module in (
        "modules/observability.bicep", "modules/openAi.bicep", "modules/aiSearch.bicep",
        "modules/documentIntelligence.bicep", "modules/containerApps.bicep",
        "modules/staticWebApp.bicep", "modules/roleAssignments.bicep",
    ):
        assert module in main, f"main.bicep does not wire {module}"


def test_document_intelligence_wired() -> None:
    """The azure profile's layout step uses Azure AI Document Intelligence (the
    cloud analogue of local unstructured.io) — provisioned, env-injected, RBAC'd,
    and exposed via the clients.py layout factory."""
    di = _read(BICEP / "modules" / "documentIntelligence.bicep")
    assert "FormRecognizer" in di, "DI module must use kind FormRecognizer (Document Intelligence)"
    capp = _container_env(_read(BICEP / "modules" / "containerApps.bicep"))
    assert "DOCINTEL_ENDPOINT" in capp
    rbac = _read(BICEP / "modules" / "roleAssignments.bicep")
    assert "a97b65f3-24c7-4388-baec-2e87135dc908" in rbac, "api MI needs Cognitive Services User on DI"
    clients = _read(CLIENTS)
    assert "document_intelligence" in clients and "DOCINTEL_ENDPOINT" in clients
