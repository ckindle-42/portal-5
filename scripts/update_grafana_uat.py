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
from pathlib import Path

from lib.grafana_panels import (
    GRAY,
    GREEN,
    RED,
    YELLOW,
    failures_panel,
    metadata_panel,
    section_table,
    summary_panel,
    trend_table,
)

PROJECT_ROOT = Path(__file__).parent.parent
DASHBOARD_PATH = PROJECT_ROOT / "config/grafana/dashboards/portal5_uat.json"
RESULTS_FILE = PROJECT_ROOT / "tests/UAT_RESULTS.md"
CORPUS_DIR = PROJECT_ROOT / "tests/uat_corpus"

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
        runs.append(
            {
                "run_id": run_id,
                "total": total,
                "counts": dict(counts),
                "pass_pct": pass_pct,
                "timestamp": entries[0].get("timestamp", ""),
            }
        )
    return runs


# ── Panel assembly ────────────────────────────────────────────────────────────


def _build_summary_panel(summary: dict, total: int) -> str:
    return summary_panel(
        summary,
        total,
        eligible_extra=("SKIP", "MANUAL"),
        legend_extra=(
            ("SKIP", GRAY, "excluded from this run (fixture missing, env gate)"),
            ("MANUAL", "#555", "requires human verification, not scored"),
        ),
        pass_rate_note="Pass rate = PASS ÷ eligible (excludes SKIP &amp; MANUAL)",
    )


def _build_metadata_panel(run_ts: str, total: int, fail_ct: int, blocked_ct: int) -> str:
    return metadata_panel(
        [("Source run", run_ts), ("Total tests", str(total))],
        fail_ct=fail_ct,
        blocked_ct=blocked_ct,
    )


_SECTION_DESCRIPTIONS: dict[str, str] = {
    "WS": "Workspace routing — end-to-end intent detection, model assignment, and workspace-level feature tests (WS-DD daily driver, WS-MATH, WS-TOOLS)",
    "P": "Persona behavioral — individual persona response quality, tone, format, and domain expertise (P-W writing, P-V vision, P-S security, P-R reasoning, P-N creative, P-DA data, P-B browser, P-TOOLS tool-use)",
    "TV": "Tool Validation — proof-of-execution tests; correct answer requires the tool to have actually run (execute_python, execute_bash, read_excel, read_pdf, read_powerpoint, read_word_document)",
    "T": "Tool functional — document generation (DOCX, XLSX, PPTX), file read/write, web search, code execution end-to-end",
    "CC": "Cross-capability benchmark — CC-01 persona suite run against each model in the fleet; validates routing, system prompt injection, and model-specific behavior",
    "A": "Agentic multi-step — autonomous task chains, memory store/recall, multi-tool orchestration, and long-horizon planning",
    "M": "Media — audio transcription (Whisper STT), text-to-speech (TTS/Kokoro), and voice workflow integration",
    "S": "Security workspace — vulnerability analysis, threat modeling, CVE lookup via SearXNG, and NERC/CIP compliance",
    "TR": "Transcription workflow — single-pass diarized speaker transcription (VibeVoice-ASR), transcript formatting, and downstream document creation",
    "EX": "Extended / exploratory — edge-case and regression tests outside the main catalog",
    "BT": "Benchmark targeted — single-model deep-dive tests run against a specific model build (e.g., Foundation-Sec-8B-Reasoning); not part of the general fleet sweep",
    "DD": "Daily Driver Tool Validation — tool-proof tests run inside the daily-driver workspace to confirm general-purpose models can invoke tools, not just specialist workspaces",
}


def _build_section_table(rows: list[dict]) -> str:
    return section_table(
        rows,
        _SECTION_DESCRIPTIONS,
        eligible_extra=("SKIP", "MANUAL"),
        max_height=480,
        desc_max=80,
        desc_width=260,
        summary_text="Section key — what each prefix covers",
    )


def _build_model_table(rows: list[dict]) -> str:
    models: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        key = (r["model"] or "unknown").split("/")[-1]
        models[key][r["status"]] += 1

    def sort_key(kv: tuple) -> tuple:
        c = kv[1]
        return (-(c.get("FAIL", 0) + c.get("BLOCKED", 0)), -sum(c.values()))

    legend_html = (
        '<div style="font-size:10px;color:#666;padding:4px 0 8px 0;border-bottom:1px solid #333;margin-bottom:6px">'
        '<b style="color:#888">How to read this table:</b> Each row is a <b>persona slug</b> — the named AI assistant '
        "used for that test (e.g. <code>auto-documents</code>, <code>statistician</code>, <code>pentester</code>). "
        "Persona slugs are Open WebUI model presets defined in <code>config/personas/</code>; each maps to an "
        "Ollama model via workspace routing. Rows are sorted by failures first (worst → best), then by test count. "
        "A persona appearing in this table ran at least one test; its pass% reflects how well that model+system-prompt "
        "combination performed across all tasks assigned to it."
        "</div>"
    )

    header = (
        '<tr style="background:#1f1f1f;position:sticky;top:0">'
        '<th style="text-align:left">Persona / Workspace slug</th>'
        '<th style="text-align:left">Pass</th>'
        '<th style="text-align:right">Warn</th>'
        '<th style="text-align:right">Fail</th>'
        '<th style="text-align:right">Total</th>'
        '<th style="text-align:left;min-width:120px">Pass%</th></tr>'
    )
    from lib.grafana_panels import bar

    table_rows = []
    for i, (model, c) in enumerate(sorted(models.items(), key=sort_key)):
        total = sum(c.values())
        pass_ct = c.get("PASS", 0)
        fail_ct = c.get("FAIL", 0) + c.get("BLOCKED", 0)
        eligible = total - c.get("SKIP", 0) - c.get("MANUAL", 0)
        warn_only = fail_ct == 0 and pass_ct == 0 and c.get("WARN", 0) > 0
        color = RED if fail_ct > 0 else (YELLOW if warn_only else GREEN)
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        table_rows.append(
            f"<tr{bg}>"
            f'<td style="font-family:monospace;color:{color}">{model[:42]}</td>'
            f'<td style="color:{GREEN if pass_ct > 0 else GRAY}">{pass_ct}</td>'
            f'<td style="text-align:right;color:{YELLOW}">{c.get("WARN", 0)}</td>'
            f'<td style="text-align:right;color:{RED}">{c.get("FAIL", 0)}</td>'
            f'<td style="text-align:right">{total}</td>'
            f"<td>{bar(pass_ct, eligible, color)}</td></tr>"
        )
    return (
        f"{legend_html}"
        '<div style="overflow:auto;max-height:480px">'
        '<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(table_rows)}</table></div>"
    )


def _build_failures_table(rows: list[dict]) -> str:
    html, _count = failures_panel(
        rows,
        status_order=STATUS_ORDER,
        status_color=STATUS_COLOR,
        id_key="test_id",
        name_key="name",
        detail_max=90,
        max_height=580,
        extra_cells=[("model", "")],
    )
    return html


def _build_trend_table(runs: list[dict]) -> str:
    return trend_table(
        runs,
        empty_note="No corpus JSONL files found in tests/uat_corpus/.",
        include_sha=False,
        include_blk=False,
        max_height=280,
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
        f"{pass_ct} PASS, {summary.get('WARN', 0)} WARN, {fail_ct} FAIL, "
        f"{blocked_ct} BLOCKED, {summary.get('SKIP', 0)} SKIP"
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
