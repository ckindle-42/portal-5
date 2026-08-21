"""TASK_BULLY_INVESTIGATION_V1 (I.1b): behaviour classes inferred from data.

Four disjoint schemas express the same four behaviours under completely
different action vocabularies -- including a never-before-seen schema
(`zz:unknown`) no curated table has ever mapped. `infer_behaviors` must
recover four pure, cross-schema classes with no table consulted.
"""

from __future__ import annotations

from portal.modules.security.core.bully import behavior_inference as bi

SCHEMAS = ["wineventlog:security", "auditd:syscall", "app:json", "zz:unknown"]
ACTIONS = {
    "auth": ["4624", "USER_AUTH", "user.session.start", "qrx-77"],
    "list": ["4661", "SYSCALL_openat", "app.list", "qrx-04"],
    "launch": ["4688", "EXECVE", "app.launch", "qrx-19"],
    "egress": ["5156", "SYSCALL_sendto", "api.token.grant", "qrx-52"],
}

# Curated names, deliberately available ONLY for `name_from_answer_key` --
# discovery must never see this map.
_CURATED = {
    "4624": "auth",
    "USER_AUTH": "auth",
    "user.session.start": "auth",
    "qrx-77": "auth",
    "4661": "enumerate",
    "SYSCALL_openat": "enumerate",
    "app.list": "enumerate",
    "qrx-04": "enumerate",
    "4688": "execute",
    "EXECVE": "execute",
    "app.launch": "execute",
    "qrx-19": "execute",
    "5156": "c2_exfil",
    "SYSCALL_sendto": "c2_exfil",
    "api.token.grant": "c2_exfil",
    "qrx-52": "c2_exfil",
}


def _build_records() -> list[dict]:
    records = []
    for si, schema in enumerate(SCHEMAS):
        for i in range(20):
            ent = f"{schema}-ent-{i}"
            seq = [("auth", 0), ("list", 1), ("list", 2), ("launch", 3), ("egress", 4)]
            for role, t in seq:
                records.append(
                    {
                        "action": ACTIONS[role][si],
                        "entity": ent,
                        "_time": float(t),
                        "sourcetype": schema,
                    }
                )
    return records


RECORDS = _build_records()


def _profiles() -> list[bi.ActionProfile]:
    return bi.profile_actions(
        RECORDS,
        action_of=lambda r: r["action"],
        entity_of=lambda r: [r["entity"]],
        time_of=lambda r: r["_time"],
        sourcetype_of=lambda r: r["sourcetype"],
    )


def test_equivalent_actions_across_schemas_cluster_into_pure_classes():
    profiles = _profiles()
    behaviors = bi.infer_behaviors(profiles)
    assert len(behaviors) == 4
    for role, actions in ACTIONS.items():
        matches = [b for b in behaviors if set(b.members) == set(actions)]
        assert len(matches) == 1, f"{role} did not form a pure class: {behaviors}"


def test_schema_absent_from_every_curated_table_is_still_profiled_and_classified():
    profiles = _profiles()
    zz_profiles = [p for p in profiles if p.sourcetype == "zz:unknown"]
    assert len(zz_profiles) == 4
    behaviors = bi.infer_behaviors(profiles)
    zz_actions = {p.action for p in zz_profiles}
    classified = {a for b in behaviors for a in b.members}
    assert zz_actions <= classified


def test_report_shows_full_cross_schema_coverage_with_no_table():
    profiles = _profiles()
    behaviors = bi.infer_behaviors(profiles)
    report = bi.inference_report(profiles, behaviors)
    assert report["schemas_seen"] == 4
    assert report["classes_inferred"] == 4
    assert report["cross_schema_fraction"] == 1.0


def test_seeded_violation_discover_must_never_see_curated_name_as_feature():
    """Seeded violation: if a curated-class vote were smuggled in as a
    profile feature, distance would collapse trivially. Prove the actual
    feature vector has no such field."""
    profiles = _profiles()
    for p in profiles:
        vec = p.vector()
        assert "curated_class" not in vec
        assert "name" not in vec
    # And the classifier used for enrichment/naming is a distinct, separate
    # call -- infer_behaviors's signature accepts no curated-table argument.
    import inspect

    sig = inspect.signature(bi.infer_behaviors)
    assert "curated" not in sig.parameters


def test_action_below_min_occurrences_is_carried_unclassified():
    records = list(RECORDS) + [
        {
            "action": "rare-once",
            "entity": "wineventlog:security-ent-0",
            "_time": 5.0,
            "sourcetype": "wineventlog:security",
        }
    ]
    profiles = bi.profile_actions(
        records,
        action_of=lambda r: r["action"],
        entity_of=lambda r: [r["entity"]],
        time_of=lambda r: r["_time"],
        sourcetype_of=lambda r: r["sourcetype"],
    )
    assert "rare-once" not in {p.action for p in profiles}


def test_name_from_answer_key_changes_only_name_never_membership():
    profiles = _profiles()
    behaviors = bi.infer_behaviors(profiles)
    before_members = [tuple(sorted(b.members)) for b in behaviors]
    named = bi.name_from_answer_key(behaviors, lambda m: _CURATED.get(m, ""))
    after_members = [tuple(sorted(b.members)) for b in named]
    assert before_members == after_members
    assert all(b.name is not None for b in named)
    names = {b.name for b in named}
    assert names == {"auth", "enumerate", "execute", "c2_exfil"}
