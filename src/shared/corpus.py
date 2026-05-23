"""Corpus manifest loader + grouping for the /corpus explorer.

The manifest (manifest/corpus.yaml) is the single source of truth for corpus
contents and status (PLAN.md §2). This module loads it, exposes the document
list, groups it tier -> documents for the UI, and resolves jurisdiction scope
tokens.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MANIFEST = _REPO_ROOT / "manifest" / "corpus.yaml"


def manifest_path() -> Path:
    return Path(os.environ.get("CORPUS_MANIFEST", str(_DEFAULT_MANIFEST)))


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    with manifest_path().open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def documents() -> list[dict[str, Any]]:
    return list(load_manifest().get("documents", []))


def jurisdictions() -> dict[str, str]:
    return dict(load_manifest().get("jurisdictions", {}))


def tiers() -> list[dict[str, Any]]:
    return list(load_manifest().get("tiers", []))


def doc_by_id(doc_id: str) -> dict[str, Any] | None:
    for d in documents():
        if d.get("id") == doc_id:
            return d
    return None


def grouped() -> dict[str, Any]:
    """Shape the corpus for the explorer: stats + tiers -> documents."""
    docs = documents()
    tier_defs = tiers()
    families = {d.get("framework_family") for d in docs if d.get("framework_family")}
    by_tier: dict[str, list[dict[str, Any]]] = {}
    for d in docs:
        by_tier.setdefault(d.get("tier", "other"), []).append(
            {
                "id": d.get("id"),
                "title": d.get("title"),
                "short_name": d.get("short_name"),
                "jurisdiction": d.get("jurisdiction"),
                "framework_family": d.get("framework_family"),
                "status": d.get("status"),
                "version_date": d.get("version_date"),
                "official_url": d.get("official_url"),
                "source_type": d.get("source_type"),
            }
        )
    out_tiers = [
        {
            "id": t["id"],
            "name": t.get("name"),
            "blurb": t.get("blurb"),
            "documents": by_tier.get(t["id"], []),
        }
        for t in tier_defs
    ]
    return {
        "stats": {"frameworks": len(families), "documents": len(docs)},
        "jurisdictions": jurisdictions(),
        "tiers": out_tiers,
    }


def resolve_scope(tokens: list[str]) -> list[str]:
    """Keep only tokens that are defined jurisdictions; dedupe, preserve order."""
    known = set(jurisdictions())
    seen: list[str] = []
    for t in tokens:
        t = t.strip().lower()
        if t in known and t not in seen:
            seen.append(t)
    return seen
