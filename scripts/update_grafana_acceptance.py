#!/usr/bin/env python3
"""Update portal5_acceptance.json Grafana dashboard from ACCEPTANCE_RESULTS.md.

Also archives a JSONL snapshot to tests/acceptance_corpus/ for trend tracking.

Usage:
    python3 scripts/update_grafana_acceptance.py
    python3 scripts/update_grafana_acceptance.py --dry-run
    python3 scripts/update_grafana_acceptance.py --input tests/ACCEPTANCE_RESULTS.md
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
DASHBOARD_PATH = PROJECT_ROOT / "config/grafana/dashboards/portal5_acceptance.json"
RESULTS_FILE = PROJECT_ROOT / "tests/ACCEPTANCE_RESULTS.md"
CORPUS_DIR = PROJECT_ROOT / "tests/acceptance_corpus"

GREEN = "#73BF69"
YELLOW = "#FFD700"
RED = "#F2495C"
GRAY = "#888888"

STATUS_ORDER = ["PASS", "WARN", "FAIL", "BLOCKED", "INFO"]
STATUS_COLOR = {
    "PASS": GREEN,
    "WARN": YELLOW,
    "FAIL": RED,
    "BLOCKED": GRAY,
    "INFO": "#6b9cd4",
}

_SECTION_DESCRIPTIONS: dict[str, str] = {
    "S0":  "Prerequisites — Python version, required packages, .env file, Git repo",
    "S1":  "Config consistency — backends.yaml, workspace IDs vs WORKSPACES, persona catalog, model hint reachability",
    "S2":  "Service health — Docker, Ollama, Open WebUI, SearXNG, Prometheus, Grafana, all MCP + MLX services",
    "S3a": "Workspace routing (production) — 21 workspaces (20 auto-* + tools-specialist): routing, content signal, served model match",
    "S4":  "Document generation MCP (:8913) — Word, Excel, PowerPoint generation end-to-end",
    "S5":  "Code sandbox MCP (:8914) — Python/Bash execution, sandboxed isolation",
    "S6":  "Security workspaces — auto-blueteam and auto-compliance routing + content signal",
    "S7":  "Music generation MCP (:8912) — MusicGen end-to-end",
    "S8":  "Text-to-Speech — MLX speech server Kokoro/Qwen3-TTS (:8918)",
    "S9":  "Speech-to-Text — MLX transcribe mlx-whisper + pyannote diarization (:8924)",
    "S10": "Personas (Ollama) — 86 non-bench personas grouped by Ollama model, behavioral signal",
    "S10c":"Compliance personas — 7 NERC/CIP compliance scenarios via fixture",
    "S12": "Web search — SearXNG integration, search result quality",
    "S13": "RAG/Embedding — MLX embedding (:8917) + Qwen3-Reranker (:8925) two-stage retrieval",
    "S15": "Shared workspace — /workspace mounts, OWUI uploads bind, AUDIO_STT_ENGINE gate",
    "S16": "Security MCP (CIRCL VLAI) — vulnerability classification end-to-end (:8919)",
    "S21": "LLM Intent Router — Llama-3.2-3B intent classifier accuracy across workspace categories",
    "S23": "Model diversity — Ollama catalog coverage, all 68+ unique models reachable",
    "S30": "Image generation — ComfyUI/FLUX end-to-end (:8910/:8188)",
    "S31": "Video generation — Wan2.2 end-to-end (:8911)",
    "S40": "Metrics/monitoring — Prometheus metrics, Grafana health, pipeline /metrics",
    "S41": "Production hardening — concurrency slots, request lifecycle, error surface",
    "S42": "Browser automation — Playwright MCP (:8923) navigation and extraction",
    "S50": "Negative testing — empty/oversized prompts, invalid models, malformed JSON, auth",
    "S60": "Tool-calling orchestration — MCP tool dispatch end-to-end, tool-loop correctness",
    "S70": "Information access MCPs — memory (:8920), research (:8922), browser (:8923)",
    "S3":  "Workspace routing wrapper (runs S3a)",
}


# ── Parsing ───────────────────────────────────────────────────────────────────


def _parse_results(path: Path) -> dict:
    if not path.exists():
        return {"error": f"{path} not found", "rows": [], "meta": {}}

    text = path.read_text()

    meta: dict[str, str] = {}
    for field in ("Date", "Git SHA", "Sections", "Runtime"):
        m = re.search(rf"\*\*{field}:\*\*\s*(.+?)(?:\s*\n|\s*$)", text, re.MULTILINE)
        if m:
            meta[field] = m.group(1).strip()

    # Row format: | Section | ID | Name | {icon} STATUS | detail | dur |
    row_re = re.compile(
        r"^\|\s*(\S+)\s*\|\s*([\w.-]+)\s*\|\s*(.+?)\s*\|"
        r"\s*(?:[^\|\w]*)?(PASS|FAIL|WARN|INFO|BLOCKED)\s*\|\s*(.*?)\s*\|\s*([\d.]+)s\s*\|"
    )
    rows: list[dict] = []
    for line in text.split("\n"):
        m = row_re.match(line)
        if not m:
            continue
        section = m.group(1).strip()
        tid = m.group(2).strip()
        name = m.group(3).strip()
        status = m.group(4).strip()
        detail = m.group(5).strip()
        elapsed = float(m.group(6))
        if section in ("Section", "---"):
            continue
        rows.append({
            "section": section,
            "tid": tid,
            "name": name,
            "status": status,
            "detail": detail,
            "elapsed": elapsed,
        })

    return {"meta": meta, "rows": rows}


def _parse_corpus_runs(corpus_dir: Path, last_n: int = 10) -> list[dict]:
    if not corpus_dir.exists():
        return []
    files = sorted(corpus_dir.glob("acceptance_*.jsonl"), key=lambda p: p.stat().st_mtime)[-last_n:]
    runs = []
    for f in files:
        entries: list[dict] = []
        try:
            for line in f.read_text().split("\n"):
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        except Exception:
            continue
        if not entries:
            continue
        run_id = entries[0].get("run_id", f.stem.replace("acceptance_", ""))
        counts = Counter(e.get("status", "?") for e in entries)
        total = len(entries)
        eligible = total - counts.get("INFO", 0)
        pass_pct = round(100 * counts.get("PASS", 0) / eligible) if eligible else 0
        runs.append({
            "run_id": run_id,
            "git_sha": entries[0].get("git_sha", ""),
            "date": entries[0].get("date", ""),
            "total": total,
            "counts": dict(counts),
            "pass_pct": pass_pct,
        })
    return runs


def _archive_corpus(rows: list[dict], meta: dict) -> Path | None:
    """Write a JSONL snapshot to tests/acceptance_corpus/ for trend tracking."""
    if not rows:
        return None
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    git_sha = meta.get("Git SHA", "unknown")
    date = meta.get("Date", "")
    out = CORPUS_DIR / f"acceptance_{run_id}.jsonl"
    lines = [
        json.dumps({
            "run_id": run_id,
            "git_sha": git_sha,
            "date": date,
            "section": r["section"],
            "tid": r["tid"],
            "name": r["name"],
            "status": r["status"],
            "detail": r["detail"][:120],
            "elapsed": r["elapsed"],
        })
        for r in rows
    ]
    out.write_text("\n".join(lines) + "\n")
    return out


# ── Panel builders ────────────────────────────────────────────────────────────


def _bar(filled: int, total: int, color: str = GREEN) -> str:
    if total == 0:
        return '<div style="color:#555;font-size:10px">n/a</div>'
    pct = round(filled / total * 100)
    bar_color = color if filled > 0 else RED
    bar_width = pct if filled > 0 else 0
    return (
        f'<div style="display:flex;align-items:center;gap:4px">'
        f'<span style="width:42px;text-align:right;font-weight:bold;color:{bar_color}">{filled}/{total}</span>'
        f'<div style="background:{bar_color};height:8px;width:{bar_width}%;border-radius:2px;max-width:80px"></div>'
        f'<span style="color:#888;font-size:10px">{pct}%</span></div>'
    )


def _build_summary_panel(rows: list[dict]) -> str:
    counts: Counter = Counter(r["status"] for r in rows)
    total = len(rows)
    pass_ct = counts.get("PASS", 0)
    warn_ct = counts.get("WARN", 0)
    fail_ct = counts.get("FAIL", 0)
    blocked_ct = counts.get("BLOCKED", 0)
    info_ct = counts.get("INFO", 0)
    eligible = total - info_ct
    pct = round(100 * pass_ct / eligible) if eligible else 0
    pass_color = GREEN if fail_ct + blocked_ct == 0 else (YELLOW if fail_ct <= 3 else RED)

    legend = (
        '<div style="font-size:10px;color:#666;margin-top:10px;text-align:left;'
        'padding:6px 12px;border-top:1px solid #333;display:flex;gap:16px;flex-wrap:wrap">'
        f'<span><b style="color:{GREEN}">PASS</b> — all assertions satisfied</span>'
        f'<span><b style="color:{YELLOW}">WARN</b> — non-critical issue (critical passed)</span>'
        f'<span><b style="color:{RED}">FAIL</b> — critical assertion failed</span>'
        f'<span><b style="color:{GRAY}">BLOCKED</b> — test could not run (infra/model unavailable)</span>'
        f'<span style="color:#555">Pass rate = PASS ÷ eligible (excludes INFO)</span>'
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
        f'<div><div style="font-size:28px;font-weight:bold;color:{pass_color}">{pass_ct}/{eligible}</div>'
        f'<div style="color:#aaa">Pass Rate ({pct}%)</div></div>'
        '</div>'
        f'{legend}'
        '</div>'
    )


def _build_metadata_panel(meta: dict, rows: list[dict]) -> str:
    counts: Counter = Counter(r["status"] for r in rows)
    fail_ct = counts.get("FAIL", 0)
    blocked_ct = counts.get("BLOCKED", 0)
    total = len(rows)
    health = "🟢 HEALTHY" if fail_ct + blocked_ct == 0 else (
        "🟡 DEGRADED" if fail_ct <= 3 else "🔴 FAILING"
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    date = meta.get("Date", "unknown")
    sha = meta.get("Git SHA", "unknown")
    runtime = meta.get("Runtime", "unknown")
    sections = meta.get("Sections", "unknown")
    return (
        '<div style="font-size:11px;color:#888;padding:2px 8px;display:flex;gap:16px;flex-wrap:wrap">'
        f"<span><b>Run date:</b> {date}</span>"
        f"<span><b>Git SHA:</b> <code>{sha}</code></span>"
        f"<span><b>Runtime:</b> {runtime}</span>"
        f"<span><b>Sections:</b> {sections}</span>"
        f"<span><b>Health:</b> {health}</span>"
        f"<span><b>Total tests:</b> {total}</span>"
        f"<span><b>Dashboard updated:</b> {now}</span>"
        "</div>"
    )


def _build_section_table(rows: list[dict]) -> str:
    sections: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        sections[r["section"]][r["status"]] += 1

    present = set(sections.keys())
    legend_items = "".join(
        f'<tr><td style="font-family:monospace;font-weight:bold;color:#6b9cd4;white-space:nowrap;padding:2px 8px 2px 0">{k}</td>'
        f'<td style="color:#888;font-size:10px;padding:2px 0">{v}</td></tr>'
        for k, v in _SECTION_DESCRIPTIONS.items()
        if k in present
    )
    legend_html = (
        '<details style="margin-bottom:8px;font-size:10px">'
        '<summary style="cursor:pointer;color:#6b9cd4;padding:4px 0">▶ Section key — what each covers</summary>'
        '<div style="padding:6px 0;border-bottom:1px solid #333;margin-bottom:6px">'
        f'<table style="border-collapse:collapse;width:100%">{legend_items}</table>'
        '</div></details>'
    )

    header = (
        '<tr style="background:#1f1f1f;position:sticky;top:0">'
        '<th style="text-align:left">Section</th>'
        '<th style="text-align:left;font-size:10px;color:#888">What it covers</th>'
        '<th style="text-align:left">Pass</th>'
        '<th style="text-align:right">Warn</th>'
        '<th style="text-align:right">Fail</th>'
        '<th style="text-align:right">Blk</th>'
        '<th style="text-align:right">Total</th>'
        '<th style="text-align:left;min-width:100px">Pass%</th></tr>'
    )
    section_order = list(_SECTION_DESCRIPTIONS.keys())
    ordered = sorted(sections.keys(), key=lambda s: (section_order.index(s) if s in section_order else 999, s))

    table_rows = []
    for i, sec in enumerate(ordered):
        c = sections[sec]
        total = sum(c.values())
        pass_ct = c.get("PASS", 0)
        fail_ct = c.get("FAIL", 0) + c.get("BLOCKED", 0)
        eligible = total - c.get("INFO", 0)
        pct = round(100 * pass_ct / eligible) if eligible else 0
        warn_only = fail_ct == 0 and pass_ct == 0 and c.get("WARN", 0) > 0
        color = RED if fail_ct > 0 else (YELLOW if warn_only else GREEN)
        icon = "✗" if fail_ct > 0 else ("⚠" if warn_only else "✓")
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        desc = _SECTION_DESCRIPTIONS.get(sec, "")
        desc_cell = f'<td style="color:#555;font-size:10px;max-width:300px">{desc[:90]}{"…" if len(desc) > 90 else ""}</td>'
        table_rows.append(
            f"<tr{bg}>"
            f'<td style="font-family:monospace;color:{color};white-space:nowrap">{icon} {sec}</td>'
            f'{desc_cell}'
            f'<td style="color:{GREEN}">{pass_ct}</td>'
            f'<td style="text-align:right;color:{YELLOW}">{c.get("WARN",0)}</td>'
            f'<td style="text-align:right;color:{RED}">{c.get("FAIL",0)}</td>'
            f'<td style="text-align:right;color:{GRAY}">{c.get("BLOCKED",0)}</td>'
            f'<td style="text-align:right">{total}</td>'
            f"<td>{_bar(pass_ct, eligible, color)}</td></tr>"
        )
    return (
        f'{legend_html}'
        '<div style="overflow:auto;max-height:560px">'
        '<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(table_rows)}</table></div>"
    )


def _build_failures_panel(rows: list[dict]) -> tuple[str, int]:
    bad = [r for r in rows if r["status"] in ("FAIL", "BLOCKED", "WARN")]
    if not bad:
        return (
            f'<div style="padding:16px;text-align:center;color:{GREEN};font-size:14px">✅ No failures or warnings — clean run!</div>',
            0,
        )

    header = (
        '<tr style="background:#1f1f1f;position:sticky;top:0">'
        '<th style="text-align:left">Status</th>'
        '<th style="text-align:left">ID</th>'
        '<th style="text-align:left">Section</th>'
        '<th style="text-align:left">Name</th>'
        '<th style="text-align:left">Detail</th></tr>'
    )
    table_rows = []
    for i, r in enumerate(sorted(bad, key=lambda x: (STATUS_ORDER.index(x["status"]) if x["status"] in STATUS_ORDER else 99, x["section"]))):
        color = STATUS_COLOR.get(r["status"], GRAY)
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        detail = r["detail"][:100].replace("<", "&lt;").replace(">", "&gt;")
        table_rows.append(
            f"<tr{bg}>"
            f'<td style="color:{color};font-weight:bold;white-space:nowrap">{r["status"]}</td>'
            f'<td style="font-family:monospace;white-space:nowrap;font-size:10px">{r["tid"]}</td>'
            f'<td style="font-family:monospace;color:#aaa;white-space:nowrap">{r["section"]}</td>'
            f"<td>{r['name'][:50]}</td>"
            f'<td style="color:#888;font-size:10px">{detail}</td></tr>'
        )
    html = (
        '<div style="overflow:auto;max-height:560px">'
        '<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(table_rows)}</table></div>"
    )
    return html, len(bad)


def _build_classifier_panel(rows: list[dict]) -> str:
    bad = [r for r in rows if r["status"] in ("FAIL", "WARN")]
    if not bad:
        return f'<div style="padding:8px;color:{GREEN}">No failures or warnings to classify.</div>'

    code_defects = [r for r in bad if "CODE-DEFECT" in r["detail"]]
    env_issues = [r for r in bad if "ENV-ISSUE" in r["detail"]]
    unclassified = [r for r in bad if "CODE-DEFECT" not in r["detail"] and "ENV-ISSUE" not in r["detail"]]

    def _pill(label: str, count: int, color: str) -> str:
        return (
            f'<div style="display:inline-flex;align-items:center;gap:8px;'
            f'background:#1f1f1f;border-radius:6px;padding:8px 16px;margin:4px">'
            f'<span style="font-size:22px;font-weight:bold;color:{color}">{count}</span>'
            f'<span style="color:#aaa;font-size:12px">{label}</span></div>'
        )

    items = "".join([
        _pill("Code Defects", len(code_defects), RED),
        _pill("Env Issues", len(env_issues), YELLOW),
        _pill("Unclassified", len(unclassified), GRAY),
    ])

    rows_html = ""
    if bad:
        trs = []
        for i, r in enumerate(bad):
            classifier = "CODE-DEFECT" if "CODE-DEFECT" in r["detail"] else ("ENV-ISSUE" if "ENV-ISSUE" in r["detail"] else "unclassified")
            color = RED if classifier == "CODE-DEFECT" else (YELLOW if classifier == "ENV-ISSUE" else GRAY)
            bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
            trs.append(
                f"<tr{bg}>"
                f'<td style="font-family:monospace;white-space:nowrap;font-size:10px">{r["tid"]}</td>'
                f'<td style="color:{STATUS_COLOR.get(r["status"], GRAY)}">{r["status"]}</td>'
                f'<td style="color:{color};font-size:10px">{classifier}</td>'
                f"<td style=\"font-size:10px\">{r['name'][:60]}</td></tr>"
            )
        rows_html = (
            '<div style="overflow:auto;max-height:200px;margin-top:8px">'
            '<table style="width:100%;border-collapse:collapse;font-size:11px">'
            '<tr style="background:#1f1f1f"><th style="text-align:left">ID</th>'
            '<th style="text-align:left">Status</th><th style="text-align:left">Classifier</th>'
            '<th style="text-align:left">Name</th></tr>'
            + "".join(trs)
            + "</table></div>"
        )

    return f'<div style="display:flex;flex-wrap:wrap;gap:4px;padding:8px 0">{items}</div>{rows_html}'


def _build_trend_panel(runs: list[dict]) -> str:
    if not runs:
        return '<div style="padding:8px;color:#888">No corpus JSONL files found in tests/acceptance_corpus/. Run the update script after each acceptance run to build trend data.</div>'

    header = (
        '<tr style="background:#1f1f1f">'
        '<th style="text-align:left">Run ID</th>'
        '<th style="text-align:left">Date</th>'
        '<th style="text-align:left">Git SHA</th>'
        '<th style="text-align:right">Pass</th>'
        '<th style="text-align:right">Warn</th>'
        '<th style="text-align:right">Fail</th>'
        '<th style="text-align:right">Blk</th>'
        '<th style="text-align:right">Total</th>'
        '<th style="text-align:left;min-width:140px">Pass%</th></tr>'
    )
    table_rows = []
    for i, run in enumerate(runs):
        c = run["counts"]
        pct = run["pass_pct"]
        color = GREEN if pct >= 90 else (YELLOW if pct >= 70 else RED)
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        date = run["date"][:10] if run["date"] else run["run_id"][:10]
        sha = run["git_sha"][:7] if run["git_sha"] else ""
        total = run["total"]
        table_rows.append(
            f"<tr{bg}>"
            f'<td style="font-family:monospace;font-size:10px">{run["run_id"]}</td>'
            f"<td>{date}</td>"
            f'<td style="font-family:monospace;color:#aaa">{sha}</td>'
            f'<td style="text-align:right;color:{GREEN}">{c.get("PASS",0)}</td>'
            f'<td style="text-align:right;color:{YELLOW}">{c.get("WARN",0)}</td>'
            f'<td style="text-align:right;color:{RED}">{c.get("FAIL",0)}</td>'
            f'<td style="text-align:right;color:{GRAY}">{c.get("BLOCKED",0)}</td>'
            f"<td style=\"text-align:right\">{total}</td>"
            f"<td>{_bar(c.get('PASS', 0), total, color)}</td></tr>"
        )
    return (
        '<div style="overflow:auto;max-height:280px">'
        '<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(table_rows)}</table></div>"
    )


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update Grafana acceptance dashboard from ACCEPTANCE_RESULTS.md."
    )
    parser.add_argument("--input", default=str(RESULTS_FILE), help="Path to ACCEPTANCE_RESULTS.md")
    parser.add_argument("--dry-run", action="store_true", help="Print summary but do not write")
    parser.add_argument("--no-archive", action="store_true", help="Skip corpus archive step")
    args = parser.parse_args()

    data = _parse_results(Path(args.input))
    if "error" in data:
        print(f"Error: {data['error']}", file=sys.stderr)
        sys.exit(1)

    rows = data["rows"]
    meta = data["meta"]

    if not rows:
        print("No test rows found in results file.", file=sys.stderr)
        sys.exit(1)

    counts: Counter = Counter(r["status"] for r in rows)
    total = len(rows)
    print(
        f"Acceptance results: {total} tests — "
        f"{counts.get('PASS',0)} PASS, {counts.get('WARN',0)} WARN, "
        f"{counts.get('FAIL',0)} FAIL, {counts.get('BLOCKED',0)} BLOCKED, "
        f"{counts.get('INFO',0)} INFO"
    )
    print(f"Run date: {meta.get('Date','?')}  Git SHA: {meta.get('Git SHA','?')}")

    if args.dry_run:
        print("Dry run — dashboard not updated.")
        return

    if not args.no_archive:
        archived = _archive_corpus(rows, meta)
        if archived:
            print(f"Archived corpus snapshot: {archived.name}")

    trend_runs = _parse_corpus_runs(CORPUS_DIR, last_n=10)
    print(f"Corpus runs found: {len(trend_runs)}")

    with open(DASHBOARD_PATH) as f:
        dashboard = json.load(f)

    failures_html, bad_count = _build_failures_panel(rows)

    for panel in dashboard["panels"]:
        pid = panel.get("id")
        if pid == 1:
            panel["options"]["content"] = _build_summary_panel(rows)
        elif pid == 2:
            panel["options"]["content"] = _build_metadata_panel(meta, rows)
        elif pid == 10:
            panel["options"]["content"] = _build_section_table(rows)
        elif pid == 20:
            panel["title"] = f"Failures & Warnings ({bad_count})"
            panel["options"]["content"] = failures_html
        elif pid == 30:
            panel["options"]["content"] = _build_classifier_panel(rows)
        elif pid == 40:
            panel["title"] = f"Run Trend — last {len(trend_runs)} corpus runs"
            panel["options"]["content"] = _build_trend_panel(trend_runs)

    dashboard["version"] = dashboard.get("version", 0) + 1

    with open(DASHBOARD_PATH, "w") as f:
        json.dump(dashboard, f, indent=2)

    print(f"Dashboard updated: {DASHBOARD_PATH}  (version {dashboard['version']})")


if __name__ == "__main__":
    main()
