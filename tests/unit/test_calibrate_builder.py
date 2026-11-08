from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def _row(serial: int, event_time: float) -> dict[str, Any]:
    return {
        "_bkt": "portal5_lab~13~bucket",
        "_cd": f"13:{serial}",
        "_indextime": "1794061765",
        "_raw": "EventCode=4769 TimeCreated=2026-11-07 20:12:12 UTC ServiceName=svc_backup",
        "_serial": str(serial),
        "_sourcetype": "windows:security",
        "_time": event_time,
        "host": "10.10.11.21",
        "index": "portal5_lab",
        "source": "portal5:live:boot:proxmox",
        "sourcetype": "windows:security",
    }


def _window_with_levels(levels: list[str]) -> SimpleNamespace:
    units = [
        SimpleNamespace(unit=SimpleNamespace(unit_id=f"u{i}", level=level))
        for i, level in enumerate(levels)
    ]
    return SimpleNamespace(units=units, events={}, receipts=[], blind_sources=[])


def _window(unit_count: int) -> SimpleNamespace:
    return _window_with_levels([("L2_ENTITY", "L3_CHAIN")[i % 2] for i in range(unit_count)])


def _patch_unit_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    from portal.modules.security.core.review import build_calibration_slice as builder
    from portal.modules.security.core.review import funnel

    monkeypatch.setattr(
        builder,
        "build_window_units",
        lambda records: _window(sum(len(rows) for rows in records.values())),
    )
    monkeypatch.setattr(
        funnel,
        "split_units",
        lambda units, salt: (units[: len(units) // 2], units[len(units) // 2 :]),
    )
    monkeypatch.setattr(builder, "build_reference", lambda *args, **kwargs: None)


def _patch_levels(monkeypatch: pytest.MonkeyPatch, levels: list[str]) -> None:
    from portal.modules.security.core.review import build_calibration_slice as builder
    from portal.modules.security.core.review import funnel

    monkeypatch.setattr(builder, "build_window_units", lambda records: _window_with_levels(levels))
    monkeypatch.setattr(
        funnel,
        "split_units",
        lambda units, salt: (units[: len(units) // 2], units[len(units) // 2 :]),
    )
    monkeypatch.setattr(builder, "build_reference", lambda *args, **kwargs: None)


class _Source:
    def __init__(self, records: dict[str, list[dict[str, Any]]]) -> None:
        self.records = records
        self.calls: list[tuple[float, float]] = []

    def fetch(self, sources: Any, start: float, end: float) -> SimpleNamespace:
        self.calls.append((start, end))
        selected = [row for row in self.records.get("all", []) if start <= row["_time"] < end]
        return SimpleNamespace(
            records_by_source={sources[0].source_id: selected}, receipts=[], degraded=[]
        )


def test_target_units_expands_fetch_and_records_half_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.security.core.review.build_calibration_slice import build

    _patch_unit_builder(monkeypatch)
    rows = [_row(i, 100 + i % 100) for i in range(998)]
    rows.extend(_row(1000 + i, 10 + i % 80) for i in range(101))
    rows.extend(_row(2000 + i, 200 + i % 100) for i in range(101))
    source = _Source({"all": rows})
    old_slice = tmp_path / "calibration_slice.json"
    old_slice.write_text('{"old":true}', encoding="utf-8")

    summary = build(
        start=100,
        end=200,
        target_units=600,
        output_dir=tmp_path,
        splunk_source=source,
        rule="stated benign window rule",
    )

    assert len(source.calls) > 1
    assert min(start for start, _ in source.calls) < 100
    assert max(end for _, end in source.calls) > 200
    assert summary["calibration_half_units"] == 600
    assert summary["p_step"] == pytest.approx(1 / 601)
    assert summary["target_reached"] is True
    assert summary["backup_slice"]
    assert Path(summary["backup_slice"]).read_text(encoding="utf-8") == '{"old":true}'
    provenance = json.loads(Path(summary["written_provenance"]).read_text(encoding="utf-8"))
    assert provenance["rule"] == "stated benign window rule"
    assert provenance["calibration_half_units"] == 600
    assert provenance["p_step"] == pytest.approx(1 / 601)


def test_insufficient_window_reports_shortfall_and_p_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.security.core.review import build_calibration_slice as builder

    _patch_unit_builder(monkeypatch)
    source = _Source({"all": [_row(i, 100 + i) for i in range(10)]})

    with pytest.raises(RuntimeError, match=r"target 600.*short by 595.*p_step=0\.166667"):
        builder.build(
            start=100,
            end=200,
            target_units=600,
            output_dir=tmp_path,
            splunk_source=source,
            rule="stated benign window rule",
        )

    assert not (tmp_path / "calibration_slice.json").exists()


def test_slice_with_no_units_at_a_required_level_fails_instead_of_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.security.core.review import build_calibration_slice as builder

    _patch_levels(monkeypatch, ["L2_ENTITY"] * 40)
    source = _Source({"all": [_row(i, 100) for i in range(40)]})

    with pytest.raises(builder.LevelUnavailableError, match="L3_CHAIN"):
        builder.build(
            start=100,
            end=200,
            target_units=10,
            output_dir=tmp_path,
            splunk_source=source,
            rule="stated benign window rule",
        )

    assert not (tmp_path / "calibration_slice.json").exists()


def test_slice_reports_an_uncertified_level_instead_of_claiming_it_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.security.core.review.build_calibration_slice import build

    _patch_levels(monkeypatch, ["L3_CHAIN", *["L2_ENTITY"] * 39])
    source = _Source({"all": [_row(i, 100) for i in range(40)]})

    summary = build(
        start=100,
        end=200,
        target_units=10,
        output_dir=tmp_path,
        splunk_source=source,
        rule="stated benign window rule",
    )

    chain = summary["levels"]["L3_CHAIN"]
    assert chain["constructed"] == 1
    assert chain["not_in_calibration_half"] == 1
    assert chain["benign_scores_recorded"] == 0
    assert chain["required_benign_scores"] == 4
    assert chain["certified"] is False
    assert "calibration half" in chain["reason"]
    assert summary["uncertified_levels"] == ["L3_CHAIN"]
    assert summary["levels"]["L2_ENTITY"]["certified"] is True
    provenance = json.loads(Path(summary["written_provenance"]).read_text(encoding="utf-8"))
    assert provenance["uncertified_levels"] == ["L3_CHAIN"]
    assert provenance["levels"]["L3_CHAIN"]["certified"] is False


def test_cli_requires_rule_and_passes_selected_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    from portal.modules.security.core import review_cli
    from portal.modules.security.core.review import build_calibration_slice as builder

    parser = review_cli._parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["build-calibration-slice", "--start", "1", "--end", "2"])

    args = parser.parse_args(
        [
            "build-calibration-slice",
            "--start",
            "1",
            "--end",
            "2",
            "--rule",
            "stated benign window rule",
            "--sources",
            "portal5_lab:windows:security",
            "portal5_lab:web:access",
        ]
    )
    captured: dict[str, Any] = {}
    monkeypatch.setattr(builder, "build", lambda **kwargs: captured.update(kwargs) or {})
    review_cli._run(None, args)

    assert [source.source_id for source in captured["sources"]] == [
        "portal5_lab:windows:security",
        "portal5_lab:web:access",
    ]
    assert captured["rule"] == "stated benign window rule"


def test_module_main_surfaces_exception_type_and_redacts_password(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from portal.modules.security.core.review import build_calibration_slice as builder

    monkeypatch.setenv("LAB_SPLUNK_PASSWORD", "secret-value")

    def fail(**kwargs: Any) -> None:
        raise RuntimeError("Splunk denied secret-value")

    monkeypatch.setattr(builder, "build", fail)
    status = builder.main(["--start", "1", "--end", "2", "--rule", "stated benign window rule"])
    captured = capsys.readouterr()

    assert status != 0
    assert "RuntimeError" in captured.err
    assert "Splunk denied" in captured.err
    assert "secret-value" not in captured.err


def test_review_cli_surfaces_builder_failure_without_runtime(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from portal.modules.security.core import review_cli
    from portal.modules.security.core.review import build_calibration_slice as builder

    monkeypatch.setenv("LAB_SPLUNK_PASSWORD", "secret-value")

    def fail(**kwargs: Any) -> None:
        raise RuntimeError("denied secret-value")

    monkeypatch.setattr(builder, "build", fail)
    status = review_cli.main(
        [
            "build-calibration-slice",
            "--start",
            "1",
            "--end",
            "2",
            "--rule",
            "stated benign window rule",
        ]
    )
    captured = capsys.readouterr()

    assert status == 1
    assert "RuntimeError" in captured.err
    assert "denied" in captured.err
    assert "secret-value" not in captured.err
