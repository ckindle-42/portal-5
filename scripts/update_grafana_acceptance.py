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
from collections import Counter
from datetime import UTC, datetime
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
DASHBOARD_PATH = PROJECT_ROOT / "config/grafana/dashboards/portal5_acceptance.json"
RESULTS_FILE = PROJECT_ROOT / "tests/ACCEPTANCE_RESULTS.md"
CORPUS_DIR = PROJECT_ROOT / "tests/acceptance_corpus"

STATUS_ORDER = ["PASS", "WARN", "FAIL", "BLOCKED", "INFO"]
STATUS_COLOR = {
    "PASS": GREEN,
    "WARN": YELLOW,
    "FAIL": RED,
    "BLOCKED": GRAY,
    "INFO": "#6b9cd4",
}

_SECTION_DESCRIPTIONS: dict[str, str] = {
    "S0": "Prerequisites — Python version, required packages, .env file, Git repo",
    "S1": "Config consistency — backends.yaml, workspace IDs vs WORKSPACES, persona catalog, model hint reachability",
    "S2": "Service health — Docker, Ollama, Open WebUI, SearXNG, Prometheus, Grafana, all MCP + MLX services",
    "S3a": "Workspace routing (production) — 21 workspaces (20 auto-* + tools-specialist): routing, content signal, served model match",
    "S4": "Document generation MCP (:8913) — Word, Excel, PowerPoint generation end-to-end",
    "S5": "Code sandbox MCP (:8914) — Python/Bash execution, sandboxed isolation",
    "S6": "Security workspaces — auto-blueteam and auto-compliance routing + content signal",
    "S7": "Dual music generation MCPs (:8912/:8933) — MiniMax + ACE-Step end-to-end",
    "S8": "Text-to-Speech — MLX speech server Kokoro/Qwen3-TTS (:8918)",
    "S9": "Speech-to-Text — MLX transcribe Parakeet-TDT-v3 + Sortformer diarization (:8924)",
    "S10": "Personas (Ollama) — 86 non-bench personas grouped by Ollama model, behavioral signal",
    "S10c": "Compliance personas — 7 NERC/CIP compliance scenarios via fixture",
    "S12": "Web search — SearXNG integration, search result quality",
    "S13": "RAG/Embedding — MLX embedding (:8917) + Qwen3-Reranker (:8925) two-stage retrieval",
    "S15": "Shared workspace — /workspace mounts, OWUI uploads bind, AUDIO_STT_ENGINE gate",
    "S16": "Security MCP (CIRCL VLAI) — vulnerability classification end-to-end (:8919)",
    "S21": "LLM Intent Router — Llama-3.2-3B intent classifier accuracy across workspace categories",
    "S23": "Model diversity — Ollama catalog coverage, all 68+ unique models reachable",
    "S30": "Image / video generation — MLX end-to-end (:8933/:8935)",
    "S31": "Video generation — Wan2.2 end-to-end (:8911)",
    "S40": "Metrics/monitoring — Prometheus metrics, Grafana health, pipeline /metrics",
    "S41": "Production hardening — concurrency slots, request lifecycle, error surface",
    "S42": "Browser automation — Playwright MCP (:8923) navigation and extraction",
    "S50": "Negative testing — empty/oversized prompts, invalid models, malformed JSON, auth",
    "S60": "Tool-calling orchestration — MCP tool dispatch end-to-end, tool-loop correctness",
    "S70": "Information access MCPs — memory (:8920), research (:8922), browser (:8923)",
    "S3": "Workspace routing wrapper (runs S3a)",
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
        rows.append(
            {
                "section": section,
                "tid": tid,
                "name": name,
                "status": status,
                "detail": detail,
                "elapsed": elapsed,
            }
        )

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
        runs.append(
            {
                "run_id": run_id,
                "git_sha": entries[0].get("git_sha", ""),
                "date": entries[0].get("date", ""),
                "total": total,
                "counts": dict(counts),
                "pass_pct": pass_pct,
            }
        )
    return runs


def _archive_corpus(rows: list[dict], meta: dict) -> Path | None:
    """Write a JSONL snapshot to tests/acceptance_corpus/ for trend tracking."""
    if not rows:
        return None
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    git_sha = meta.get("Git SHA", "unknown")
    date = meta.get("Date", "")
    out = CORPUS_DIR / f"acceptance_{run_id}.jsonl"
    lines = [
        json.dumps(
            {
                "run_id": run_id,
                "git_sha": git_sha,
                "date": date,
                "section": r["section"],
                "tid": r["tid"],
                "name": r["name"],
                "status": r["status"],
                "detail": r["detail"][:120],
                "elapsed": r["elapsed"],
            }
        )
        for r in rows
    ]
    out.write_text("\n".join(lines) + "\n")
    return out


# ── Panel assembly ─────────────────────────────────────────────────────────────


def _build_summary_panel(rows: list[dict]) -> str:
    counts: Counter = Counter(r["status"] for r in rows)
    return summary_panel(
        dict(counts),
        len(rows),
        eligible_extra=("INFO",),
        pass_rate_note="Pass rate = PASS ÷ eligible (excludes INFO)",
    )


def _build_metadata_panel(meta: dict, rows: list[dict]) -> str:
    counts: Counter = Counter(r["status"] for r in rows)
    fields = [
        ("Run date", meta.get("Date", "unknown")),
        ("Git SHA", f"<code>{meta.get('Git SHA', 'unknown')}</code>"),
        ("Runtime", meta.get("Runtime", "unknown")),
        ("Sections", meta.get("Sections", "unknown")),
        ("Total tests", str(len(rows))),
    ]
    return metadata_panel(
        fields, fail_ct=counts.get("FAIL", 0), blocked_ct=counts.get("BLOCKED", 0)
    )


def _build_section_table(rows: list[dict]) -> str:
    return section_table(
        rows,
        _SECTION_DESCRIPTIONS,
        eligible_extra=("INFO",),
        max_height=560,
        desc_max=90,
        desc_width=300,
        summary_text="Section key — what each covers",
        section_order=list(_SECTION_DESCRIPTIONS.keys()),
    )


def _build_failures_panel(rows: list[dict]) -> tuple[str, int]:
    return failures_panel(
        rows,
        status_order=STATUS_ORDER,
        status_color=STATUS_COLOR,
        id_key="tid",
        name_key="name",
        detail_max=100,
        max_height=560,
        extra_cells=[],
    )


def _build_classifier_panel(rows: list[dict]) -> str:
    bad = [r for r in rows if r["status"] in ("FAIL", "WARN")]
    if not bad:
        return f'<div style="padding:8px;color:{GREEN}">No failures or warnings to classify.</div>'

    code_defects = [r for r in bad if "CODE-DEFECT" in r["detail"]]
    env_issues = [r for r in bad if "ENV-ISSUE" in r["detail"]]
    unclassified = [
        r for r in bad if "CODE-DEFECT" not in r["detail"] and "ENV-ISSUE" not in r["detail"]
    ]

    def _pill(label: str, count: int, color: str) -> str:
        return (
            f'<div style="display:inline-flex;align-items:center;gap:8px;'
            f'background:#1f1f1f;border-radius:6px;padding:8px 16px;margin:4px">'
            f'<span style="font-size:22px;font-weight:bold;color:{color}">{count}</span>'
            f'<span style="color:#aaa;font-size:12px">{label}</span></div>'
        )

    items = "".join(
        [
            _pill("Code Defects", len(code_defects), RED),
            _pill("Env Issues", len(env_issues), YELLOW),
            _pill("Unclassified", len(unclassified), GRAY),
        ]
    )

    rows_html = ""
    if bad:
        trs = []
        for i, r in enumerate(bad):
            classifier = (
                "CODE-DEFECT"
                if "CODE-DEFECT" in r["detail"]
                else ("ENV-ISSUE" if "ENV-ISSUE" in r["detail"] else "unclassified")
            )
            color = (
                RED
                if classifier == "CODE-DEFECT"
                else (YELLOW if classifier == "ENV-ISSUE" else GRAY)
            )
            bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
            trs.append(
                f"<tr{bg}>"
                f'<td style="font-family:monospace;white-space:nowrap;font-size:10px">{r["tid"]}</td>'
                f'<td style="color:{STATUS_COLOR.get(r["status"], GRAY)}">{r["status"]}</td>'
                f'<td style="color:{color};font-size:10px">{classifier}</td>'
                f'<td style="font-size:10px">{r["name"][:60]}</td></tr>'
            )
        rows_html = (
            '<div style="overflow:auto;max-height:200px;margin-top:8px">'
            '<table style="width:100%;border-collapse:collapse;font-size:11px">'
            '<tr style="background:#1f1f1f"><th style="text-align:left">ID</th>'
            '<th style="text-align:left">Status</th><th style="text-align:left">Classifier</th>'
            '<th style="text-align:left">Name</th></tr>' + "".join(trs) + "</table></div>"
        )

    return (
        f'<div style="display:flex;flex-wrap:wrap;gap:4px;padding:8px 0">{items}</div>{rows_html}'
    )


def _build_trend_panel(runs: list[dict]) -> str:
    return trend_table(
        runs,
        empty_note=(
            "No corpus JSONL files found in tests/acceptance_corpus/. Run the update script "
            "after each acceptance run to build trend data."
        ),
        include_sha=True,
        include_blk=True,
        max_height=280,
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
        f"{counts.get('PASS', 0)} PASS, {counts.get('WARN', 0)} WARN, "
        f"{counts.get('FAIL', 0)} FAIL, {counts.get('BLOCKED', 0)} BLOCKED, "
        f"{counts.get('INFO', 0)} INFO"
    )
    print(f"Run date: {meta.get('Date', '?')}  Git SHA: {meta.get('Git SHA', '?')}")

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
