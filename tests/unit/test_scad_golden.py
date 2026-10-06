"""Byte-identical SCAD gate: the emitter's output must not change across the
plan/backend split (TASK_CAD_ARM_REDEVELOP_V1 P3). Inputs and goldens live in
tests/data/cad_scad_golden/ (captured from the pre-refactor emitter)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portal.modules.cad.tools.scad_emitter import emit_scad

GOLDEN = Path(__file__).resolve().parents[1] / "data" / "cad_scad_golden"
CASES = sorted(p.stem for p in GOLDEN.glob("*.json"))


def test_golden_set_is_not_empty():
    assert len(CASES) >= 80


@pytest.mark.parametrize("name", CASES)
def test_emit_scad_matches_golden(name):
    geometry = json.loads((GOLDEN / f"{name}.json").read_text())
    assert emit_scad(geometry) == (GOLDEN / f"{name}.scad").read_text()
