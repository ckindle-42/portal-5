#!/usr/bin/env python3
"""Portal 5 UAT Results Dashboard.

Reads tests/UAT_RESULTS.md (and optionally uat_corpus/*.jsonl for trend data)
and outputs a structured dashboard similar in spirit to the TPS bench tables.

Usage:
    python3 tests/uat_dashboard.py              # print to stdout (latest run)
    python3 tests/uat_dashboard.py --md         # write tests/UAT_DASHBOARD.md
    python3 tests/uat_dashboard.py --trend 5    # show last N runs in trend table
    python3 tests/uat_dashboard.py --md --trend 8
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

RESULTS_FILE = Path("tests/UAT_RESULTS.md")
CORPUS_DIR = Path("tests/uat_corpus")
DASHBOARD_FILE = Path("tests/UAT_DASHBOARD.md")

# Status ordering for display
STATUS_ORDER = ["PASS", "WARN", "FAIL", "BLOCKED", "SKIP", "MANUAL"]
STATUS_ICON = {
    "PASS": "✅",
    "WARN": "⚠️",
    "FAIL": "❌",
    "BLOCKED": "🚫",
    "SKIP": "⏭",
    "MANUAL": "🔵",
}


# ── Parsing ───────────────────────────────────────────────────────────────────


def _parse_uat_results(path: Path = RESULTS_FILE) -> dict:
    """Parse UAT_RESULTS.md and return structured data."""
    if not path.exists():
        return {"error": f"{path} not found", "rows": [], "summary": {}, "run_ts": ""}

    text = path.read_text()

    # Run timestamp
    run_ts = ""
    m = re.search(r"\*\*Run:\*\* (.+?)\s*\n", text)
    if m:
        run_ts = m.group(1).strip()

    # Summary counts
    summary: dict[str, int] = {}
    for m in re.finditer(r"\*\*(\w+)\*\*: (\d+)", text):
        summary[m.group(1)] = int(m.group(2))

    # Result rows — format: | N | STATUS | [ID name](url) | `model` | detail | Ns |
    rows: list[dict] = []
    row_re = re.compile(
        r"^\|\s*\d+\s*\|\s*(\w+)\s*\|\s*\[([^\]]+)\]\(([^)]*)\)\s*\|"
        r"\s*`([^`]*)`\s*\|\s*(.*?)\s*\|\s*([\d.]+)s\s*\|"
    )
    for line in text.split("\n"):
        m = row_re.match(line)
        if not m:
            continue
        status = m.group(1)
        name = m.group(2).strip()
        url = m.group(3)
        model = m.group(4)
        detail = m.group(5)
        elapsed = float(m.group(6))

        # Extract test_id (first word) and section from name
        # Name is like "WS-01 Auto Router — ..." or "S3-P01 Tool use — ..."
        parts = name.split(None, 1)
        test_id = parts[0] if parts else name
        # Section prefix: WS, P-, S3, T-, M-, A-, etc.
        sec_m = re.match(r"([A-Z]{1,3})-?(\d+)?", test_id)
        section = sec_m.group(1) if sec_m else "OTHER"

        rows.append(
            {
                "test_id": test_id,
                "name": name,
                "status": status,
                "model": model,
                "detail": detail,
                "elapsed": elapsed,
                "url": url,
                "section": section,
            }
        )

    return {"run_ts": run_ts, "summary": summary, "rows": rows}


def _parse_corpus_runs(corpus_dir: Path = CORPUS_DIR, last_n: int = 10) -> list[dict]:
    """Parse UAT corpus JSONL files for trend data. Returns list of run summaries."""
    if not corpus_dir.exists():
        return []

    files = sorted(corpus_dir.glob("uat_*.jsonl"), key=lambda p: p.stat().st_mtime)
    files = files[-last_n:]

    runs = []
    for f in files:
        entries = []
        try:
            for line in f.read_text().split("\n"):
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        except Exception:
            continue
        if not entries:
            continue
        run_id = entries[0].get("corpus_run_id", f.stem.replace("uat_", ""))
        counts = Counter(e.get("status", "?") for e in entries)
        total = len(entries)
        pass_pct = round(100 * counts.get("PASS", 0) / total) if total else 0
        runs.append(
            {
                "run_id": run_id,
                "file": f.name,
                "total": total,
                "counts": dict(counts),
                "pass_pct": pass_pct,
                "timestamp": entries[0].get("timestamp", ""),
            }
        )
    return runs


# ── Dashboard builders ────────────────────────────────────────────────────────


def _section_table(rows: list[dict]) -> str:
    """By-section breakdown table."""
    sections: dict[str, Counter] = defaultdict(Counter)
    section_tests: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        sections[r["section"]][r["status"]] += 1
        if r["status"] in ("FAIL", "BLOCKED"):
            section_tests[r["section"]].append(r["test_id"])

    lines = [
        "",
        "## By Section",
        "",
        "| Section | Pass | Warn | Fail | Blocked | Skip | Total | Pass% |",
        "|---------|------|------|------|---------|------|-------|-------|",
    ]
    for sec in sorted(sections):
        c = sections[sec]
        total = sum(c.values())
        pass_pct = round(100 * c.get("PASS", 0) / total) if total else 0
        icon = "✅" if c.get("FAIL", 0) + c.get("BLOCKED", 0) == 0 else "❌"
        failing = ", ".join(section_tests[sec])[:40] if section_tests[sec] else ""
        lines.append(
            f"| {icon} {sec:<6} | {c.get('PASS', 0):<4} | {c.get('WARN', 0):<4} | "
            f"{c.get('FAIL', 0):<4} | {c.get('BLOCKED', 0):<7} | {c.get('SKIP', 0):<4} | "
            f"{total:<5} | {pass_pct}% |"
        )
    return "\n".join(lines)


def _model_table(rows: list[dict]) -> str:
    """By-model / workspace breakdown."""
    models: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        key = r["model"] or "unknown"
        # Shorten model names
        key = key.split("/")[-1] if "/" in key else key
        models[key][r["status"]] += 1

    # Sort by fail+blocked count desc, then total tests desc
    def sort_key(kv: tuple) -> tuple:
        c = kv[1]
        return (-(c.get("FAIL", 0) + c.get("BLOCKED", 0)), -sum(c.values()))

    lines = [
        "",
        "## By Model / Workspace",
        "",
        "| Model | Pass | Warn | Fail | Skip | Total | Pass% |",
        "|-------|------|------|------|------|-------|-------|",
    ]
    for model, c in sorted(models.items(), key=sort_key):
        total = sum(c.values())
        pass_pct = round(100 * c.get("PASS", 0) / total) if total else 0
        icon = (
            "✅"
            if c.get("FAIL", 0) + c.get("BLOCKED", 0) == 0
            else ("⚠️" if c.get("FAIL", 0) == 0 else "❌")
        )
        lines.append(
            f"| {icon} `{model[:40]}`  | {c.get('PASS', 0):<4} | {c.get('WARN', 0):<4} | "
            f"{c.get('FAIL', 0):<4} | {c.get('SKIP', 0):<4} | {total:<5} | {pass_pct}% |"
        )
    return "\n".join(lines)


def _failing_table(rows: list[dict]) -> str:
    """Detail table for FAIL, BLOCKED, WARN entries."""
    bad = [r for r in rows if r["status"] in ("FAIL", "BLOCKED", "WARN")]
    if not bad:
        return "\n## Failures & Warnings\n\nNone — clean run! 🎉\n"

    lines = [
        "",
        "## Failures & Warnings",
        "",
        "| Status | Test ID | Name | Model | Detail |",
        "|--------|---------|------|-------|--------|",
    ]
    for r in sorted(bad, key=lambda x: STATUS_ORDER.index(x["status"])):
        icon = STATUS_ICON.get(r["status"], r["status"])
        detail = r["detail"][:80].replace("|", "\\|")
        name = r["name"][:50].replace("|", "\\|")
        lines.append(
            f"| {icon} {r['status']:<7} | `{r['test_id']}`  | {name} | `{r['model'][:25]}` | {detail} |"
        )
    return "\n".join(lines)


def _trend_table(runs: list[dict]) -> str:
    """Multi-run trend from corpus JSONL files."""
    if not runs:
        return "\n## Trend (corpus runs)\n\nNo corpus data found.\n"

    lines = [
        "",
        "## Trend (UAT corpus runs — challenge + TV sections)",
        "",
        "| Run ID | Date | Pass | Warn | Fail | Blocked | Total | Pass% |",
        "|--------|------|------|------|------|---------|-------|-------|",
    ]
    for run in runs:
        c = run["counts"]
        ts = run["timestamp"][:10] if run["timestamp"] else run["run_id"][:10]
        lines.append(
            f"| `{run['run_id']}`  | {ts} | {c.get('PASS', 0):<4} | {c.get('WARN', 0):<4} | "
            f"{c.get('FAIL', 0):<4} | {c.get('BLOCKED', 0):<7} | {run['total']:<5} | {run['pass_pct']}% |"
        )
    return "\n".join(lines)


# ── Main dashboard output ─────────────────────────────────────────────────────


def build_dashboard(results: dict, trend_runs: list[dict]) -> str:
    """Assemble the full dashboard markdown string."""
    rows = results.get("rows", [])
    summary = results.get("summary", {})
    run_ts = results.get("run_ts", "unknown")
    total = len(rows)
    pass_ct = summary.get("PASS", 0)
    fail_ct = summary.get("FAIL", 0)
    warn_ct = summary.get("WARN", 0)
    blocked_ct = summary.get("BLOCKED", 0)
    skip_ct = summary.get("SKIP", 0)
    manual_ct = summary.get("MANUAL", 0)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    pass_pct = round(100 * pass_ct / total) if total else 0
    health = (
        "🟢 HEALTHY"
        if fail_ct + blocked_ct == 0
        else ("🟡 DEGRADED" if fail_ct <= 3 else "🔴 FAILING")
    )

    header = f"""# Portal 5 UAT Dashboard

**Generated:** {now}
**Source run:** {run_ts}
**Health:** {health}

## Summary

| Status | Count | Pct |
|--------|-------|-----|
| ✅ PASS    | {pass_ct:<5} | {pass_pct}% |
| ⚠️  WARN   | {warn_ct:<5} | {round(100 * warn_ct / total) if total else 0}% |
| ❌ FAIL    | {fail_ct:<5} | {round(100 * fail_ct / total) if total else 0}% |
| 🚫 BLOCKED | {blocked_ct:<5} | |
| ⏭ SKIP    | {skip_ct:<5} | |
| 🔵 MANUAL | {manual_ct:<5} | |
| **Total** | **{total}** | |
"""

    return (
        header
        + _section_table(rows)
        + _model_table(rows)
        + _failing_table(rows)
        + _trend_table(trend_runs)
        + "\n\n---\n*Generated by `tests/uat_dashboard.py` — source: `tests/UAT_RESULTS.md`*\n"
    )


def _print_terminal(results: dict, trend_runs: list[dict]) -> None:
    """Print a compact terminal summary (no markdown headers)."""
    rows = results.get("rows", [])
    summary = results.get("summary", {})
    run_ts = results.get("run_ts", "unknown")
    total = len(rows)

    print("=" * 90)
    print("Portal 5 — UAT Dashboard")
    print("=" * 90)
    print(f"Run:    {run_ts}")
    print(
        f"Result: {summary.get('PASS', 0)} PASS  {summary.get('WARN', 0)} WARN  "
        f"{summary.get('FAIL', 0)} FAIL  {summary.get('BLOCKED', 0)} BLOCKED  "
        f"{summary.get('SKIP', 0)} SKIP  {summary.get('MANUAL', 0)} MANUAL  |  {total} total"
    )
    print()

    # By-section table
    sections: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        sections[r["section"]][r["status"]] += 1
    print(
        f"{'Section':<10} {'Pass':>4} {'Warn':>4} {'Fail':>4} {'Blk':>4} {'Skip':>4} {'Total':>5} {'Pass%':>6}"
    )
    print("-" * 55)
    for sec in sorted(sections):
        c = sections[sec]
        t = sum(c.values())
        pct = round(100 * c.get("PASS", 0) / t) if t else 0
        icon = "✓" if c.get("FAIL", 0) + c.get("BLOCKED", 0) == 0 else "✗"
        print(
            f"{icon} {sec:<8} {c.get('PASS', 0):>4} {c.get('WARN', 0):>4} {c.get('FAIL', 0):>4} "
            f"{c.get('BLOCKED', 0):>4} {c.get('SKIP', 0):>4} {t:>5} {pct:>5}%"
        )
    print()

    # Failing / warning tests
    bad = [r for r in rows if r["status"] in ("FAIL", "BLOCKED", "WARN")]
    if bad:
        print(f"{'Status':<9} {'Test ID':<15} {'Name':<45} {'Model':<25}")
        print("-" * 95)
        for r in sorted(bad, key=lambda x: STATUS_ORDER.index(x["status"])):
            name = r["name"][:44]
            model = r["model"][:24]
            print(f"{r['status']:<9} {r['test_id']:<15} {name:<45} {model:<25}")
    else:
        print("No failures or warnings — clean run!")
    print()

    # Trend (corpus)
    if trend_runs:
        print(
            f"{'Run ID':<22} {'Date':<12} {'Pass':>4} {'Warn':>4} {'Fail':>4} {'Total':>5} {'Pass%':>6}"
        )
        print("-" * 60)
        for run in trend_runs:
            c = run["counts"]
            ts = run["timestamp"][:10] if run["timestamp"] else run["run_id"][:10]
            print(
                f"{run['run_id']:<22} {ts:<12} {c.get('PASS', 0):>4} {c.get('WARN', 0):>4} "
                f"{c.get('FAIL', 0):>4} {run['total']:>5} {run['pass_pct']:>5}%"
            )
    print("=" * 90)


def main() -> None:
    parser = argparse.ArgumentParser(description="Portal 5 UAT Dashboard")
    parser.add_argument("--md", action="store_true", help=f"Write {DASHBOARD_FILE}")
    parser.add_argument(
        "--trend",
        type=int,
        default=8,
        metavar="N",
        help="Number of recent corpus runs to include in trend (default: 8)",
    )
    parser.add_argument("--input", default=str(RESULTS_FILE), help="Path to UAT_RESULTS.md")
    args = parser.parse_args()

    results = _parse_uat_results(Path(args.input))
    if "error" in results:
        print(f"Error: {results['error']}", file=sys.stderr)
        sys.exit(1)

    trend_runs = _parse_corpus_runs(last_n=args.trend)

    if args.md:
        md = build_dashboard(results, trend_runs)
        DASHBOARD_FILE.write_text(md)
        print(f"Dashboard written to {DASHBOARD_FILE}")
    else:
        _print_terminal(results, trend_runs)


if __name__ == "__main__":
    main()
