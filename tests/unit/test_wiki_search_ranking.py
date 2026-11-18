"""Wiki search ranking: a test-section unit must not outrank the design unit.

TASK_WIKI_ZERO_DEBT_V1 Phase 7. The flat keyword score treated a design unit
and a test-section unit identically, so "workspace routing" surfaced
`unit-acceptance-s03_routing` ahead of the routing design unit.
"""

from __future__ import annotations

from portal_wiki.mcp import wiki_search


def test_workspace_routing_demotes_test_section_unit():
    """The Phase 7 defect: a test-section unit must not outrank the design unit."""
    result = wiki_search("workspace routing", top_k=3)
    ids = [r["unit_id"] for r in result["results"]]
    assert ids[0] == "unit-surface-router", ids
    assert "unit-acceptance-s03_routing" not in ids[:2], ids
