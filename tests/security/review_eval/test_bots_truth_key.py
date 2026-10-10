"""The rebuilt BOTS key loads only cited entries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portal.modules.security.core.review_eval import bots_truth_key


def _write(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def test_load_returns_answer_key_entries(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "key.json",
        [
            {
                "dataset": "botsv1",
                "technique": "T1595.002",
                "entities": ["40.80.148.42", "imreallynotbatman.com"],
                "sourcetypes": ["stream:http"],
                "citations": ["https://example.org/botsv1 — question 101"],
            }
        ],
    )
    (entry,) = bots_truth_key.load(path)
    assert entry.citations == ("https://example.org/botsv1 — question 101",)
    converted = entry.answer_key_entry()
    assert converted.entities == ("40.80.148.42", "imreallynotbatman.com")
    assert converted.sourcetypes == ("stream:http",)


def test_load_refuses_an_uncited_entry(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "key.json",
        [
            {
                "dataset": "botsv1",
                "technique": "T1",
                "entities": ["a"],
                "sourcetypes": ["s"],
                "citations": [],
            }
        ],
    )
    with pytest.raises(ValueError, match="citations"):
        bots_truth_key.load(path)
