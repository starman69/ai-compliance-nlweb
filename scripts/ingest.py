#!/usr/bin/env python3
"""Ingest the corpus into the active profile's vector store (PLAN.md §4).

  parse sources/open/<id>.{pdf,md} -> structure-aware chunk -> contextual header
  -> embed -> upsert into the `compliance_chunks` store.

Per document:
  - a fetched PDF/MD with enough text  -> chunk the real content (pypdf / headings)
  - otherwise                          -> fall back to the curated seed chunks
                                          (data/mock_chunks.yaml) for that doc_id

Real profiles only (NLWEB_BACKEND=real):
  local -> Ollama mxbai-embed-large (1024-d) -> Qdrant
  azure -> Azure OpenAI text-embedding-3-small (1536-d) -> Azure AI Search

Usage (repo root, stack up):
  NLWEB_BACKEND=real RUNTIME_PROFILE=local PYTHONPATH=src python scripts/ingest.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

# This file is `ingest.py`, which would shadow the `src/ingest` package when run
# as a script (its own dir lands on sys.path[0]). Drop the script dir and put
# src first so `from ingest import …` resolves to the package.
REPO = Path(__file__).resolve().parents[1]
_HERE = str(Path(__file__).resolve().parent)
sys.path[:] = [p for p in sys.path if p not in ("", _HERE)]
_SRC = str(REPO / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from ingest import chunking  # noqa: E402
from shared import clients, corpus, embedding_text  # noqa: E402
OPEN = REPO / "sources" / "open"
SEED = REPO / "data" / "mock_chunks.yaml"

MIN_DOC_CHARS = 600          # below this, treat fetched content as unusable
MAX_CHUNKS_PER_DOC = 90      # keep the corpus balanced + ingest fast
# mxbai-embed-large has a 512-token context. Dense legal/table text can pack
# many tokens per word, so keep chunks small and hard-cap the embed input below.
CHUNK_MAX_WORDS = 200
EMBED_BATCH = 32


def _seed_by_doc() -> dict[str, list[dict]]:
    if not SEED.exists():
        return {}
    data = yaml.safe_load(SEED.read_text(encoding="utf-8")) or {}
    out: dict[str, list[dict]] = {}
    for c in data.get("chunks", []):
        out.setdefault(c["doc_id"], []).append(c)
    return out


def _looks_garbled(chunks: list[dict]) -> bool:
    """Detect broken PDF extraction (e.g. the EUR-Lex OJ's justified multi-column
    layout makes pypdf split words: 'syste m', 'countr y'). Such text has an
    abnormally high ratio of single-character tokens. We skip it and let the
    clean seed cover the doc instead."""
    toks = " ".join(c["text"] for c in chunks).split()
    if len(toks) < 50:
        return False
    ones = sum(1 for t in toks if len(t) == 1)
    # Calibrated: clean PDFs ≤0.04, the EUR-Lex OJ's broken multi-column ≥0.09.
    return ones / len(toks) > 0.07


def _source_chunks(doc: dict) -> list[dict]:
    did = doc["id"]
    pdf, md = OPEN / f"{did}.pdf", OPEN / f"{did}.md"
    if pdf.exists():
        raw = pdf.read_bytes()
        chunks = chunking.chunks_for_pdf(doc, raw, max_words=CHUNK_MAX_WORDS)
        if _looks_garbled(chunks):
            # pypdf garbled this (e.g. the EUR-Lex OJ's multi-column layout) —
            # retry via the unstructured service, which extracts it cleanly.
            endpoint = (
                os.environ.get("UNSTRUCTURED_URL", "http://localhost:8002").rstrip("/")
                + "/general/v0/general"
            )
            try:
                u = chunking.chunks_for_pdf_unstructured(doc, raw, endpoint=endpoint, max_words=CHUNK_MAX_WORDS)
                chunks = u if (u and not _looks_garbled(u)) else []
            except Exception:
                chunks = []
            if not chunks:  # unstructured unavailable or still garbled -> seed
                return []
    elif md.exists():
        chunks = chunking.chunks_for_markdown(doc, md.read_text(encoding="utf-8"), max_words=CHUNK_MAX_WORDS)
    else:
        return []
    if sum(len(c["text"]) for c in chunks) < MIN_DOC_CHARS:
        return []
    return chunks[:MAX_CHUNKS_PER_DOC]


def collect_chunks() -> tuple[list[dict], dict[str, int]]:
    """Per doc, ingest real-parsed chunks AND any curated seed chunks (union).

    The seed is a clean, high-value 'highlights' layer (e.g. EU AI Act Art. 9/12,
    Annex III) authored as plain text — it stays useful even where real PDF
    extraction is noisy (the OJ's justified multi-column layout) or where the
    article we want is past the per-doc chunk cap. Retrieval picks whichever ranks.
    """
    seed = _seed_by_doc()
    chunks: list[dict] = []
    stats = {"real+seed": 0, "real": 0, "seed": 0, "empty": 0}
    for doc in corpus.documents():
        real = _source_chunks(doc)
        seed_chunks = seed.get(doc["id"], [])
        if real and seed_chunks:
            chunks.extend(real + seed_chunks)
            stats["real+seed"] += 1
        elif real:
            chunks.extend(real)
            stats["real"] += 1
        elif seed_chunks:
            chunks.extend(seed_chunks)
            stats["seed"] += 1
        else:
            stats["empty"] += 1
    return chunks, stats


def _embed_all(embed, texts: list[str], model: str) -> list[list[float]]:
    """Embed all texts, robust to a few token-dense chunks that exceed the
    embedder's context: on a batch error, split; for a single failing item,
    truncate hard and retry, then skip (empty vector) if it still fails."""
    vectors: list[list[float]] = [[] for _ in texts]
    done = 0

    def run(idxs: list[int]) -> None:
        nonlocal done
        try:
            vecs, _ = embed.embed([texts[i] for i in idxs], model=model)
            for k, i in enumerate(idxs):
                vectors[i] = vecs[k]
            done += len(idxs)
        except Exception:
            if len(idxs) == 1:
                i = idxs[0]
                try:
                    vecs, _ = embed.embed([texts[i][:400]], model=model)
                    vectors[i] = vecs[0]
                except Exception:
                    vectors[i] = []
                done += 1
            else:
                mid = len(idxs) // 2
                run(idxs[:mid])
                run(idxs[mid:])

    for start in range(0, len(texts), EMBED_BATCH):
        run(list(range(start, min(start + EMBED_BATCH, len(texts)))))
        print(f"  embedded {min(start + EMBED_BATCH, len(texts))}/{len(texts)}")
    return vectors


def main() -> int:
    if clients.backend() != "real":
        print("Refusing to ingest with NLWEB_BACKEND=mock — set it to 'real'.", file=sys.stderr)
        return 1

    chunks, stats = collect_chunks()
    print(f"Documents: {stats['real+seed']} real+seed, {stats['real']} real-only, "
          f"{stats['seed']} seed-only, {stats['empty']} no-content.  Total chunks: {len(chunks)}")
    if not chunks:
        return 1

    # Hard char cap so even dense legal text / numeric tables stay under
    # mxbai-embed-large's 512-token context. The stored payload keeps full text.
    texts = [
        embedding_text.chunk_embedding_text(
            c.get("text", ""),
            framework=c.get("short_name") or c.get("framework_family") or "corpus",
            jurisdiction=c.get("jurisdiction"),
            section_path=c.get("section_path"),
        )[:900]
        for c in chunks
    ]

    embed = clients.get_embed_client()
    model = clients.embed_model()
    print(f"Embedding {len(texts)} chunks via {model} …")
    vectors = _embed_all(embed, texts, model)

    dims = {len(v) for v in vectors if v}
    if not dims:
        print("Empty embeddings — is the model server reachable?", file=sys.stderr)
        return 1
    dim = dims.pop()
    skipped = sum(1 for v in vectors if not v)
    if skipped:
        print(f"  ({skipped} chunks skipped — too token-dense to embed even truncated)")

    store = clients.get_vector_client("chunks")
    store.ensure_collection(dim, recreate=True)
    n = store.upsert(chunks, vectors)
    print(f"Upserted {n} chunks (dim {dim}) into the chunks collection (recreated).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
