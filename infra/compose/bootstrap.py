"""One-shot bootstrap (idempotent): create Qdrant collections + pull Ollama
models for the `local` profile. For `azure`, prints the Azure AI Search index
expectations (provision separately). PLAN.md §8.
"""
from __future__ import annotations

import os
import sys
import time

# Collection/index names — must match shared.clients.get_vector_client, which
# builds f"compliance_{which}". The compose-contract test asserts this stays in sync.
COLLECTIONS = ("compliance_docs", "compliance_chunks")


def embedding_dim() -> int:
    return int(os.environ.get("EMBEDDING_DIM", "1024"))


def _qdrant_url() -> str:
    return os.environ.get("QDRANT_URL", "http://qdrant:6333")


def create_qdrant_collections() -> None:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, SparseVectorParams, VectorParams

    qc = QdrantClient(url=_qdrant_url())
    existing = {c.name for c in qc.get_collections().collections}
    dim = embedding_dim()
    for name in COLLECTIONS:
        if name in existing:
            print(f"  collection exists: {name}")
            continue
        qc.create_collection(
            collection_name=name,
            vectors_config={"dense": VectorParams(size=dim, distance=Distance.COSINE)},
            sparse_vectors_config={"sparse": SparseVectorParams()},
        )
        print(f"  created collection: {name} (dense {dim}-d + sparse)")


def pull_ollama_models() -> None:
    import httpx

    base = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434/v1").replace("/v1", "")
    models = [m.strip() for m in os.environ.get("OLLAMA_MODELS", "").split(",") if m.strip()]
    for m in models:
        print(f"  ollama pull {m} …")
        with httpx.Client(timeout=None) as c:
            with c.stream("POST", f"{base}/api/pull", json={"name": m}) as r:
                for _ in r.iter_lines():
                    pass
        print(f"  pulled {m}")


def wait_for_qdrant(timeout: float = 60.0) -> None:
    import httpx

    deadline = time.time() + timeout
    url = _qdrant_url().rstrip("/") + "/readyz"
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=3).status_code < 500:
                return
        except Exception:
            pass
        time.sleep(2)
    print("  (warning) Qdrant not confirmed ready; proceeding")


def main() -> int:
    profile = (os.environ.get("RUNTIME_PROFILE") or "local").lower()
    print(f"bootstrap: profile={profile} EMBEDDING_DIM={embedding_dim()}")
    if profile == "azure":
        print(
            "  azure profile: ensure Azure AI Search indexes "
            "'compliance-docs-index' and 'compliance-chunks-index' exist at 1536-d, "
            "and Azure OpenAI deployments gpt-4.1 + text-embedding-3-small are available."
        )
        return 0
    wait_for_qdrant()
    create_qdrant_collections()
    pull_ollama_models()
    print("bootstrap: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
