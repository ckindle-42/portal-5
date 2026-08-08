"""UAT catalog group: auto-documents (Transcript Analyst golden-path chain)."""

from __future__ import annotations

from portal.platform.data_loader import load_data
from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

# (transcribe_with_speakers → create_word_document)


TESTS: list[dict] = load_data("tests/data", "uat_catalog_g_auto_documents")
