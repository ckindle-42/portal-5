#!/usr/bin/env python3
"""Update portal5_uat.json Grafana dashboard from UAT_RESULTS.md.

Usage:
    python3 scripts/update_grafana_uat.py
    python3 scripts/update_grafana_uat.py --dry-run
    python3 scripts/update_grafana_uat.py --input tests/UAT_RESULTS.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DASHBOARD_PATH = PROJECT_ROOT / "config/grafana/dashboards/portal5_uat.json"
RESULTS_FILE = PROJECT_ROOT / "tests/UAT_RESULTS.md"
CORPUS_DIR = PROJECT_ROOT / "tests/uat_corpus"

GREEN = "#73BF69"
YELLOW = "#FFD700"
RED = "#F2495C"
GRAY = "#888888"

STATUS_ORDER = ["PASS", "WARN", "FAIL", "BLOCKED", "SKIP", "MANUAL"]
STATUS_COLOR = {
    "PASS": GREEN,
    "WARN": YELLOW,
    "FAIL": RED,
    "BLOCKED": GRAY,
    "SKIP": GRAY,
    "MANUAL": "#6b9cd4",
}


# ── Parsing (mirrors tests/uat_dashboard.py) ──────────────────────────────────


def _parse_uat_results(path: Path) -> dict:
    if not path.exists():
        return {"error": f"{path} not found", "rows": [], "summary": {}, "run_ts": ""}

    text = path.read_text()

    run_ts = ""
    m = re.search(r"\*\*Run:\*\* (.+?)\s*\n", text)
    if m:
        run_ts = m.group(1).strip()

    summary: dict[str, int] = {}
    for m in re.finditer(r"\*\*(\w+)\*\*: (\d+)", text):
        summary[m.group(1)] = int(m.group(2))

    row_re = re.compile(
        r"^\|\s*\d+\s*\|\s*(\w+)\s*\|\s*\[([^\]]+)\]\(([^)]*)\)\s*\|"
        r"\s*`([^`]*)`\s*\|\s*(.*?)\s*\|\s*([\d.]+)s\s*\|"
    )
    rows: list[dict] = []
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
        parts = name.split(None, 1)
        test_id = parts[0] if parts else name
        sec_m = re.match(r"([A-Z]{1,3})-?(\d+)?", test_id)
        section = sec_m.group(1) if sec_m else "OTHER"
        rows.append({
            "test_id": test_id,
            "name": name,
            "status": status,
            "model": model,
            "detail": detail,
            "elapsed": elapsed,
            "url": url,
            "section": section,
        })
    return {"run_ts": run_ts, "summary": summary, "rows": rows}


def _parse_corpus_runs(corpus_dir: Path, last_n: int = 10) -> list[dict]:
    if not corpus_dir.exists():
        return []
    files = sorted(corpus_dir.glob("uat_*.jsonl"), key=lambda p: p.stat().st_mtime)[-last_n:]
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
        eligible = total - counts.get("SKIP", 0) - counts.get("MANUAL", 0)
        pass_pct = round(100 * counts.get("PASS", 0) / eligible) if eligible else 0
        runs.append({
            "run_id": run_id,
            "total": total,
            "counts": dict(counts),
            "pass_pct": pass_pct,
            "timestamp": entries[0].get("timestamp", ""),
        })
    return runs


# ── Panel builders ────────────────────────────────────────────────────────────


def _bar(filled: int, total: int, color: str = GREEN) -> str:
    pct = max(1, min(100, round(filled / total * 100))) if total > 0 else 0
    return (
        f'<div style="display:flex;align-items:center;gap:4px">'
        f'<span style="width:42px;text-align:right;font-weight:bold;color:{color}">{filled}/{total}</span>'
        f'<div style="background:{color};height:8px;width:{pct}%;min-width:2px;border-radius:2px;max-width:80px"></div>'
        f'<span style="color:#888;font-size:10px">{pct}%</span></div>'
    )


def _build_summary_panel(summary: dict, total: int) -> str:
    pass_ct = summary.get("PASS", 0)
    warn_ct = summary.get("WARN", 0)
    fail_ct = summary.get("FAIL", 0)
    blocked_ct = summary.get("BLOCKED", 0)
    skip_ct = summary.get("SKIP", 0)
    manual_ct = summary.get("MANUAL", 0)
    eligible = total - skip_ct - manual_ct
    pct = round(100 * pass_ct / eligible) if eligible else 0
    pass_color = GREEN if fail_ct + blocked_ct == 0 else (YELLOW if fail_ct <= 3 else RED)

    legend = (
        '<div style="font-size:10px;color:#666;margin-top:10px;text-align:left;'
        'padding:6px 12px;border-top:1px solid #333;display:flex;gap:16px;flex-wrap:wrap">'
        f'<span><b style="color:{GREEN}">PASS</b> — all assertions satisfied</span>'
        f'<span><b style="color:{YELLOW}">WARN</b> — non-critical assertions failed (critical passed)</span>'
        f'<span><b style="color:{RED}">FAIL</b> — one or more critical assertions failed</span>'
        f'<span><b style="color:{GRAY}">BLOCKED</b> — test could not run (infra/model unavailable)</span>'
        f'<span><b style="color:{GRAY}">SKIP</b> — excluded from this run (fixture missing, env gate)</span>'
        f'<span><b style="color:#555">MANUAL</b> — requires human verification, not scored</span>'
        f'<span style="color:#555">Pass rate = PASS ÷ eligible (excludes SKIP &amp; MANUAL)</span>'
        '</div>'
    )

    return (
        '<div style="display:flex;flex-direction:column;justify-content:center;height:100%">'
        '<div style="display:flex;justify-content:space-around;align-items:center;'
        'text-align:center;font-size:14px;padding:8px 0">'
        f'<div><div style="font-size:28px;font-weight:bold;color:{GREEN}">{pass_ct}</div>'
        f'<div style="color:#aaa">PASS</div></div>'
        f'<div><div style="font-size:28px;font-weight:bold;color:{YELLOW}">{warn_ct}</div>'
        f'<div style="color:#aaa">WARN</div></div>'
        f'<div><div style="font-size:28px;font-weight:bold;color:{RED}">{fail_ct}</div>'
        f'<div style="color:#aaa">FAIL</div></div>'
        f'<div><div style="font-size:28px;font-weight:bold;color:{GRAY}">{blocked_ct}</div>'
        f'<div style="color:#aaa">BLOCKED</div></div>'
        f'<div><div style="font-size:28px;font-weight:bold;color:{GRAY}">{skip_ct}</div>'
        f'<div style="color:#aaa">SKIP</div></div>'
        f'<div><div style="font-size:28px;font-weight:bold;color:#555">{manual_ct}</div>'
        f'<div style="color:#aaa">MANUAL</div></div>'
        f'<div><div style="font-size:28px;font-weight:bold;color:{pass_color}">{pass_ct}/{eligible}</div>'
        f'<div style="color:#aaa">Pass Rate ({pct}%)</div></div>'
        '</div>'
        f'{legend}'
        '</div>'
    )


def _build_metadata_panel(run_ts: str, total: int, fail_ct: int, blocked_ct: int) -> str:
    health = "🟢 HEALTHY" if fail_ct + blocked_ct == 0 else (
        "🟡 DEGRADED" if fail_ct <= 3 else "🔴 FAILING"
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        '<div style="font-size:11px;color:#888;padding:2px 8px;display:flex;gap:16px;flex-wrap:wrap">'
        f"<span><b>Source run:</b> {run_ts}</span>"
        f"<span><b>Health:</b> {health}</span>"
        f"<span><b>Total tests:</b> {total}</span>"
        f"<span><b>Dashboard updated:</b> {now}</span>"
        "</div>"
    )


def _build_section_table(rows: list[dict]) -> str:
    sections: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        sections[r["section"]][r["status"]] += 1

    header = (
        '<tr style="background:#1f1f1f;position:sticky;top:0">'
        '<th style="text-align:left">Section'
        '<th style="text-align:left">Pass'
        '<th style="text-align:right">Warn'
        '<th style="text-align:right">Fail'
        '<th style="text-align:right">Blk'
        '<th style="text-align:right">Total'
        '<th style="text-align:left;min-width:100px">Pass%</tr>'
    )
    table_rows = []
    for i, sec in enumerate(sorted(sections)):
        c = sections[sec]
        total = sum(c.values())
        pass_ct = c.get("PASS", 0)
        fail_ct = c.get("FAIL", 0) + c.get("BLOCKED", 0)
        eligible = total - c.get("SKIP", 0) - c.get("MANUAL", 0)
        pct = round(100 * pass_ct / eligible) if eligible else 0
        color = GREEN if fail_ct == 0 else (YELLOW if c.get("FAIL", 0) == 0 else RED)
        icon = "✓" if fail_ct == 0 else "✗"
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        table_rows.append(
            f"<tr{bg}>"
            f'<td style="font-family:monospace;color:{color}">{icon} {sec}</td>'
            f'<td style="color:{GREEN}">{pass_ct}</td>'
            f'<td style="text-align:right;color:{YELLOW}">{c.get("WARN",0)}</td>'
            f'<td style="text-align:right;color:{RED}">{c.get("FAIL",0)}</td>'
            f'<td style="text-align:right;color:{GRAY}">{c.get("BLOCKED",0)}</td>'
            f'<td style="text-align:right">{total}</td>'
            f"<td>{_bar(pass_ct, total, color)}</td></tr>"
        )
    return (
        '<div style="overflow:auto;max-height:550px">'
        '<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(table_rows)}</table></div>"
    )


def _build_model_table(rows: list[dict]) -> str:
    models: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        key = (r["model"] or "unknown").split("/")[-1]
        models[key][r["status"]] += 1

    def sort_key(kv: tuple) -> tuple:
        c = kv[1]
        return (-(c.get("FAIL", 0) + c.get("BLOCKED", 0)), -sum(c.values()))

    header = (
        '<tr style="background:#1f1f1f;position:sticky;top:0">'
        '<th style="text-align:left">Model / Workspace'
        '<th style="text-align:left">Pass'
        '<th style="text-align:right">Warn'
        '<th style="text-align:right">Fail'
        '<th style="text-align:right">Total'
        '<th style="text-align:left;min-width:120px">Pass%</tr>'
    )
    table_rows = []
    for i, (model, c) in enumerate(sorted(models.items(), key=sort_key)):
        total = sum(c.values())
        pass_ct = c.get("PASS", 0)
        fail_ct = c.get("FAIL", 0) + c.get("BLOCKED", 0)
        pct = round(100 * pass_ct / total) if total else 0
        color = GREEN if fail_ct == 0 else (YELLOW if c.get("FAIL", 0) == 0 else RED)
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        table_rows.append(
            f"<tr{bg}>"
            f'<td style="font-family:monospace;color:{color}">{model[:42]}</td>'
            f'<td style="color:{GREEN}">{pass_ct}</td>'
            f'<td style="text-align:right;color:{YELLOW}">{c.get("WARN",0)}</td>'
            f'<td style="text-align:right;color:{RED}">{c.get("FAIL",0)}</td>'
            f'<td style="text-align:right">{total}</td>'
            f"<td>{_bar(pass_ct, total, color)}</td></tr>"
        )
    return (
        '<div style="overflow:auto;max-height:550px">'
        '<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(table_rows)}</table></div>"
    )


def _build_failures_table(rows: list[dict]) -> str:
    bad = [r for r in rows if r["status"] in ("FAIL", "BLOCKED", "WARN")]
    if not bad:
        return f'<div style="padding:16px;text-align:center;color:{GREEN};font-size:14px">✅ No failures or warnings — clean run!</div>'

    header = (
        '<tr style="background:#1f1f1f;position:sticky;top:0">'
        '<th style="text-align:left">Status'
        '<th style="text-align:left">Test ID'
        '<th style="text-align:left">Name'
        '<th style="text-align:left">Model'
        '<th style="text-align:left">Detail</tr>'
    )
    table_rows = []
    for i, r in enumerate(sorted(bad, key=lambda x: STATUS_ORDER.index(x["status"]))):
        color = STATUS_COLOR.get(r["status"], GRAY)
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        url = r.get("url", "")
        name_cell = (
            f'<a href="{url}" style="color:#6b9cd4;text-decoration:none">{r["name"][:60]}</a>'
            if url else r["name"][:60]
        )
        detail = r["detail"][:90].replace("<", "&lt;").replace(">", "&gt;")
        table_rows.append(
            f"<tr{bg}>"
            f'<td style="color:{color};font-weight:bold">{r["status"]}</td>'
            f'<td style="font-family:monospace;white-space:nowrap">{r["test_id"]}</td>'
            f"<td>{name_cell}</td>"
            f'<td style="font-family:monospace;color:#aaa">{r["model"][:28]}</td>'
            f'<td style="color:#888;font-size:10px">{detail}</td></tr>'
        )
    return (
        '<div style="overflow:auto;max-height:580px">'
        '<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(table_rows)}</table></div>"
    )


def _build_trend_table(runs: list[dict]) -> str:
    if not runs:
        return '<div style="padding:8px;color:#888">No corpus JSONL files found in tests/uat_corpus/.</div>'

    peak_pass = max((r["pass_pct"] for r in runs), default=0)

    header = (
        '<tr style="background:#1f1f1f">'
        '<th style="text-align:left">Run ID'
        '<th style="text-align:left">Date'
        '<th style="text-align:right">Pass'
        '<th style="text-align:right">Warn'
        '<th style="text-align:right">Fail'
        '<th style="text-align:right">Total'
        '<th style="text-align:left;min-width:140px">Pass%</tr>'
    )
    table_rows = []
    for i, run in enumerate(runs):
        c = run["counts"]
        ts = run["timestamp"][:10] if run["timestamp"] else run["run_id"][:10]
        pct = run["pass_pct"]
        color = GREEN if pct >= 90 else (YELLOW if pct >= 70 else RED)
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        total = run["total"]
        table_rows.append(
            f"<tr{bg}>"
            f'<td style="font-family:monospace;font-size:10px">{run["run_id"]}</td>'
            f"<td>{ts}</td>"
            f'<td style="text-align:right;color:{GREEN}">{c.get("PASS",0)}</td>'
            f'<td style="text-align:right;color:{YELLOW}">{c.get("WARN",0)}</td>'
            f'<td style="text-align:right;color:{RED}">{c.get("FAIL",0)}</td>'
            f"<td style=\"text-align:right\">{total}</td>"
            f"<td>{_bar(c.get('PASS',0), total, color)}</td></tr>"
        )
    return (
        '<div style="overflow:auto;max-height:280px">'
        '<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(table_rows)}</table></div>"
    )


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update Grafana UAT dashboard from UAT_RESULTS.md."
    )
    parser.add_argument("--input", default=str(RESULTS_FILE), help="Path to UAT_RESULTS.md")
    parser.add_argument("--dry-run", action="store_true", help="Print summary but do not write")
    args = parser.parse_args()

    data = _parse_uat_results(Path(args.input))
    if "error" in data:
        print(f"Error: {data['error']}", file=sys.stderr)
        sys.exit(1)

    rows = data["rows"]
    summary = data["summary"]
    run_ts = data["run_ts"]
    total = len(rows)
    fail_ct = summary.get("FAIL", 0)
    blocked_ct = summary.get("BLOCKED", 0)
    pass_ct = summary.get("PASS", 0)

    trend_runs = _parse_corpus_runs(CORPUS_DIR, last_n=10)

    print(
        f"UAT results: {total} tests — "
        f"{pass_ct} PASS, {summary.get('WARN',0)} WARN, {fail_ct} FAIL, "
        f"{blocked_ct} BLOCKED, {summary.get('SKIP',0)} SKIP"
    )
    print(f"Corpus runs found: {len(trend_runs)}")

    if args.dry_run:
        print("Dry run — dashboard not updated.")
        return

    with open(DASHBOARD_PATH) as f:
        dashboard = json.load(f)

    summary_html = _build_summary_panel(summary, total)
    metadata_html = _build_metadata_panel(run_ts, total, fail_ct, blocked_ct)
    section_html = _build_section_table(rows)
    model_html = _build_model_table(rows)
    failures_html = _build_failures_table(rows)
    trend_html = _build_trend_table(trend_runs)

    for panel in dashboard["panels"]:
        pid = panel.get("id")
        if pid == 1:
            panel["options"]["content"] = summary_html
        elif pid == 2:
            panel["options"]["content"] = metadata_html
        elif pid == 10:
            panel["options"]["content"] = section_html
        elif pid == 20:
            panel["options"]["content"] = model_html
        elif pid == 30:
            bad_count = sum(1 for r in rows if r["status"] in ("FAIL", "BLOCKED", "WARN"))
            panel["title"] = f"Failures & Warnings ({bad_count})"
            panel["options"]["content"] = failures_html
        elif pid == 40:
            panel["title"] = f"Run Trend — last {len(trend_runs)} corpus runs"
            panel["options"]["content"] = trend_html

    dashboard["version"] = dashboard.get("version", 0) + 1

    with open(DASHBOARD_PATH, "w") as f:
        json.dump(dashboard, f, indent=2)

    print(f"Dashboard updated: {DASHBOARD_PATH}  (version {dashboard['version']})")


if __name__ == "__main__":
    main()
