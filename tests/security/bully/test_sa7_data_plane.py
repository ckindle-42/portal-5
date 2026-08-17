from __future__ import annotations

import pytest

from portal.modules.security.core.bully.connectors import (
    CredentialedConnector,
    MissingCredentialsError,
    QueryAuditLog,
    QueryInPlaceConnector,
    QueryIntent,
)
from portal.modules.security.core.bully.data_plane import (
    CatalogPlanner,
    DataPlane,
    SourceCatalog,
    bind_semantics,
    discover_schema,
    profile_source,
    resolve_entity_links,
)
from portal.modules.security.core.bully.source_adapters import adapt


def test_record_adapter_accepts_documents_and_inventory_without_event_padding():
    advisory = adapt(
        records=[{"title": "Vendor bulletin", "ioc": "203.0.113.4", "content": "..."}],
        source_meta={
            "source_id": "vendor-advisories",
            "sourcetype": "threat-intel:advisory",
            "record_class": "advisory",
        },
    )
    inventory = adapt(
        records=[{"asset_id": "host-1", "owner": "alice@example.com"}],
        source_meta={
            "source_id": "asset-inventory",
            "sourcetype": "asset:inventory",
            "record_class": "inventory",
        },
    )
    assert "action_sequence" not in advisory
    assert "action_sequence" not in inventory
    assert advisory["artifacts"]["document_count"] == 1
    assert inventory["artifacts"]["inventory_ids"] == ["alice@example.com", "host-1"]


def test_schema_discovery_infers_nested_types_and_high_null_fields():
    schema = discover_schema(
        "events",
        [
            {"actor": {"id": "alice"}, "timestamp": 1, "rare": "x"},
            {"actor": {"id": "bob"}, "timestamp": 2},
            {"actor": {"id": "carol"}, "timestamp": 3},
        ],
    )
    assert schema.field("actor.id").observed_type == "string"
    assert schema.field("rare").null_rate > 0.5
    assert bind_semantics(schema)[0].meaning == "actor"


def test_semantic_binding_leaves_unavailable_meanings_absent():
    schema = discover_schema("docs", [{"body": "text", "created": "2026-01-01"}])
    bindings = {binding.meaning: binding for binding in bind_semantics(schema)}
    assert bindings["action"].present is False
    assert bindings["time"].present is True


def test_entity_links_require_explicit_alias_or_unified_id_and_keep_provenance():
    no_link = resolve_entity_links([("a", [{"user": "alice"}]), ("b", [{"user": "al1ce"}])])
    linked = resolve_entity_links(
        [("a", [{"user": "alice"}]), ("b", [{"user": "al1ce"}])],
        aliases={"al1ce": "alice"},
    )
    assert no_link == ()
    assert linked[0].confidence >= 0.9
    assert linked[0].provenance


def test_query_in_place_and_ingest_profile_to_same_catalog_contract():
    live = QueryInPlaceConnector(
        "splunk", lambda expression: [{"user": "alice", "time": 1}], language="spl"
    )
    intent = QueryIntent("find actor activity", entities=("alice",))
    result = live.read(intent)
    audit = QueryAuditLog()
    audit.record(result)
    profile = profile_source("splunk", live, result.records, source_meta={"benign_present": True})
    catalog = SourceCatalog([profile])
    plan = catalog.plan("seed-1")
    assert live.mode == "query_in_place"
    assert isinstance(result.native_query.expression, str)
    assert plan.source_order == ("splunk",)
    assert catalog.census()["sources"][0]["capabilities"]["queryable_in_place"] is True
    assert audit.replay_plan()[0]["language"] == "spl"


def test_credentials_fail_loudly_and_restricted_audit_cannot_export():
    live = QueryInPlaceConnector("private", lambda expression: [])
    with pytest.raises(MissingCredentialsError):
        CredentialedConnector(live, None).read(QueryIntent("read"))
    audit = QueryAuditLog()
    audit.record(live.read(QueryIntent("read")), sensitivity="restricted")
    with pytest.raises(PermissionError):
        audit.export()


def test_catalog_planner_changes_source_selection_from_capabilities_only():
    event_source = QueryInPlaceConnector("events", lambda expression: [])
    advisory_source = QueryInPlaceConnector("advisories", lambda expression: [])
    catalog = SourceCatalog(
        [
            profile_source(
                "events",
                event_source,
                [{"user": "alice", "time": 1}],
                source_meta={"capabilities": {"label_basis": True}},
            ),
            profile_source(
                "advisories",
                advisory_source,
                [{"title": "bulletin", "content": "text"}],
                source_meta={"capabilities": {"benign_present": True}},
            ),
        ]
    )
    planner = CatalogPlanner(catalog)
    alert_plan = planner.select(
        seed_id="alert",
        intent=QueryIntent("alert context", seed={"required_capabilities": ["label_basis"]}),
    )
    advisory_plan = planner.select(
        seed_id="advisory",
        intent=QueryIntent("advisory context", seed={"required_capabilities": ["benign_present"]}),
    )
    assert alert_plan.source_order == ("events",)
    assert advisory_plan.source_order == ("advisories",)
    assert any(
        "missing-capabilities" in reason
        for decision in advisory_plan.decisions
        if decision.source_id == "events"
        for reason in decision.reasons
    )


def test_data_plane_gate_and_drift_invalidation_are_explicit():
    plane = DataPlane()
    for source_id, records, meta in (
        ("events", [{"user": "alice", "time": 1}], {"capabilities": {"benign_present": True}}),
        ("advisories", [{"title": "bulletin", "content": "text"}], {}),
        ("case-history", [{"case_id": "c-1", "decision": "BENIGN_CLOSE"}], {}),
        ("asset-inventory", [{"asset_id": "host-1", "owner": "alice"}], {}),
        ("coverage", [{"rule_id": "r-1", "technique_id": "T1059"}], {}),
    ):
        connector = QueryInPlaceConnector(
            source_id, lambda _expression, values=records: values, language="api"
        )
        plane.connect(source_id, connector, records, source_meta=meta)
    assert plane.gate().passed is True
    assert plane.query("events", QueryIntent("read"))
    drift = plane.reprofile("events", [{"new_field": "changed"}])
    assert drift["drifted"] is True
    assert plane.catalog.get("events") is None
