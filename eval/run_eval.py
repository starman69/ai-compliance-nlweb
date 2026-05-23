#!/usr/bin/env python3
"""Eval harness (PLAN.md §5).

Runs eval/golden_qa.yaml against the live /ask endpoint and scores:
  - retrieval hit-rate  — did an expected doc appear in the cited sources?
  - term coverage       — fraction of expected key facts present in the answer
  - intent accuracy     — did the router classify as expected (when specified)?

Writes a dated, model-tagged baseline report to docs/poc/eval-baselines/.

Usage:
  python eval/run_eval.py                         # http://localhost:8000
  EVAL_API_URL=http://localhost:8000 python eval/run_eval.py --limit 5
"""
from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

import httpx
import yaml

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "eval" / "golden_qa.yaml"
OUT_DIR = REPO / "docs" / "poc" / "eval-baselines"
API = os.environ.get("EVAL_API_URL", "http://localhost:8000")


def ask(q: dict) -> dict:
    payload = {"query": q["query"], "mode": q.get("mode", "summarize")}
    if q.get("site"):
        payload["site"] = q["site"]
    r = httpx.post(f"{API}/ask", json=payload, timeout=180.0)
    r.raise_for_status()
    return r.json()


def score(q: dict, resp: dict) -> dict:
    source_ids = " ".join(s["doc_id"] for s in resp.get("sources", [])).lower()
    answer = (resp.get("answer") or "").lower()
    expect_docs = q.get("expect_docs", [])
    expect_terms = q.get("expect_terms", [])

    if q.get("intent") == "out_of_scope":
        ret_hit = resp["intent"] == "out_of_scope" and not resp.get("sources")
    elif expect_docs:
        ret_hit = any(d.lower() in source_ids for d in expect_docs)
    else:
        ret_hit = bool(resp.get("sources"))

    coverage = None
    if expect_terms and q.get("mode", "summarize") != "list":
        coverage = sum(1 for t in expect_terms if t.lower() in answer) / len(expect_terms)

    intent_ok = (resp["intent"] == q["intent"]) if q.get("intent") else None

    if q.get("intent") == "out_of_scope":
        passed = ret_hit and (intent_ok is not False)
    elif q.get("mode") == "list":
        passed = ret_hit
    else:
        passed = ret_hit and (coverage is None or coverage >= 0.5)

    return {"ret_hit": ret_hit, "coverage": coverage, "intent_ok": intent_ok, "passed": passed}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="only run the first N questions")
    args = ap.parse_args()

    questions = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))["questions"]
    if args.limit:
        questions = questions[: args.limit]

    rows, model = [], "?"
    for q in questions:
        try:
            resp = ask(q)
            if resp.get("model") and resp["model"] != "none":
                model = resp["model"]
            s = score(q, resp)
            rows.append((q, resp, s))
            mark = "PASS" if s["passed"] else "FAIL"
            cov = "-" if s["coverage"] is None else f"{s['coverage']:.0%}"
            print(f"  [{mark}] {q['id']:<22} hit={s['ret_hit']} cov={cov} intent={resp['intent']} {resp['elapsed_ms']}ms")
        except Exception as exc:
            rows.append((q, None, {"error": str(exc), "passed": False}))
            print(f"  [ERR ] {q['id']:<22} {exc}")

    n = len(rows)
    passed = sum(1 for *_, s in rows if s.get("passed"))
    hits = sum(1 for *_, s in rows if s.get("ret_hit"))
    covs = [s["coverage"] for *_, s in rows if s.get("coverage") is not None]
    mean_cov = sum(covs) / len(covs) if covs else 0.0
    intents = [s["intent_ok"] for *_, s in rows if s.get("intent_ok") is not None]
    intent_acc = sum(1 for x in intents if x) / len(intents) if intents else 0.0

    report = _render(rows, model, n, passed, hits, mean_cov, intent_acc)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = model.replace(":", "-").replace("/", "-")
    out = OUT_DIR / f"{date.today().isoformat()}-local-golden-qa-{tag}.md"
    out.write_text(report, encoding="utf-8")
    print(f"\nPassed {passed}/{n} · retrieval hit-rate {hits}/{n} · mean term coverage "
          f"{mean_cov:.0%} · intent acc {intent_acc:.0%}")
    print(f"Report: {out.relative_to(REPO)}")
    return 0 if passed == n else 1


def _render(rows, model, n, passed, hits, mean_cov, intent_acc) -> str:
    lines = [
        f"# Eval baseline — golden Q&A ({model})",
        "",
        f"_Date: {date.today().isoformat()} · backend: real · profile: local · "
        f"answer model: `{model}`_",
        "",
        "| Result | Aggregate |",
        "|---|---|",
        f"| Passed | **{passed}/{n}** |",
        f"| Retrieval hit-rate | {hits}/{n} ({hits / n:.0%}) |",
        f"| Mean term coverage | {mean_cov:.0%} |",
        f"| Intent accuracy | {intent_acc:.0%} |",
        "",
        "| # | Question | Pass | Hit | Coverage | Intent | ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for q, resp, s in rows:
        if resp is None:
            lines.append(f"| {q['id']} | {q['query']} | ❌ | — | — | ERROR | — |")
            continue
        cov = "—" if s["coverage"] is None else f"{s['coverage']:.0%}"
        lines.append(
            f"| {q['id']} | {q['query']} | {'✅' if s['passed'] else '❌'} | "
            f"{'✓' if s['ret_hit'] else '✗'} | {cov} | {resp['intent']} | {resp['elapsed_ms']} |"
        )
    lines += ["", "_Generated by `eval/run_eval.py` against the live `/ask` endpoint._"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
