"""`portal trace` report model — formatting and JSON shape, no I/O."""

from __future__ import annotations

import json

from portal.platform.inference.cli.trace.model import (
    Hop,
    Section,
    Status,
    TraceReport,
    format_hop,
    render_json,
    render_text,
    short,
)


def _report() -> TraceReport:
    return TraceReport(
        sections=[
            Section(
                "host",
                "HOST SERVICES",
                [
                    Hop("plist com.portal5.omlx", Status.PASS, "ProcessType=Standard", "Standard"),
                    Hop("process com.portal5.omlx", Status.FAIL, "pri=4", "pri>=20", "background"),
                ],
            ),
            Section("lab", "LAB PATHS", [Hop("splunk auth", Status.WARN, "slow")]),
        ],
        elapsed_s=1.234,
        head="abc1234",
    )


def test_format_hop_puts_observed_beside_expected() -> None:
    line = format_hop(Hop("omlx", Status.FAIL, "pri=4", "pri>=20", "background"))
    assert line == f"  FAIL {'omlx':<38} pri=4  expected pri>=20  | background"


def test_format_hop_omits_empty_parts() -> None:
    assert format_hop(Hop("splunk", Status.PASS, "ok")) == f"  PASS {'splunk':<38} ok"


def test_counts_and_ok_follow_the_worst_hop() -> None:
    report = _report()
    assert report.counts() == {"PASS": 1, "FAIL": 1, "WARN": 1}
    assert report.ok is False


def test_render_text_lists_sections_and_a_summary() -> None:
    text = render_text(_report())
    assert "head=abc1234" in text
    assert "HOST SERVICES" in text
    assert "LAB PATHS" in text
    assert text.rstrip().endswith("(1.2s)")
    assert "SUMMARY  PASS=1 FAIL=1 WARN=1" in text


def test_json_report_round_trips() -> None:
    payload = json.loads(render_json(_report()))
    assert payload["ok"] is False
    assert payload["elapsed_s"] == 1.23
    assert payload["counts"]["FAIL"] == 1
    assert [section["key"] for section in payload["sections"]] == ["host", "lab"]
    assert payload["sections"][0]["hops"][1]["detail"] == "background"


def test_short_flattens_and_bounds() -> None:
    assert short("a\n b\tc") == "a b c"
    clipped = short("x" * 200, limit=20)
    assert len(clipped) == 20 and clipped.endswith("…")
