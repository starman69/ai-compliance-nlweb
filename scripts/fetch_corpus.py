#!/usr/bin/env python3
"""Acquire the open-access corpus into sources/ (PLAN.md §3).

For each manifest document:
  - `authored_summary`  -> copy manifest/summaries/<file> to sources/open/<id>.md (no network)
  - open `pdf`          -> download to sources/open/<id>.pdf
  - open `html`         -> fetch + light readability -> sources/open/<id>.md

The corpus is 100% open-access; nothing is skipped for licensing. Idempotent
and resumable (skips unchanged files), polite (real UA + rate-limit), and emits
sources/_index.json (checksum, status, fetch date) for audit.

Usage:
  python scripts/fetch_corpus.py                  # fetch everything
  python scripts/fetch_corpus.py --summaries-only # no network; just ISO summaries
  python scripts/fetch_corpus.py --only eu-ai-act-2024-1689 gdpr-2016-679
  python scripts/fetch_corpus.py --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "manifest" / "corpus.yaml"
SUMMARIES = REPO_ROOT / "manifest" / "summaries"
OPEN_DIR = REPO_ROOT / "sources" / "open"
INDEX_PATH = REPO_ROOT / "sources" / "_index.json"
# A browser UA — many government/standards sites 403 a bot UA. We only fetch
# public, open-access publications (PLAN §3 legal note).
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def html_to_markdown(html: str) -> str:
    """Light readability: drop scripts/styles, keep heading hierarchy + text."""
    html = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<h([1-6])[^>]*>(.*?)</h\1>", lambda m: f"\n\n{'#' * int(m.group(1))} {m.group(2)}\n\n", html)
    html = re.sub(r"(?is)</p>|<br\s*/?>", "\n", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def eurlex_pdf_url(url: str) -> str | None:
    """EUR-Lex pages are JS-rendered (HTML extraction yields nothing), but it
    serves a PDF rendering. Map a EUR-Lex doc URL to its PDF endpoint:
      …/legal-content/EN/TXT/?uri=X      -> …/legal-content/EN/TXT/PDF/?uri=X
      …/eli/reg/<year>/<num>/oj          -> …/TXT/PDF/?uri=CELEX:3<year>R<num4>
    """
    if "eur-lex.europa.eu" not in url:
        return None
    if "uri=" in url:
        return re.sub(r"/TXT/\?uri=", "/TXT/PDF/?uri=", url)
    m = re.search(r"/eli/reg/(\d{4})/(\d+)/oj", url)
    if m:
        celex = f"3{m.group(1)}R{int(m.group(2)):04d}"
        return f"https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:{celex}"
    return None


def fetch_url(url: str, *, is_pdf: bool, timeout: float = 45.0) -> bytes:
    import time as _time

    import httpx

    with httpx.Client(follow_redirects=True, timeout=timeout, headers={"User-Agent": UA}) as c:
        r = None
        for _ in range(6):
            r = c.get(url)
            if r.status_code == 202:  # EUR-Lex is generating the PDF; wait + retry
                _time.sleep(2.5)
                continue
            break
        assert r is not None
        r.raise_for_status()
        return r.content


def process(doc: dict, *, summaries_only: bool, dry_run: bool) -> dict:
    doc_id = doc["id"]
    rec = {
        "id": doc_id, "source_type": doc.get("source_type"), "url": doc.get("official_url"),
        "status": "pending", "path": None, "sha256": None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if doc.get("source_type") == "authored_summary":
            src = REPO_ROOT / "manifest" / doc["path"]
            dst = OPEN_DIR / f"{doc_id}.md"
            if not dry_run:
                dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                rec["sha256"] = sha256(dst)
            rec["path"] = str(dst.relative_to(REPO_ROOT))
            rec["status"] = "copied"
            return rec

        if summaries_only:
            rec["status"] = "skipped (summaries-only)"
            return rec

        url = doc["official_url"]
        fmt = doc.get("format", "html")
        eur = eurlex_pdf_url(url)
        if eur:                       # fetch EUR-Lex as its PDF rendering
            url, fmt = eur, "pdf"
        is_pdf = fmt == "pdf"
        ext = "pdf" if is_pdf else "md"
        dst = OPEN_DIR / f"{doc_id}.{ext}"
        if dst.exists() and not dry_run:
            rec["path"] = str(dst.relative_to(REPO_ROOT))
            rec["sha256"] = sha256(dst)
            rec["status"] = "cached"
            return rec
        if dry_run:
            rec["status"] = "would-fetch"
            return rec

        rec["url"] = url
        content = fetch_url(url, is_pdf=is_pdf)
        if is_pdf:
            dst.write_bytes(content)
        else:
            dst.write_text(html_to_markdown(content.decode("utf-8", errors="replace")), encoding="utf-8")
        rec["path"] = str(dst.relative_to(REPO_ROOT))
        rec["sha256"] = sha256(dst)
        rec["status"] = "fetched"
    except Exception as exc:
        rec["status"] = f"error: {type(exc).__name__}: {exc}"
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--summaries-only", action="store_true", help="copy ISO summaries only; no network")
    ap.add_argument("--only", nargs="*", help="restrict to these doc ids")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rate", type=float, default=1.0, help="seconds between network fetches")
    args = ap.parse_args(argv)

    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    docs = manifest["documents"]
    if args.only:
        docs = [d for d in docs if d["id"] in set(args.only)]
    OPEN_DIR.mkdir(parents=True, exist_ok=True)

    index = []
    for i, doc in enumerate(docs):
        rec = process(doc, summaries_only=args.summaries_only, dry_run=args.dry_run)
        index.append(rec)
        print(f"[{i + 1:>2}/{len(docs)}] {rec['status']:<28} {doc['id']}")
        if rec["status"] in ("fetched",) and not args.dry_run and args.rate:
            time.sleep(args.rate)

    if not args.dry_run:
        INDEX_PATH.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {INDEX_PATH.relative_to(REPO_ROOT)} ({len(index)} entries)")
    by_status: dict[str, int] = {}
    for r in index:
        by_status[r["status"].split(":")[0]] = by_status.get(r["status"].split(":")[0], 0) + 1
    print("Summary:", dict(sorted(by_status.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
