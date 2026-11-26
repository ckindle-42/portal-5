"""The compliance triage's public row must read the raw trace record's keys.

`_public_row` reads `served_model` from the raw `/v1/trace` record — a key only
`transport_dialects.PipelineCompat._trace` invents on its own renamed receipt.
The record's served model is `model`; the old lookup left the column permanently
empty, so served-model drift across sampling arms was invisible.
"""

from __future__ import annotations

import importlib
from pathlib import Path


def test_public_row_reads_the_raw_record_model_key() -> None:
    triage = importlib.import_module("scripts.compliance.reading_loop_triage")
    row = {
        "arm": "a",
        "key": "k",
        "repeat": 1,
        "verdict": "answered",
        "result": {
            "trace": {"backend": "b", "model": "served-tag"},
            "correlation_id": "p5-1",
        },
    }

    public = triage._public_row(row, Path("private.jsonl"))

    assert public["served_model"] == "served-tag"
    assert public["route_backend"] == "b"
    assert public["options_applied"] is None
