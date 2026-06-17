"""Assembled UAT test catalog.

Each ``g_<group>.py`` module exports a ``TESTS: list[dict]`` for one
``# GROUP`` from the original inline TEST_CATALOG. This package concatenates
them in the original catalog order and exposes the combined ``TEST_CATALOG``.

To add a workspace's tests: create ``g_<group>.py`` with a ``TESTS`` list and
append its import to ``_GROUPS`` below — no edits to the 11k-line driver.

Catalog order is significant: it is the stable pre-sort order consumed by
``tests.uat.runner.sort_tests_cascade`` before cascade reordering.
"""

from __future__ import annotations

# Import order == catalog order. Append new groups at the correct position.
from tests.uat_catalog import (
    g_advanced,
    g_auto,
    g_auto_agentic,
    g_auto_audio,
    g_auto_blueteam,
    g_auto_cad,
    g_auto_coding,
    g_auto_compliance,
    g_auto_creative,
    g_auto_daily,
    g_auto_data,
    g_auto_docs,
    g_auto_documents,
    g_auto_mistral,
    g_auto_music,
    g_auto_pentest,
    g_auto_purpleteam,
    g_auto_reasoning,
    g_auto_redteam,
    g_auto_research,
    g_auto_security,
    g_auto_spl,
    g_auto_video,
    g_auto_vision,
    g_auto_voice,
    g_benchmark,
    g_browser_automation,
    g_tools_specialist,
    g_vision_personas,
)

_GROUPS = [
    g_auto,
    g_auto_daily,
    g_auto_coding,
    g_auto_spl,
    g_auto_mistral,
    g_auto_creative,
    g_auto_docs,
    g_auto_agentic,
    g_auto_security,
    g_auto_redteam,
    g_auto_blueteam,
    g_auto_pentest,
    g_auto_purpleteam,
    g_tools_specialist,
    g_auto_reasoning,
    g_auto_data,
    g_auto_compliance,
    g_auto_research,
    g_auto_vision,
    g_auto_audio,
    g_auto_music,
    g_auto_video,
    g_auto_voice,
    g_auto_documents,
    g_auto_cad,
    g_advanced,
    g_benchmark,
    g_vision_personas,
    g_browser_automation,
]

TEST_CATALOG: list[dict] = []
for _m in _GROUPS:
    TEST_CATALOG.extend(_m.TESTS)

__all__ = ["TEST_CATALOG"]
