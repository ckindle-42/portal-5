"""Offline checks for the compliance recapture's fail-closed corpus guard."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "rebuild_compliance_projections.py"

_SPEC = importlib.util.spec_from_file_location("rebuild_compliance_projections", SCRIPT_PATH)
projections = importlib.util.module_from_spec(_SPEC)
sys.modules["rebuild_compliance_projections"] = projections
_SPEC.loader.exec_module(projections)


def _receipt(acquisition: dict | None) -> dict:
    return {"projections": {"acquisition": acquisition} if acquisition is not None else {}}


def test_a_corpus_that_ingested_files_passes_the_guard() -> None:
    assert projections._corpus_problem(_receipt({"files_ingested": 68})) is None


def test_an_empty_or_missing_corpus_is_refused() -> None:
    assert "no files" in str(projections._corpus_problem(_receipt({"files_ingested": 0})))
    assert "no files" in str(projections._corpus_problem(_receipt(None)))
    assert "no files" in str(projections._corpus_problem({"projections": {}}))


def test_an_ingest_error_is_refused_with_its_reason() -> None:
    problem = projections._corpus_problem(
        _receipt({"files_ingested": 3, "ingest_error": "embedder unreachable"})
    )
    assert "embedder unreachable" in str(problem)


def test_require_corpus_without_a_corpus_path_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        projections.main(["--require-corpus"])

    assert exc.value.code == 2
