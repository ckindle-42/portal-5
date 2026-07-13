#!/usr/bin/env python3
"""Doc-currency ledger for Portal.

Binds every documentation file to the source paths that determine its
correctness, and records the commit each doc was last *reconciled* against.
A doc is STALE when any bound source path has at least one commit in the
range ``<last_reconciled_commit>..HEAD``.

This is the doc-side analogue of the test/validate harness: the re-runnable
doc-audit agent task is how you *clear* staleness; this module is how
staleness is *detected* and CI-gated (validate_system.py check "AK. doc
currency"). Docs must never list themselves or this ledger as a source,
so a reconcile commit (which touches only docs + the ledger) never
re-triggers staleness.

Repo-name-agnostic: every path is repo-relative, so the ledger survives the
portal-5 -> portal migration with no edits.

Usage:
    python3 scripts/doc_ledger.py status [--json]
    python3 scripts/doc_ledger.py check  [--json]      # exit 1 if any doc stale
    python3 scripts/doc_ledger.py stamp <doc> [--commit HEAD]
    python3 scripts/doc_ledger.py stamp-all [--commit HEAD]
    python3 scripts/doc_ledger.py add <doc> --sources pathA,pathB,...
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "docs" / ".doc_ledger.yaml"


def _git(*args: str) -> str:
    out = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip()


def head_sha() -> str:
    return _git("rev-parse", "HEAD")


def _is_valid_rev(commit: str) -> bool:
    if not commit:
        return False
    out = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return out.returncode == 0


def load_ledger() -> dict[str, Any]:
    if not LEDGER_PATH.exists():
        return {"version": 1, "docs": {}}
    data = yaml.safe_load(LEDGER_PATH.read_text(encoding="utf-8")) or {}
    data.setdefault("version", 1)
    data.setdefault("docs", {})
    return data


def save_ledger(data: dict[str, Any]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Doc-currency ledger — see scripts/doc_ledger.py.\n"
        "# Each doc binds to the source paths that determine its correctness.\n"
        "# last_reconciled_commit = the commit the doc was last verified against.\n"
        "# A doc is STALE when a bound source changed in <commit>..HEAD.\n"
        "# Re-stamp after reconciling: python3 scripts/doc_ledger.py stamp <doc>\n"
        "# Never list a doc or this ledger as its own source.\n"
    )
    body = yaml.dump(data, sort_keys=False, default_flow_style=False)
    LEDGER_PATH.write_text(header + body, encoding="utf-8")


def sources_changed_since(commit: str, sources: list[str]) -> list[str]:
    """Return `git log --oneline <commit>..HEAD -- <sources>` lines.

    Empty list => fresh. Non-empty => those source commits post-date the stamp.
    """
    if not sources:
        return []
    log = _git("log", "--oneline", f"{commit}..HEAD", "--", *sources)
    return [ln for ln in log.splitlines() if ln.strip()]


def doc_status(doc: str, entry: dict[str, Any]) -> dict[str, Any]:
    sources = entry.get("sources", []) or []
    commit = str(entry.get("last_reconciled_commit", "") or "")
    if not commit:
        return {
            "doc": doc,
            "sources": sources,
            "last_reconciled_commit": "",
            "stale": True,
            "reason": "never reconciled (no last_reconciled_commit)",
            "changed": [],
        }
    if not _is_valid_rev(commit):
        return {
            "doc": doc,
            "sources": sources,
            "last_reconciled_commit": commit,
            "stale": True,
            "reason": f"last_reconciled_commit {commit[:12]} not found in history",
            "changed": [],
        }
    changed = sources_changed_since(commit, sources)
    return {
        "doc": doc,
        "sources": sources,
        "last_reconciled_commit": commit,
        "stale": bool(changed),
        "reason": ("bound source(s) changed since stamp" if changed else "fresh"),
        "changed": changed,
    }


def all_status() -> list[dict[str, Any]]:
    led = load_ledger()
    return [doc_status(d, e) for d, e in sorted(led["docs"].items())]


def check_doc_currency() -> tuple[str, str, list[dict[str, Any]]]:
    """(status, detail, findings) — for validate_system.py check AL."""
    statuses = all_status()
    if not statuses:
        return ("SKIP", "doc ledger empty (no docs bound)", [])
    stale = [s for s in statuses if s["stale"]]
    if not stale:
        return ("PASS", f"{len(statuses)} docs fresh vs HEAD", [])
    findings = [
        {
            "doc": s["doc"],
            "reason": s["reason"],
            "changed_source_commits": s["changed"][:5],
        }
        for s in stale
    ]
    detail = (
        f"{len(stale)}/{len(statuses)} docs stale — run the doc-audit agent, "
        "then `python3 scripts/doc_ledger.py stamp-all`"
    )
    return ("FAIL", detail, findings)


def cmd_status(args: argparse.Namespace) -> int:
    statuses = all_status()
    if args.json:
        print(json.dumps({"docs": statuses}, indent=2))
        return 0
    stale = [s for s in statuses if s["stale"]]
    for s in statuses:
        mark = "STALE" if s["stale"] else "ok"
        print(f"[{mark:5}] {s['doc']}  ({s['reason']})")
        for c in s["changed"][:5]:
            print(f"          -> {c}")
    print(f"\n{len(statuses) - len(stale)}/{len(statuses)} fresh, {len(stale)} stale")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    status, detail, findings = check_doc_currency()
    if args.json:
        print(json.dumps({"status": status, "detail": detail, "findings": findings}))
    else:
        print(f"{status}: {detail}")
        for f in findings:
            print(f"  - {f['doc']}: {f['reason']}")
    return 1 if status == "FAIL" else 0


def cmd_stamp(args: argparse.Namespace) -> int:
    commit = args.commit if args.commit != "HEAD" else head_sha()
    led = load_ledger()
    if args.doc not in led["docs"]:
        print(f"error: {args.doc} not in ledger (add it first)", file=sys.stderr)
        return 2
    led["docs"][args.doc]["last_reconciled_commit"] = commit
    save_ledger(led)
    print(f"stamped {args.doc} @ {commit[:12]}")
    return 0


def cmd_stamp_all(args: argparse.Namespace) -> int:
    commit = args.commit if args.commit != "HEAD" else head_sha()
    led = load_ledger()
    for d in led["docs"]:
        led["docs"][d]["last_reconciled_commit"] = commit
    save_ledger(led)
    print(f"stamped {len(led['docs'])} docs @ {commit[:12]}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    led = load_ledger()
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    led["docs"].setdefault(args.doc, {})
    led["docs"][args.doc]["sources"] = sources
    led["docs"][args.doc].setdefault("last_reconciled_commit", "")
    save_ledger(led)
    print(f"added/updated {args.doc} ({len(sources)} sources)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Portal doc-currency ledger")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", help="show per-doc freshness")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("check", help="exit 1 if any doc stale")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("stamp", help="stamp one doc to a commit")
    sp.add_argument("doc")
    sp.add_argument("--commit", default="HEAD")
    sp.set_defaults(func=cmd_stamp)

    sp = sub.add_parser("stamp-all", help="stamp every doc to a commit")
    sp.add_argument("--commit", default="HEAD")
    sp.set_defaults(func=cmd_stamp_all)

    sp = sub.add_parser("add", help="add/update a doc binding")
    sp.add_argument("doc")
    sp.add_argument("--sources", required=True, help="comma-separated repo-relative paths")
    sp.set_defaults(func=cmd_add)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
