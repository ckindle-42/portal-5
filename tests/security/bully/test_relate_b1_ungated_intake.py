"""B.1 -- ungated stream intake: annotation semantics, never permission
semantics. A source with zero proven capabilities is still queryable and
yields annotated, low-confidence records; no read path can deny on
capability grounds."""

from __future__ import annotations

from portal.modules.security.core.bully.connectors import IterableIngestConnector, QueryIntent
from portal.modules.security.core.bully.data_plane import CAPABILITIES, DataPlane


def test_zero_capability_source_is_still_queryable_and_annotated():
    plane = DataPlane()
    connector = IterableIngestConnector(
        "opaque-blob-feed", [{"raw": "unstructured payload one"}, {"raw": "payload two"}]
    )
    plane.connect(
        "opaque-blob-feed",
        connector,
        connector.records,
        source_meta={"capabilities": dict.fromkeys(CAPABILITIES, False)},
    )

    result, annotation = plane.query_annotated(
        "opaque-blob-feed", QueryIntent(purpose="hunt-seed-scope")
    )

    assert len(result.records) == 2
    assert annotation["confidence_hint"] == 0.0
    assert annotation["missing_capabilities"] == sorted(CAPABILITIES)
    assert all(present is False for present in annotation["capabilities"].values())


def test_no_read_path_denies_on_capability_grounds():
    plane = DataPlane()
    connector = IterableIngestConnector("bare-source", [{"v": 1}])
    plane.connect(
        "bare-source",
        connector,
        connector.records,
        source_meta={"capabilities": dict.fromkeys(CAPABILITIES, False)},
    )
    # plan() may deprioritise a zero-capability source for a *specific*
    # requirement set, but that only affects source_order/ranking -- the
    # underlying read is never blocked.
    plan = plane.plan(
        "seed-1", QueryIntent(purpose="x", seed={"required_capabilities": CAPABILITIES})
    )
    decision = next(d for d in plan.decisions if d.source_id == "bare-source")
    assert decision.selected is False  # deprioritised in this plan's ranking...
    result = plane.query("bare-source", QueryIntent(purpose="x"))  # ...but never denied
    assert len(result.records) == 1


def test_fully_capable_source_gets_full_confidence_hint():
    plane = DataPlane()
    connector = IterableIngestConnector("rich-source", [{"actor": "a", "asset": "b", "time": 1}])
    plane.connect(
        "rich-source",
        connector,
        connector.records,
        source_meta={"capabilities": dict.fromkeys(CAPABILITIES, True)},
    )
    _result, annotation = plane.query_annotated("rich-source", QueryIntent(purpose="x"))
    assert annotation["confidence_hint"] == 1.0
    assert annotation["missing_capabilities"] == []
