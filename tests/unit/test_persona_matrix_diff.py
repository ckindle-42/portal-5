"""Unit tests for tests/persona_matrix_diff.py."""

from __future__ import annotations

import json

import pytest

from tests import persona_matrix_diff as pmd


def _make_report(cells, schema="portal5.persona_matrix.v1") -> dict:
    return {
        "schema": schema,
        "timestamp_utc": "2026-04-30T00:00:00+00:00",
        "elapsed_s": 0.0,
        "plan": {},
        "cells": cells,
    }


def _cell(persona, backend, model, P, W, F, E=0):
    return {
        "persona": persona,
        "backend": backend,
        "model": model,
        "group": "general",
        "scenarios": [],
        "summary": {"PASS": P, "WARN": W, "FAIL": F, "ERROR": E},
    }


def test_no_regression_below_threshold(tmp_path):
    base = _make_report([_cell("p1", "ollama", "m1", 9, 0, 1)])
    new = _make_report([_cell("p1", "ollama", "m1", 8, 1, 1)])
    base_path = tmp_path / "base.json"
    base_path.write_text(json.dumps(base))
    regressions = pmd.compute_regressions(base_path, new, threshold_pp=10.0)
    assert regressions == []


def test_regression_over_threshold(tmp_path):
    base = _make_report([_cell("p1", "ollama", "m1", 9, 0, 1)])
    new = _make_report([_cell("p1", "ollama", "m1", 7, 0, 3)])
    base_path = tmp_path / "base.json"
    base_path.write_text(json.dumps(base))
    regressions = pmd.compute_regressions(base_path, new, threshold_pp=10.0)
    assert len(regressions) == 1
    assert "p1" in regressions[0]
    assert "m1" in regressions[0]


def test_improvement_surfaced(tmp_path):
    base = _make_report([_cell("p1", "ollama", "m1", 5, 0, 5)])
    new = _make_report([_cell("p1", "ollama", "m1", 9, 0, 1)])
    base_path = tmp_path / "base.json"
    base_path.write_text(json.dumps(base))
    improvements = pmd.compute_improvements(base_path, new, threshold_pp=10.0)
    assert len(improvements) == 1
    assert "+IMPROVED" in improvements[0]


def test_added_and_removed_cells(tmp_path):
    base = _make_report([_cell("p1", "ollama", "m1", 9, 0, 1)])
    new = _make_report(
        [
            _cell("p1", "ollama", "m1", 9, 0, 1),
            _cell("p1", "ollama", "m2-NEW", 8, 0, 2),
        ]
    )
    base_path = tmp_path / "base.json"
    base_path.write_text(json.dumps(base))
    added, removed = pmd.added_removed_cells(base_path, new)
    assert any("m2-NEW" in a for a in added)
    assert removed == []


def test_invalid_schema_raises(tmp_path):
    bad = _make_report([], schema="not.a.real.schema")
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        pmd.compute_regressions(bad_path, _make_report([]), threshold_pp=10.0)


def test_cell_with_only_errors_is_skipped(tmp_path):
    base = _make_report([_cell("p1", "ollama", "m1", 9, 0, 1)])
    new = _make_report([_cell("p1", "ollama", "m1", 0, 0, 0, E=10)])
    base_path = tmp_path / "base.json"
    base_path.write_text(json.dumps(base))
    regressions = pmd.compute_regressions(base_path, new, threshold_pp=10.0)
    assert regressions == []
