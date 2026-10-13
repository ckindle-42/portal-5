"""bench_judgment_probe_v6 instrument fixes (2026-10-13 selection-bias audit)."""

from __future__ import annotations

import bench_judgment_probe_v6 as probe


def _perfect_rows(cases):
    return [
        probe.score_case(
            c, {"determination": c["gold_label"], "cited_refs": c["gold_citation"]}, set()
        )
        for c in cases
    ]


def test_transport_errors_are_excluded_not_scored_as_misses():
    cases = probe.load_cases()
    rows = _perfect_rows(cases)
    rows[0] = {**probe.score_case(cases[0], None, set()), "instrument_error": True}
    agg = probe.aggregate(rows, cases)
    assert agg["instrument_errors"] == 1 and agg["n"] == len(cases) - 1
    assert agg["violation_class_accuracy"] == 1.0


def test_default_transport_is_the_council_seat_path(monkeypatch):
    seen = {}

    def fake_chat(model, system, user, **kw):
        seen.update(kw, system=system)
        from portal.modules.compliance.core.reading_transport import ChatResult

        return ChatResult(content='{"determination": "SUPPORTED", "cited_refs": []}')

    monkeypatch.setattr("portal.modules.compliance.core.reading_transport.chat", fake_chat)
    monkeypatch.setattr(probe, "_PIPELINE_MODE", False)
    monkeypatch.setattr(probe, "_LEGACY_NATIVE", False)
    run = probe.run_case("some-model", probe.load_cases()[0], system="VARIANT")
    assert seen["system"] == "VARIANT"
    assert run["request"]["transport"] == "council"
    assert (
        seen["budget"] == 8192 and "think" not in seen
    )  # reasoning allowed, as the council runs it
    assert run["parsed"]["determination"] == "SUPPORTED"
