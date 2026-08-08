"""UAT catalog group: auto-phi4 (STEM reasoning specialist).

phi4-reasoning:plus / plus-ctx32k are NOT used here — confirmed to crash
Ollama's llama-server on load (signal: abort trap, llama.cpp
common_fit_params device-memory-fit crash) on this host, reproduced even
after a full ollama rm + re-pull + rebuild of the ctx-tagged variants (so
NOT a corrupted-download issue, contra the earlier theory in
KNOWN_LIMITATIONS.md). Tests target auto-reasoning's actual pool default
(DeepSeek-R1-0528-Qwen3-8B) instead — matches phi4stemanalyst's
re-identified (Phi-4-lineage-dropped) persona.
"""

from __future__ import annotations

from portal.platform.data_loader import load_data
from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = load_data("tests/data", "uat_catalog_g_auto_phi4")
