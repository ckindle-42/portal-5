"""R.5b -- schema-agnostic source universe + R.5b-fix cohesive-identifier."""

from __future__ import annotations

import uuid

from portal.modules.security.core.bully import field_roles as fr
from portal.modules.security.core.bully import universe

# ── universe.py ──────────────────────────────────────────────────────────────


def test_invents_many_sources_across_info_levels_and_naming_conventions() -> None:
    lot = universe.build_universe(
        n_sources=40,
        background_n=800,
        cousins=[
            {
                "parent_family": "priv-esc",
                "parent_technique": "T1078",
                "behavioural_spine": ["auth", "enumerate", "escalate"],
                "transformation": t,
            }
            for t in ("REVOCABULARY", "REIDENTITY", "REORDER_MINOR", "RESCHEMA", "DOWNLEVEL")
        ],
        seed=42,
    )
    assert len(lot.shapes) >= 30
    assert len({s.info_level for s in lot.shapes}) >= 3
    assert len({s.naming for s in lot.shapes}) >= 4
    ratio = lot.implant_count / (lot.benign_count + lot.implant_count)
    assert ratio < 0.05


def test_no_indexable_event_carries_any_label_field() -> None:
    """Seeded violation: label leakage into grader-visible events would let
    the grader cheat by reading the answer -- assert it never happens."""
    lot = universe.build_universe(
        n_sources=10,
        background_n=100,
        cousins=[
            {
                "parent_family": "x",
                "parent_technique": "T1078",
                "behavioural_spine": ["auth", "escalate"],
            }
        ],
        seed=1,
    )
    for record in lot.indexable():
        assert "_labels" not in record
        assert "true_behavior_class" not in record
        assert "malicious" not in record


def test_reschema_cousin_shares_zero_literal_tokens_with_parent_vocabulary() -> None:
    lot = universe.build_universe(
        n_sources=15,
        background_n=50,
        cousins=[
            {
                "parent_family": "x",
                "parent_technique": "T1078",
                "behavioural_spine": ["auth", "enumerate", "escalate"],
                "transformation": "RESCHEMA",
            }
        ],
        seed=7,
    )
    cousin_events = [e for e in lot.events if e["_labels"]["injected"]]
    assert cousin_events
    # the realized values come from the target shape's OWN behavior_realization
    # table, not any parent-vocabulary literal -- confirm none of the AWS/Win
    # canonical verb tokens leak into the realized event payloads.
    parent_tokens = {"AssumeRole", "ListBuckets", "PutRolePolicy", "secretsdump", "kerberos"}
    for ev in cousin_events:
        values = {str(v) for v in _flatten_values(ev["event"])}
        assert not (values & parent_tokens)


def _flatten_values(d):
    for v in d.values():
        if isinstance(v, dict):
            yield from _flatten_values(v)
        else:
            yield v


# ── R.5b-fix: cohesive-identifier recognition ────────────────────────────────


def test_busy_source_cohesive_counter_id_column_resolves_entity_at_high_cardinality() -> None:
    """Seeded violation: 2800 distinct svcNNN values over 3000 records (a busy
    real source's OWN identity column) must resolve ENTITY even though
    distinct_ratio (~0.93) is above the near-unique threshold -- under the
    pre-fix rule this was demoted to PAYLOAD and the source read
    INSUFFICIENT_VIEW."""
    records = [{"srcId": f"svc{i % 2800}", "op": "list" if i % 2 else "get"} for i in range(3000)]
    role_map = fr.infer_field_roles(records, source_id="busy")
    assert role_map.profiles["srcId"].role == "ENTITY"
    assert role_map.entity_coverage > 0.0


def test_guid_per_record_still_resolves_payload_not_entity() -> None:
    """GUIDs are cohesive by template but are the archetypal per-record id,
    never a pivotable entity -- the cohesion override must not apply to them."""
    records = [
        {"requestID": str(uuid.uuid4()), "user": f"alice{i % 3}", "eventTime": float(i)}
        for i in range(50)
    ]
    role_map = fr.infer_field_roles(records, source_id="record-ids")
    assert role_map.profiles["requestID"].role == "PAYLOAD"
    assert role_map.profiles["user"].role == "ENTITY"


def test_incohesive_high_cardinality_free_text_stays_payload() -> None:
    records = [
        {"note": f"free text {i} unrelated content spanning several words", "id": i}
        for i in range(100)
    ]
    role_map = fr.infer_field_roles(records, source_id="freetext")
    assert role_map.profiles["note"].role != "ENTITY"
