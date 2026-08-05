"""UAT catalog group: auto-video (video generation workspace)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)


def _load_catalog(name: str) -> list[dict]:
    path = Path(__file__).resolve().parents[2] / "tests" / "data" / f"uat_catalog_{name}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


TESTS: list[dict] = _load_catalog("g_auto_video")
