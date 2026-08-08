"""UAT catalog group: vision personas (M6-T08)."""

from __future__ import annotations

from portal.platform.data_loader import load_data
from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = load_data("tests/data", "uat_catalog_g_vision_personas")
