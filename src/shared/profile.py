"""Runtime profile selector. Reads RUNTIME_PROFILE.

`local` (default) — Docker stack: Qdrant + Ollama (qwen3:14b + mxbai-embed-large).
`azure`           — Azure OpenAI (gpt-4.1 + text-embedding-3-small) + Azure AI Search.

Local-first is the default so the app runs zero-config on a dev box. The
`clients` factory branches on this; business logic must not.
"""
from __future__ import annotations

import os
from enum import Enum


class Profile(str, Enum):
    LOCAL = "local"
    AZURE = "azure"


def get_profile() -> Profile:
    raw = (os.environ.get("RUNTIME_PROFILE") or "local").lower()
    try:
        return Profile(raw)
    except ValueError:
        return Profile.LOCAL


def is_local() -> bool:
    return get_profile() is Profile.LOCAL


def is_azure() -> bool:
    return get_profile() is Profile.AZURE
