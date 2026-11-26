"""Layout integrity for the orchestrated-usage Grafana dashboard."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

DASHBOARD = (
    Path(__file__).resolve().parents[2] / "config/grafana/dashboards/portal5_orchestrate_usage.json"
)
# Frozen from the pre-redesign dashboard. Titles and gridPos may change; nothing else may.
# 2026-11-25: re-frozen after pace and deficit cells became words and the exporter sha panel was added.
CONTENT_SHA256 = "d5d5064816ff14335912571c7b938fb1aff1c589fa557834dae1347549e83449"
EXPECTED_EXPRS = 103
# fmt: off
EXPECTED_DATA_IDS = frozenset({
    2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 15, 16, 17,
    103, 104, 105, 106, 107, 109, 110, 111, 113, 115, 116, 117,
    119, 120, 121, 122, 123, 124, 125, 127, 128, 129, 130, 131, 133, 134, 136, 137,
    201, 202, 203, 204,  # drilldown tables (orchestrate da11fc6)
})
# fmt: on
EXEC_TITLES = (
    "Cash Spent (7d)",
    "Prepaid Value Saved (7d)",
    "Dispatches (7d)",
    "Accept Rate (7d)",
    "Pools Resetting to Waste",
    "Rate-Limited Pools Now",
    "Plan Headroom & Burn Pace",
    "Quota Burn-Down & Resets",
    "Metered Cash & Live Balances",
)
BURN_TITLES = (
    "Projected Unused at Reset",
    "Burn Deficit (Behind Even Burn)",
    "Hours to Reset by Pool",
    "Work Backlog Supply",
    "Windows Actively Biting",
    "Argon Shared Gemini Fence (Used / Left)",
)
SEAT_TITLES = (
    "Current Routable Seats",
    "Routing Evidence: Family × Task Kind",
    "Provider Reliability & Failures",
    "P40 dispatches (7d)",
    "P40 accept rate, current seats (7d)",
    "P40 tokens (7d)",
    "Value of free P40 work (7d)",
    "P40 Dispatches by Model",
)
COST_TITLES = (
    "Lifetime Paid & Vendor Usage",
    "Booked Spend by Plan (Ledger)",
    "Per-Tier Routing Ledger",
    "New Tokens by Tier",
    "OrcaRouter Wallet History",
    "OrcaRouter Free Buckets & Rung",
    "OrcaRouter Wallet Now",
    "Metered Balances",
    "Extra Usage Past Plan",
)
RATE_TITLES = (
    "Quota Reading Freshness",
    "Quota Staleness vs 3h Gate",
    "Daily Requests vs Published Cap",
    "RPM High-Water vs Per-Minute Cap",
    "Rate-Limit Events (24h)",
    "Last Rate-Limit Retry Time",
    "Last Rate-Limit Event per Pool",
    "Exporter running sha",
)
ARCHIVE_TITLES = (
    "Retired Seats (History Only)",
    "Dashboard Scope & Data Notes",
)
DRILL_TITLES = ("Lanes running", "Lanes stalled", "Lanes in timeout", "Lanes failed")
SECTION_TITLES = {
    "Executive Summary": EXEC_TITLES,
    "Burn Pacing & Capacity Waste": BURN_TITLES,
    "Seats, Routing & Local P40 Capacity": SEAT_TITLES,
    "Cost, Spend & Token Ledger": COST_TITLES,
    "Rate Limits & Exporter Health": RATE_TITLES,
    "Lane Drilldown": DRILL_TITLES,
    "Archive & Data Notes": ARCHIVE_TITLES,
}
EXPECTED_BANDS = {
    "Executive Summary": (((4, 4, 4, 4, 4, 4), 4), ((24,), 11), ((14, 10), 7)),
    "Burn Pacing & Capacity Waste": (((12, 12), 7), ((8, 8, 8), 7), ((24,), 5)),
    "Seats, Routing & Local P40 Capacity": (
        ((24,), 10),
        ((12, 12), 8),
        ((6, 6, 6, 6), 4),
        ((24,), 6),
    ),
    "Cost, Spend & Token Ledger": (
        ((12, 12), 8),
        ((24,), 9),
        ((24,), 7),
        ((12, 12), 7),
        ((6, 9, 9), 5),
    ),
    "Rate Limits & Exporter Health": (
        ((12, 12), 7),
        ((12, 12), 8),
        ((16, 8), 7),
        ((24,), 7),
        ((24,), 4),
    ),
    "Lane Drilldown": (((6, 6, 6, 6), 4),),
    "Archive & Data Notes": (((24,), 7), ((24,), 6)),
}

Panel = dict[str, Any]


def _load() -> dict[str, Any]:
    return json.loads(DASHBOARD.read_text(encoding="utf-8"))


def _walk(panels: list[Panel]) -> list[Panel]:
    found: list[Panel] = []
    for panel in panels:
        found.append(panel)
        if panel.get("type") == "row":
            found.extend(_walk(panel.get("panels") or []))
    return found


def _rows(dash: dict[str, Any]) -> list[Panel]:
    return [panel for panel in dash["panels"] if panel.get("type") == "row"]


def _data_panels(dash: dict[str, Any]) -> list[Panel]:
    return [panel for panel in _walk(dash["panels"]) if panel.get("type") != "row"]


def _section_panels(dash: dict[str, Any]) -> list[tuple[str, list[Panel]]]:
    top = dash["panels"]
    rows = _rows(dash)
    cut = top.index(rows[1])
    sections = [(rows[0]["title"], top[1:cut])]
    sections.extend((row["title"], list(row.get("panels") or [])) for row in rows[1:])
    return sections


def _reading_order(panels: list[Panel]) -> list[Panel]:
    data = [panel for panel in panels if panel.get("type") != "row"]
    return sorted(data, key=lambda panel: (panel["gridPos"]["y"], panel["gridPos"]["x"]))


def _band_shapes(panels: list[Panel]) -> tuple[tuple[tuple[int, ...], int], ...]:
    grouped: dict[int, list[Panel]] = {}
    for panel in panels:
        if panel.get("type") == "row":
            continue
        grouped.setdefault(panel["gridPos"]["y"], []).append(panel)
    shapes: list[tuple[tuple[int, ...], int]] = []
    prev_end: int | None = None
    for y in sorted(grouped):
        group = sorted(grouped[y], key=lambda panel: panel["gridPos"]["x"])
        height = group[0]["gridPos"]["h"]
        assert all(panel["gridPos"]["h"] == height for panel in group), (y, height)
        if prev_end is not None:
            assert y == prev_end, (y, prev_end)
        prev_end = y + height
        cursor = 0
        widths: list[int] = []
        for panel in group:
            assert panel["gridPos"]["x"] == cursor, (panel["id"], panel["gridPos"]["x"], cursor)
            cursor += panel["gridPos"]["w"]
            widths.append(panel["gridPos"]["w"])
        assert cursor == 24, (y, cursor)
        shapes.append((tuple(widths), height))
    return tuple(shapes)


def _separated(left: Panel, right: Panel) -> bool:
    ax, ay, aw, ah = (left["gridPos"][key] for key in ("x", "y", "w", "h"))
    bx, by, bw, bh = (right["gridPos"][key] for key in ("x", "y", "w", "h"))
    return ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay


def _content_sha(panels: list[Panel]) -> str:
    chunks = []
    for panel in panels:
        body = {key: value for key, value in panel.items() if key not in {"gridPos", "title"}}
        chunks.append(json.dumps(body, sort_keys=True, separators=(",", ":")))
    chunks.sort()
    return hashlib.sha256("\n".join(chunks).encode()).hexdigest()


def test_ids_unique_and_queries_preserved() -> None:
    dash = _load()
    ids = [panel["id"] for panel in _walk(dash["panels"])]
    assert len(ids) == len(set(ids))
    data = _data_panels(dash)
    assert {panel["id"] for panel in data} == EXPECTED_DATA_IDS
    exprs = [
        target.get("expr")
        for panel in data
        for target in panel.get("targets") or []
        if str(target.get("expr") or "").strip()
    ]
    assert len(exprs) == EXPECTED_EXPRS
    assert _content_sha(data) == CONTENT_SHA256


def test_sections_tile_without_holes_or_overlap() -> None:
    dash = _load()
    sections = _section_panels(dash)
    assert [name for name, _panels in sections] == list(SECTION_TITLES)
    for name, panels in sections:
        ordered = _reading_order(panels)
        assert [panel["title"] for panel in ordered] == list(SECTION_TITLES[name])
        assert _band_shapes(panels) == EXPECTED_BANDS[name]
        for index, panel in enumerate(ordered):
            for other in ordered[index + 1 :]:
                assert _separated(panel, other), (name, panel["id"], other["id"])


def test_executive_kpis_sit_above_the_fold() -> None:
    _name, panels = _section_panels(_load())[0]
    kpis = [panel for panel in _reading_order(panels) if panel["title"] in EXEC_TITLES[:6]]
    assert [panel["title"] for panel in kpis] == list(EXEC_TITLES[:6])
    assert all(panel["type"] == "stat" for panel in kpis)
    assert all(panel["gridPos"]["y"] <= 5 for panel in kpis)


def test_row_headers_stack_under_the_cockpit() -> None:
    dash = _load()
    rows = _rows(dash)
    cockpit = _section_panels(dash)[0][1]
    bottom = max(panel["gridPos"]["y"] + panel["gridPos"]["h"] for panel in cockpit)
    assert rows[0]["gridPos"] == {"x": 0, "y": 0, "w": 24, "h": 1}
    assert rows[0]["collapsed"] is False
    assert min(panel["gridPos"]["y"] for panel in cockpit) == 1
    assert [row["gridPos"]["y"] for row in rows[1:]] == list(range(bottom, bottom + len(rows) - 1))
    assert all(row["collapsed"] is True for row in rows[1:])
    for row in rows:
        assert row["gridPos"]["x"] == 0
        assert row["gridPos"]["w"] == 24
        assert row["gridPos"]["h"] == 1


def test_collapsed_rows_hold_their_children() -> None:
    top = _load()["panels"]
    second = next(
        index for index, panel in enumerate(top) if panel.get("type") == "row" and index > 0
    )
    assert all(panel.get("type") == "row" for panel in top[second:])
    for row in top[second:]:
        assert row["panels"]
        assert all(panel.get("type") != "row" for panel in row["panels"])


def test_archive_is_last_and_argon_is_in_burn_pacing() -> None:
    dash = _load()
    rows = _rows(dash)
    assert rows[-1]["title"] == "Archive & Data Notes"
    assert dash["panels"][-1] is rows[-1]
    burn = next(row for row in rows if row["title"] == "Burn Pacing & Capacity Waste")
    argon = [panel for panel in burn.get("panels") or [] if "Argon" in panel["title"]]
    assert [panel["id"] for panel in argon] == [136]
    archive_ids = [panel["id"] for panel in rows[-1]["panels"]]
    assert 12 in archive_ids
    assert 136 not in archive_ids
    assert rows.index(burn) < rows.index(rows[-1])
