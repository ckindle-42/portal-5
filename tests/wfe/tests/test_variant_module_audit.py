"""A disabled variant is skipped by the settings audit, not failed."""

from __future__ import annotations

from pathlib import Path

import yaml

from tests.wfe.settings_audit import classify_seats

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "variant_module_gate.yaml"
DISABLED = "disabled, not tested"


def _portal() -> dict:
    return yaml.safe_load(FIXTURE.read_text())


def _ids(seats: list[tuple[str, dict]]) -> set[str]:
    return {seat_id for seat_id, _ws in seats}


def test_disabled_variants_are_not_tested() -> None:
    seats, skipped = classify_seats(_portal(), {"media"})
    ids = _ids(seats)
    assert "auto-media" in ids
    assert "auto-media::speech" in ids
    assert {"auto-media::image", "auto-media::video", "auto-media::music"}.isdisjoint(ids)
    assert {row["id"]: row["status"] for row in skipped} == {
        "auto-media::image": DISABLED,
        "auto-media::video": DISABLED,
        "auto-media::music": DISABLED,
    }
    assert all(row["status"] != "FAIL" for row in skipped)


def test_enabling_image_tests_only_that_variant() -> None:
    seats, skipped = classify_seats(_portal(), {"media", "image"})
    ids = _ids(seats)
    assert "auto-media::image" in ids
    assert "auto-media::video" not in ids
    assert "auto-media::music" not in ids
    assert {row["id"] for row in skipped} == {"auto-media::video", "auto-media::music"}


def test_unfiltered_audit_still_seats_every_variant() -> None:
    seats, skipped = classify_seats(_portal(), None)
    assert skipped == []
    assert "auto-media::image" in _ids(seats)
    assert "auto-media::speech" in _ids(seats)
