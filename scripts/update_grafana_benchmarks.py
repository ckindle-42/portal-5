#!/usr/bin/env python3
"""Update portal5_benchmarks.json Grafana dashboard from bench_tps results JSON.

Usage:
    python3 scripts/update_grafana_benchmarks.py
    python3 scripts/update_grafana_benchmarks.py --input /tmp/bench_tps_results.json
    python3 scripts/update_grafana_benchmarks.py --input results.json --dry-run
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DASHBOARD_PATH = PROJECT_ROOT / "config/grafana/dashboards/portal5_benchmarks.json"
DEFAULT_INPUT = "/tmp/bench_tps_results.json"

# ── TPS colour thresholds ─────────────────────────────────────────────────────
GREEN = "#73BF69"
YELLOW = "#FFD700"
RED = "#F2495C"


def _bar_color(tps: float, peak: float) -> str:
    if peak <= 0:
        return YELLOW
    ratio = tps / peak
    if ratio >= 0.5:
        return GREEN
    return YELLOW


def _tier_badge(backend: str) -> str:
    if backend == "mlx":
        return '<span style="background:#2c5282;color:#90cdf4;padding:1px 4px;border-radius:3px;font-size:10px">T1-MLX</span>'
    if backend == "ollama":
        return '<span style="background:#2d3748;color:#68d391;padding:1px 4px;border-radius:3px;font-size:10px">T2-Ollama</span>'
    return ""


def _bar(tps: float, peak: float) -> str:
    pct = max(1, min(100, round(tps / peak * 100))) if peak > 0 else 1
    color = _bar_color(tps, peak)
    return (
        f'<div style="display:flex;align-items:center;gap:4px">'
        f'<span style="width:48px;text-align:right;font-weight:bold">{tps}</span>'
        f'<div style="background:{color};height:8px;width:{pct}%;min-width:2px;border-radius:2px"></div>'
        f"</div>"
    )


def _runs_cell(success: int, total: int) -> str:
    color = "#73BF69" if success == total else "#FFD700" if success > 0 else RED
    return f'<td style="color:{color}">{success}/{total}</td>'


# ── Panel: Model TPS table ────────────────────────────────────────────────────


def _build_model_table(direct_results: list[dict]) -> str:
    available = [r for r in direct_results if r.get("available", True) and r.get("avg_tps", 0) > 0]
    unavailable = [r for r in direct_results if not r.get("available", True)]

    all_rows = sorted(available, key=lambda r: r["avg_tps"], reverse=True) + unavailable
    peak = max((r["avg_tps"] for r in available), default=1.0)

    rows = []
    for i, r in enumerate(all_rows):
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        tier = _tier_badge(r.get("backend", ""))
        short_model = r["model"].split("/")[-1]
        mem = f"{r.get('est_memory_gb', 0):.0f}GB" if r.get("est_memory_gb") else "-"
        cat = r.get("prompt_category", "general")
        tps = r.get("avg_tps", 0)
        runs_s = r.get("runs_success", 0)
        runs_t = r.get("runs_total", 5)

        if not r.get("available", True):
            rows.append(
                f"<tr{bg}><td>{i + 1}</td><td>{tier}</td>"
                f'<td style="font-family:monospace;color:#666">{short_model}</td>'
                f'<td style="color:#666">{mem}</td><td style="color:#666">{cat}</td>'
                f'<td style="color:#666">N/A</td><td style="color:#666">0/{runs_t}</td></tr>'
            )
        else:
            rows.append(
                f"<tr{bg}><td>{i + 1}</td><td>{tier}</td>"
                f'<td style="font-family:monospace">{short_model}</td>'
                f"<td>{mem}</td><td>{cat}</td>"
                f"<td>{_bar(tps, peak)}</td>{_runs_cell(runs_s, runs_t)}</tr>"
            )

    mlx_count = sum(1 for r in available if r.get("backend") == "mlx")
    ollama_count = sum(1 for r in available if r.get("backend") == "ollama")
    header = (
        '<tr style="background:#1f1f1f;position:sticky;top:0">'
        '<th style="text-align:left">#'
        '<th style="text-align:left">Tier'
        '<th style="text-align:left">Model'
        '<th style="text-align:left">Mem'
        '<th style="text-align:left">Cat'
        '<th style="text-align:left;min-width:160px">Avg TPS'
        '<th style="text-align:left">Runs</tr>'
    )
    table_html = (
        f'<div style="overflow:auto;max-height:600px">'
        f'<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(rows)}</table></div>"
    )
    return table_html, mlx_count, ollama_count, peak


# ── Panel: Pipeline workspace TPS table ──────────────────────────────────────


def _build_workspace_table(pipeline_results: list[dict]) -> str:
    rows_data = sorted(
        [r for r in pipeline_results if r.get("avg_tps", 0) > 0],
        key=lambda r: r["avg_tps"],
        reverse=True,
    )
    peak = max((r["avg_tps"] for r in rows_data), default=1.0)
    failed = [r for r in pipeline_results if r.get("avg_tps", 0) == 0]

    all_rows = rows_data + failed
    rows = []
    for i, r in enumerate(all_rows):
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        ws = r.get("workspace", r["model"])
        cat = r.get("prompt_category", "general")
        tps = r.get("avg_tps", 0)
        runs_s = r.get("runs_success", 0)
        runs_t = r.get("runs_total", 5)
        if tps > 0:
            rows.append(
                f"<tr{bg}><td>{i + 1}</td>"
                f'<td style="font-family:monospace;font-weight:bold">{ws}</td>'
                f'<td style="color:#888">{cat}</td>'
                f"<td>{_bar(tps, peak)}</td>{_runs_cell(runs_s, runs_t)}</tr>"
            )
        else:
            errors = list({run.get("error", "?") for run in r.get("runs", []) if "error" in run})
            err_str = errors[0][:40] if errors else "fail"
            rows.append(
                f"<tr{bg}><td>{i + 1}</td>"
                f'<td style="font-family:monospace;color:#666">{ws}</td>'
                f'<td style="color:#666">{cat}</td>'
                f'<td style="color:{RED}">{err_str}</td>'
                f'<td style="color:{RED}">{runs_s}/{runs_t}</td></tr>'
            )

    header = (
        '<tr style="background:#1f1f1f;position:sticky;top:0">'
        '<th style="text-align:left">#'
        '<th style="text-align:left">Workspace'
        '<th style="text-align:left">Prompt Cat'
        '<th style="text-align:left;min-width:160px">Avg TPS'
        '<th style="text-align:left">Runs</tr>'
    )
    html = (
        f'<div style="overflow:auto;max-height:400px">'
        f'<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(rows)}</table></div>"
    )
    fastest = rows_data[0] if rows_data else None
    slowest = rows_data[-1] if rows_data else None
    return html, fastest, slowest


# ── Panel: Persona TPS table ──────────────────────────────────────────────────


def _build_persona_table(persona_results: list[dict]) -> str:
    rows_data = sorted(
        [r for r in persona_results if r.get("avg_tps", 0) > 0],
        key=lambda r: r["avg_tps"],
        reverse=True,
    )
    failed = [r for r in persona_results if r.get("avg_tps", 0) == 0]
    peak = max((r["avg_tps"] for r in rows_data), default=1.0)
    all_rows = rows_data + failed

    rows = []
    for i, r in enumerate(all_rows):
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        slug = r.get("persona_slug", r.get("model", "?"))
        cat = r.get("persona_category", "?")
        wm = r.get("workspace_model", r.get("model", "?"))
        tps = r.get("avg_tps", 0)
        runs_s = r.get("runs_success", 0)
        runs_t = r.get("runs_total", 5)
        if tps > 0:
            rows.append(
                f"<tr{bg}><td>{i + 1}</td>"
                f'<td style="font-family:monospace">{slug}</td>'
                f'<td style="color:#888">{cat}</td>'
                f'<td style="color:#6b9cd4;font-size:10px">{wm}</td>'
                f"<td>{_bar(tps, peak)}</td>{_runs_cell(runs_s, runs_t)}</tr>"
            )
        else:
            rows.append(
                f"<tr{bg}><td>{i + 1}</td>"
                f'<td style="font-family:monospace;color:#666">{slug}</td>'
                f'<td style="color:#666">{cat}</td>'
                f'<td style="color:#666">{wm}</td>'
                f'<td style="color:{RED}">FAIL</td>'
                f'<td style="color:{RED}">{runs_s}/{runs_t}</td></tr>'
            )

    header = (
        '<tr style="background:#1f1f1f;position:sticky;top:0">'
        '<th style="text-align:left">#'
        '<th style="text-align:left">Persona'
        '<th style="text-align:left">Category'
        '<th style="text-align:left">Model'
        '<th style="text-align:left;min-width:160px">Avg TPS'
        '<th style="text-align:left">Runs</tr>'
    )
    html = (
        f'<div style="overflow:auto;max-height:580px">'
        f'<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(rows)}</table></div>"
    )
    fastest = rows_data[0] if rows_data else None
    return html, fastest


# ── Panel: Summary banner ─────────────────────────────────────────────────────


def _build_summary_panel(
    mlx_count: int,
    ollama_count: int,
    ws_count: int,
    persona_count: int,
    mlx_avg: float,
    ollama_avg: float,
    peak_tps: float,
    passed: int,
    total: int,
) -> str:
    passed_color = "#73BF69" if passed == total else "#FFD700"
    return (
        '<div style="display:flex;justify-content:space-around;align-items:center;'
        'height:100%;text-align:center;font-size:14px">'
        f'<div><div style="font-size:28px;font-weight:bold;color:#73BF69">{mlx_count}</div>'
        f'<div style="color:#aaa">MLX Models</div></div>'
        f'<div><div style="font-size:28px;font-weight:bold;color:#73BF69">{ollama_count}</div>'
        f'<div style="color:#aaa">Ollama Models</div></div>'
        f'<div><div style="font-size:28px;font-weight:bold;color:#73BF69">{ws_count}</div>'
        f'<div style="color:#aaa">Workspaces</div></div>'
        f'<div><div style="font-size:28px;font-weight:bold;color:#73BF69">{persona_count}</div>'
        f'<div style="color:#aaa">Personas</div></div>'
        f'<div><div style="font-size:28px;font-weight:bold;color:#FFD700">{mlx_avg}</div>'
        f'<div style="color:#aaa">MLX avg t/s</div></div>'
        f'<div><div style="font-size:28px;font-weight:bold;color:#FFD700">{ollama_avg}</div>'
        f'<div style="color:#aaa">Ollama avg t/s</div></div>'
        f'<div><div style="font-size:28px;font-weight:bold;color:#F2CC0C">{peak_tps}</div>'
        f'<div style="color:#aaa">Peak t/s</div></div>'
        f'<div><div style="font-size:28px;font-weight:bold;color:{passed_color}">{passed}/{total}</div>'
        f'<div style="color:#aaa">Passed</div></div>'
        "</div>"
    )


# ── Panel: Run metadata ───────────────────────────────────────────────────────


def _build_metadata_panel(data: dict, runs: int, cooldown: int, wall_s: float, hw: dict) -> str:
    ts = data.get("timestamp", datetime.now(timezone.utc).isoformat())
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        ts_fmt = dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        ts_fmt = ts[:16]
    hw_str = f"{hw.get('cpu', 'Apple Silicon')} / {hw.get('unified_memory_gb', '?')}GB"
    wall_h = f"{wall_s / 3600:.1f}h" if wall_s >= 3600 else f"{wall_s / 60:.0f}m"
    return (
        '<div style="font-size:11px;color:#888;padding:2px 8px;display:flex;gap:16px;flex-wrap:wrap">'
        f"<span><b>Run:</b> {ts_fmt}</span>"
        f"<span><b>HW:</b> {hw_str}</span>"
        f"<span><b>Runs/model:</b> {runs}</span>"
        f"<span><b>Cooldown:</b> {cooldown}s</span>"
        f"<span><b>Max tokens:</b> 256</span>"
        f"<span><b>Wall time:</b> {wall_h}</span>"
        "<span><b>mlx-watchdog:</b> disabled during run</span>"
        "</div>"
    )


# ── Panel: Workspace routing notes ───────────────────────────────────────────


def _build_ws_notes(fastest, slowest, ws_count: int) -> str:
    fastest_str = f"{fastest['avg_tps']} t/s" if fastest else "N/A"
    slowest_str = f"{slowest['avg_tps']} t/s" if slowest else "N/A"
    fastest_ws = fastest.get("workspace", fastest.get("model", "?")) if fastest else "?"
    slowest_ws = slowest.get("workspace", slowest.get("model", "?")) if slowest else "?"
    return (
        f'<div style="font-size:12px;padding:8px"><p><b>All {ws_count} workspaces validated</b>'
        f" — MLX proxy + Ollama Tier 2 routing active.</p><ul>"
        f"<li><b>Fastest:</b> {fastest_ws} ({fastest_str})</li>"
        f"<li><b>Slowest:</b> {slowest_ws} ({slowest_str})</li>"
        "<li><b>Routing:</b> LLM router (Llama-3.2-3B abliterated) + keyword scoring fallback</li>"
        "</ul></div>"
    )


# ── Panel: Key findings ───────────────────────────────────────────────────────


def _build_key_findings(
    direct_results: list[dict],
    persona_results: list[dict],
    mlx_avg: float,
    ollama_avg: float,
    passed: int,
    total: int,
) -> str:
    mlx_ok = [r for r in direct_results if r.get("backend") == "mlx" and r.get("avg_tps", 0) > 0]
    ol_ok = [r for r in direct_results if r.get("backend") == "ollama" and r.get("avg_tps", 0) > 0]
    pers_ok = [r for r in persona_results if r.get("avg_tps", 0) > 0]

    best_mlx = max(mlx_ok, key=lambda r: r["avg_tps"], default=None)
    best_ol = max(ol_ok, key=lambda r: r["avg_tps"], default=None)
    best_pers = max(pers_ok, key=lambda r: r["avg_tps"], default=None)

    lines = []
    if best_mlx:
        lines.append(
            f"<li><b>Fastest MLX:</b> {best_mlx['model'].split('/')[-1]} at {best_mlx['avg_tps']} t/s"
            f" ({best_mlx.get('est_memory_gb', 0):.1f}GB)</li>"
        )
    if best_ol:
        lines.append(
            f"<li><b>Fastest Ollama:</b> {best_ol['model'].split('/')[-1]} at {best_ol['avg_tps']} t/s</li>"
        )
    if best_pers:
        lines.append(
            f"<li><b>Fastest Persona:</b> {best_pers.get('persona_slug', '?')} at {best_pers['avg_tps']} t/s</li>"
        )

    if mlx_avg > 0 and ollama_avg > 0:
        diff_pct = round(abs(ollama_avg - mlx_avg) / mlx_avg * 100)
        faster = "Ollama" if ollama_avg > mlx_avg else "MLX"
        lines.append(
            f"<li><b>MLX vs Ollama avg:</b> {faster} {diff_pct}% faster"
            f" ({ollama_avg} vs {mlx_avg} t/s) — MLX 8-bit vs Ollama Q4</li>"
        )

    failures = total - passed
    if failures == 0:
        lines.append(
            f'<li><b>Failures:</b> <span style="color:#73BF69">None — {passed}/{total} ✓</span></li>'
        )
    else:
        lines.append(
            f'<li><b>Failures:</b> <span style="color:#FFD700">{failures} failed ({passed}/{total} passed)</span></li>'
        )

    return f'<div style="font-size:12px;padding:8px"><ul>{"".join(lines)}</ul></div>'


# ── Panel: MLX vs Ollama size comparison ─────────────────────────────────────


def _build_size_comparison(direct_results: list[dict], mlx_avg: float, ollama_avg: float) -> str:
    mlx_ok = [r for r in direct_results if r.get("backend") == "mlx" and r.get("avg_tps", 0) > 0]
    ol_ok = [r for r in direct_results if r.get("backend") == "ollama" and r.get("avg_tps", 0) > 0]

    buckets = [
        ("~3-5GB", 0, 6),
        ("~7-12GB", 6, 13),
        ("~12-15GB", 13, 16),
        ("~15-22GB", 15, 23),
        ("~22-30GB", 22, 31),
        ("~34-46GB", 33, 50),
    ]

    rows = []
    for label, lo, hi in buckets:
        m_bucket = [r for r in mlx_ok if lo <= r.get("est_memory_gb", 0) < hi]
        o_bucket = [r for r in ol_ok if lo <= r.get("est_memory_gb", 0) < hi]
        if not m_bucket and not o_bucket:
            continue
        m_best = max(m_bucket, key=lambda r: r["avg_tps"], default=None)
        o_best = max(o_bucket, key=lambda r: r["avg_tps"], default=None)
        m_str = (
            f"{m_best['avg_tps']} t/s ({m_best['model'].split('/')[-1][:35]})" if m_best else "-"
        )
        o_str = (
            f"{o_best['avg_tps']} t/s ({o_best['model'].split('/')[-1][:35]})" if o_best else "-"
        )
        bg = ' style="background:#1a1a2e"' if len(rows) % 2 == 1 else ""
        rows.append(
            f"<tr{bg}><td>{label}</td>"
            f'<td style="color:#90cdf4">{m_str}</td>'
            f'<td style="color:#68d391">{o_str}</td></tr>'
        )

    mlx_n = len(mlx_ok)
    ol_n = len(ol_ok)
    rows.append(
        '<tr style="border-top:1px solid #333;font-weight:bold"><td>Overall avg</td>'
        f'<td style="color:#90cdf4">{mlx_avg} t/s ({mlx_n} models)</td>'
        f'<td style="color:#68d391">{ollama_avg} t/s ({ol_n} models)</td></tr>'
    )

    header = (
        '<tr style="background:#1f1f1f"><th style="text-align:left">Size Bucket'
        '<th style="text-align:left">MLX Best (8-bit)'
        '<th style="text-align:left">Ollama Best (Q4)</tr>'
    )
    return (
        '<div style="font-size:12px;padding:4px">'
        '<p style="color:#FFD700;font-size:10px;margin:0 0 4px">MLX runs 8-bit (higher quality), Ollama runs Q4 (lower quality).</p>'
        f'<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(rows)}</table></div>"
    )


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update Grafana benchmark dashboard from bench_tps results."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Path to bench_tps results JSON")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print summary but do not write dashboard"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Results file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path) as f:
        data = json.load(f)

    results = data.get("results", [])
    hw = data.get("hardware", {})
    wall_s = data.get("total_wall_time_s", 0)
    runs = data.get("runs_per_model", 5)
    cooldown = int(data.get("cooldown_s", 10))

    direct_results = [r for r in results if r.get("path") == "direct"]
    pipeline_results = [r for r in results if r.get("path") == "pipeline"]
    persona_results = [r for r in results if r.get("path") == "persona"]

    mlx_ok = [r for r in direct_results if r.get("backend") == "mlx" and r.get("avg_tps", 0) > 0]
    ol_ok = [r for r in direct_results if r.get("backend") == "ollama" and r.get("avg_tps", 0) > 0]
    mlx_avg = round(sum(r["avg_tps"] for r in mlx_ok) / len(mlx_ok), 1) if mlx_ok else 0.0
    ollama_avg = round(sum(r["avg_tps"] for r in ol_ok) / len(ol_ok), 1) if ol_ok else 0.0

    all_tested = [r for r in results if r.get("available", True)]
    passed = sum(1 for r in all_tested if r.get("runs_success", 0) > 0)
    total = len(all_tested)

    model_html, mlx_count, ollama_count, peak = _build_model_table(direct_results)
    ws_html, ws_fastest, ws_slowest = _build_workspace_table(pipeline_results)
    persona_html, persona_fastest = _build_persona_table(persona_results)

    ws_count = len([r for r in pipeline_results if r.get("path") == "pipeline"])
    persona_count = len(persona_results)

    summary_html = _build_summary_panel(
        mlx_count,
        ollama_count,
        ws_count,
        persona_count,
        mlx_avg,
        ollama_avg,
        round(peak, 1),
        passed,
        total,
    )
    metadata_html = _build_metadata_panel(data, runs, cooldown, wall_s, hw)
    ws_notes_html = _build_ws_notes(ws_fastest, ws_slowest, ws_count)
    findings_html = _build_key_findings(
        direct_results, persona_results, mlx_avg, ollama_avg, passed, total
    )
    size_cmp_html = _build_size_comparison(direct_results, mlx_avg, ollama_avg)

    print(
        f"Results: {len(results)} entries ({len(mlx_ok)} MLX, {len(ol_ok)} Ollama, "
        f"{ws_count} workspaces, {persona_count} personas)"
    )
    print(
        f"Passed: {passed}/{total}  MLX avg: {mlx_avg}  Ollama avg: {ollama_avg}  Peak: {round(peak, 1)}"
    )

    if args.dry_run:
        print("Dry run — dashboard not updated.")
        return

    with open(DASHBOARD_PATH) as f:
        dashboard = json.load(f)

    for panel in dashboard["panels"]:
        pid = panel.get("id")
        if pid == 1:
            panel["options"]["content"] = summary_html
        elif pid == 2:
            panel["options"]["content"] = metadata_html
        elif pid == 10:
            panel["title"] = f"Model TPS — MLX ({mlx_count}) + Ollama ({ollama_count})"
            panel["options"]["content"] = model_html
        elif pid == 20:
            panel["title"] = f"Pipeline Workspace TPS ({ws_count})"
            panel["options"]["content"] = ws_html
        elif pid == 21:
            panel["options"]["content"] = ws_notes_html
        elif pid == 40:
            panel["title"] = f"Persona Routing TPS ({persona_count})"
            panel["options"]["content"] = persona_html
        elif pid == 50:
            panel["options"]["content"] = findings_html
        elif pid == 51:
            panel["options"]["content"] = size_cmp_html

    dashboard["version"] = dashboard.get("version", 0) + 1

    with open(DASHBOARD_PATH, "w") as f:
        json.dump(dashboard, f, indent=2)

    print(f"Dashboard updated: {DASHBOARD_PATH}  (version {dashboard['version']})")


if __name__ == "__main__":
    main()
