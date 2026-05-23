"""Append-only JSONL audit sink (ADR 0017). Must never break the answer path —
all errors are swallowed and logged, never raised.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def audit_path() -> Path:
    return Path(os.environ.get("AUDIT_PATH", str(_REPO_ROOT / "data" / "audit.jsonl")))


def write(record: dict) -> None:
    """Append one audit record. Swallows its own errors."""
    try:
        record = {"ts": datetime.now(timezone.utc).isoformat(), **record}
        path = audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover - defensive
        LOG.warning("audit write failed (ignored): %s", exc)
