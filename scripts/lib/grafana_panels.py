#!/usr/bin/env python3
"""Shared Grafana HTML panel builders for the three dashboard updaters.

Extracted from scripts/update_grafana_{acceptance,uat,benchmarks}.py in
TASK_PORTAL_SIMPLIFY_V1 Phase C1 Step E. The three scripts were 566+497+490
lines with `_bar` byte-identical across the first two; the builders here carry
the shared HTML so each updater is a thin driver over its own parsing.

All functions are pure HTML-string builders — they never touch the dashboard
JSON. The dashboard load/version-bump/save pattern stayed in the drivers
because each bumps the same way but reads/writes a different file.
"""

from __future__ import annotations

from collections import Counter, defaultdict

GREEN = "#73BF69"
YELLOW = "#FFD700"
RED = "#F2495C"
GRAY = "#888888"


def bar(filled: int, total: int, color: str = GREEN) -> str:
    """A compact pass-rate bar cell shared by the acceptance and UAT dashboards."""
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


def summary_panel(
    counts: dict[str, int],
    total: int,
    *,
    eligible_extra: tuple[str, ...] = (),
    legend_extra: tuple[tuple[str, str, str], ...] = (),
    pass_rate_note: str,
) -> str:
    """The four-to-seven-cell summary banner with a legend.

    acceptance passes eligible_extra=("INFO",); uat passes
    eligible_extra=("SKIP", "MANUAL") plus SKIP/MANUAL cells and a richer
    legend. The legend_extra tuples are (label, hex, description).
    """
    pass_ct = counts.get("PASS", 0)
    warn_ct = counts.get("WARN", 0)
    fail_ct = counts.get("FAIL", 0)
    blocked_ct = counts.get("BLOCKED", 0)
    eligible = total - sum(counts.get(s, 0) for s in eligible_extra)
    pct = round(100 * pass_ct / eligible) if eligible else 0
    pass_color = GREEN if fail_ct + blocked_ct == 0 else (YELLOW if fail_ct <= 3 else RED)

    legend = (
        '<div style="font-size:10px;color:#666;margin-top:10px;text-align:left;'
        'padding:6px 12px;border-top:1px solid #333;display:flex;gap:16px;flex-wrap:wrap">'
        f'<span><b style="color:{GREEN}">PASS</b> — all assertions satisfied</span>'
        f'<span><b style="color:{YELLOW}">WARN</b> — non-critical issue (critical passed)</span>'
        f'<span><b style="color:{RED}">FAIL</b> — critical assertion failed</span>'
        f'<span><b style="color:{GRAY}">BLOCKED</b> — test could not run (infra/model unavailable)</span>'
    )
    for label, color, desc in legend_extra:
        legend += f'<span><b style="color:{color}">{label}</b> — {desc}</span>'
    legend += f'<span style="color:#555">{pass_rate_note}</span>'
    legend += "</div>"

    cells = [
        (
            f'<div><div style="font-size:28px;font-weight:bold;color:{GREEN}">{pass_ct}</div>'
            '<div style="color:#aaa">PASS</div></div>'
        ),
        (
            f'<div><div style="font-size:28px;font-weight:bold;color:{YELLOW}">{warn_ct}</div>'
            '<div style="color:#aaa">WARN</div></div>'
        ),
        (
            f'<div><div style="font-size:28px;font-weight:bold;color:{RED}">{fail_ct}</div>'
            '<div style="color:#aaa">FAIL</div></div>'
        ),
        (
            f'<div><div style="font-size:28px;font-weight:bold;color:{GRAY}">{blocked_ct}</div>'
            '<div style="color:#aaa">BLOCKED</div></div>'
        ),
    ]
    # acceptance order: PASS/WARN/FAIL/BLOCKED + pass rate.
    # uat order: PASS/WARN/FAIL/BLOCKED/SKIP/MANUAL + pass rate.
    for label, color, _desc in legend_extra:
        ct = counts.get(label, 0)
        cells.append(
            f'<div><div style="font-size:28px;font-weight:bold;color:{color}">{ct}</div>'
            f'<div style="color:#aaa">{label}</div></div>'
        )
    cells.append(
        f'<div><div style="font-size:28px;font-weight:bold;color:{pass_color}">{pass_ct}/{eligible}</div>'
        f'<div style="color:#aaa">Pass Rate ({pct}%)</div></div>'
    )

    return (
        '<div style="display:flex;flex-direction:column;justify-content:center;height:100%">'
        '<div style="display:flex;justify-content:space-around;align-items:center;'
        'text-align:center;font-size:14px;padding:8px 0">'
        + "".join(cells)
        + "</div>"
        + legend
        + "</div>"
    )


def metadata_panel(
    fields: list[tuple[str, str]],
    *,
    fail_ct: int,
    blocked_ct: int,
) -> str:
    """The run-metadata strip. `fields` are (label, html) pairs rendered in order."""
    health = (
        "🟢 HEALTHY"
        if fail_ct + blocked_ct == 0
        else ("🟡 DEGRADED" if fail_ct <= 3 else "🔴 FAILING")
    )
    now = datetime_now_utc()
    spans = "".join(f"<span><b>{label}:</b> {value}</span>" for label, value in fields)
    return (
        '<div style="font-size:11px;color:#888;padding:2px 8px;display:flex;gap:16px;flex-wrap:wrap">'
        f"{spans}"
        f"<span><b>Health:</b> {health}</span>"
        f"<span><b>Dashboard updated:</b> {now}</span>"
        "</div>"
    )


def section_table(
    rows: list[dict],
    section_descriptions: dict[str, str],
    *,
    eligible_extra: tuple[str, ...],
    max_height: int,
    desc_max: int,
    desc_width: int,
    summary_text: str,
    section_order: list[str] | None = None,
) -> str:
    """Per-section pass/warn/fail table with a section-key legend.

    acceptance uses eligible_extra=("INFO",), ordered by _SECTION_DESCRIPTIONS,
    max-height 560, desc 90/300px. uat uses eligible_extra=("SKIP","MANUAL"),
    alphabetical order, max-height 480, desc 80/260px.
    """
    sections: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        sections[r["section"]][r["status"]] += 1

    present = set(sections.keys())
    legend_items = "".join(
        f'<tr><td style="font-family:monospace;font-weight:bold;color:#6b9cd4;white-space:nowrap;padding:2px 8px 2px 0">{k}</td>'
        f'<td style="color:#888;font-size:10px;padding:2px 0">{v}</td></tr>'
        for k, v in section_descriptions.items()
        if k in present
    )
    legend_html = (
        '<details style="margin-bottom:8px;font-size:10px">'
        f'<summary style="cursor:pointer;color:#6b9cd4;padding:4px 0">▶ {summary_text}</summary>'
        '<div style="padding:6px 0;border-bottom:1px solid #333;margin-bottom:6px">'
        f'<table style="border-collapse:collapse;width:100%">{legend_items}</table>'
        "</div></details>"
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
    if section_order is not None:
        ordered = sorted(
            sections.keys(),
            key=lambda s: (section_order.index(s) if s in section_order else 999, s),
        )
    else:
        ordered = sorted(sections.keys())

    table_rows = []
    for i, sec in enumerate(ordered):
        c = sections[sec]
        total = sum(c.values())
        pass_ct = c.get("PASS", 0)
        fail_ct = c.get("FAIL", 0) + c.get("BLOCKED", 0)
        eligible = total - sum(c.get(s, 0) for s in eligible_extra)
        pct = round(100 * pass_ct / eligible) if eligible else 0
        warn_only = fail_ct == 0 and pass_ct == 0 and c.get("WARN", 0) > 0
        color = RED if fail_ct > 0 else (YELLOW if warn_only else GREEN)
        icon = "✗" if fail_ct > 0 else ("⚠" if warn_only else "✓")
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        desc = section_descriptions.get(sec, "")
        desc_cell = f'<td style="color:#555;font-size:10px;max-width:{desc_width}px">{desc[:desc_max]}{"…" if len(desc) > desc_max else ""}</td>'
        table_rows.append(
            f"<tr{bg}>"
            f'<td style="font-family:monospace;color:{color};white-space:nowrap">{icon} {sec}</td>'
            f"{desc_cell}"
            f'<td style="color:{GREEN}">{pass_ct}</td>'
            f'<td style="text-align:right;color:{YELLOW}">{c.get("WARN", 0)}</td>'
            f'<td style="text-align:right;color:{RED}">{c.get("FAIL", 0)}</td>'
            f'<td style="text-align:right;color:{GRAY}">{c.get("BLOCKED", 0)}</td>'
            f'<td style="text-align:right">{total}</td>'
            f"<td>{bar(pass_ct, eligible, color)}</td></tr>"
        )
    return (
        f"{legend_html}"
        f'<div style="overflow:auto;max-height:{max_height}px">'
        '<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(table_rows)}</table></div>"
    )


def failures_panel(
    rows: list[dict],
    *,
    status_order: list[str],
    status_color: dict[str, str],
    id_key: str,
    name_key: str,
    detail_max: int,
    max_height: int,
    extra_cells: list[tuple[str, str]],
) -> tuple[str, int]:
    """Failures/warnings table. Returns (html, count).

    acceptance: no extra cells. uat: a Model column and clickable names.
    extra_cells is a list of (key, css_class) to render after the ID cell.
    """
    bad = [r for r in rows if r["status"] in ("FAIL", "BLOCKED", "WARN")]
    if not bad:
        return (
            f'<div style="padding:16px;text-align:center;color:{GREEN};font-size:14px">✅ No failures or warnings — clean run!</div>',
            0,
        )

    headers = "".join(
        f'<th style="text-align:left">{h}</th>'
        for h in ("Status", "ID") + tuple(k for k, _ in extra_cells) + ("Name", "Detail")
    )
    header = f'<tr style="background:#1f1f1f;position:sticky;top:0">{headers}</tr>'
    table_rows = []
    for i, r in enumerate(
        sorted(
            bad,
            key=lambda x: status_order.index(x["status"]) if x["status"] in status_order else 99,
        )
    ):
        color = status_color.get(r["status"], GRAY)
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        detail = r["detail"][:detail_max].replace("<", "&lt;").replace(">", "&gt;")
        extra_tds = "".join(
            f'<td style="font-family:monospace;color:#aaa">{r.get(k, "")[:28]}</td>'
            for k, _css in extra_cells
        )
        table_rows.append(
            f"<tr{bg}>"
            f'<td style="color:{color};font-weight:bold;white-space:nowrap">{r["status"]}</td>'
            f'<td style="font-family:monospace;white-space:nowrap;font-size:10px">{r[id_key]}</td>'
            f"{extra_tds}"
            f"<td>{r[name_key][:50]}</td>"
            f'<td style="color:#888;font-size:10px">{detail}</td></tr>'
        )
    html = (
        f'<div style="overflow:auto;max-height:{max_height}px">'
        '<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(table_rows)}</table></div>"
    )
    return html, len(bad)


def trend_table(
    runs: list[dict],
    *,
    empty_note: str,
    include_sha: bool,
    include_blk: bool,
    max_height: int,
) -> str:
    """Corpus run-trend table. acceptance includes Git SHA + Blk; uat does not."""
    if not runs:
        return f'<div style="padding:8px;color:#888">{empty_note}</div>'

    headers = ["Run ID", "Date"]
    if include_sha:
        headers.append("Git SHA")
    headers += ["Pass", "Warn", "Fail"]
    if include_blk:
        headers.append("Blk")
    headers.append("Total")
    headers.append("Pass%")

    header_row = "".join(
        f'<th style="text-align:{"right" if h in ("Pass", "Warn", "Fail", "Blk", "Total", "Pass%") else "left"}{"min-width:140px" if h == "Pass%" else ""}">{h}</th>'
        for h in headers
    )
    header = f'<tr style="background:#1f1f1f">{header_row}</tr>'

    table_rows = []
    for i, run in enumerate(runs):
        c = run["counts"]
        pct = run["pass_pct"]
        color = GREEN if pct >= 90 else (YELLOW if pct >= 70 else RED)
        bg = ' style="background:#1a1a2e"' if i % 2 == 1 else ""
        date = run.get("date") or run.get("timestamp") or ""
        date = date[:10] if date else run["run_id"][:10]
        sha = (run.get("git_sha", "") or "")[:7]
        total = run["total"]
        cells = [
            f'<td style="font-family:monospace;font-size:10px">{run["run_id"]}</td>',
            f"<td>{date}</td>",
        ]
        if include_sha:
            cells.append(f'<td style="font-family:monospace;color:#aaa">{sha}</td>')
        cells += [
            f'<td style="text-align:right;color:{GREEN}">{c.get("PASS", 0)}</td>',
            f'<td style="text-align:right;color:{YELLOW}">{c.get("WARN", 0)}</td>',
            f'<td style="text-align:right;color:{RED}">{c.get("FAIL", 0)}</td>',
        ]
        if include_blk:
            cells.append(f'<td style="text-align:right;color:{GRAY}">{c.get("BLOCKED", 0)}</td>')
        cells += [
            f'<td style="text-align:right">{total}</td>',
            f"<td>{bar(c.get('PASS', 0), total, color)}</td>",
        ]
        table_rows.append(f"<tr{bg}>" + "".join(cells) + "</tr>")
    return (
        f'<div style="overflow:auto;max-height:{max_height}px">'
        '<table style="width:100%;border-collapse:collapse;font-size:11px">'
        f"{header}{''.join(table_rows)}</table></div>"
    )


def datetime_now_utc() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
