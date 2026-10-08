"""Shared fixtures for the SA2 discovery-lane tests: a deterministic,
fully offline read-only snapshot (no embed service, no LanceDB) plus a small
synthetic real-vs-real corpus spanning two source classes with a genuine
cross-class technique overlap and a mix of covered/near-miss/missed/no-signal
detector outcomes.

Specimen layout (all `source_lane: attack_data`, i.e. real, never forged):
  - sysmon-kerberoast   (windows:sysmon, T1558.003, MISSED) -- its nearest
    real structural cousin, by construction, is the cross-class Okta
    specimen below, not the same-class distractor.
  - sysmon-unrelated    (windows:sysmon, T1059.001, COVERED) -- FLOOR/floor
    distractor, unrelated technique.
  - okta-kerberoast-cousin (OktaIM2:log, T1558.003, no detector signal) --
    the genuine cross-class cousin of sysmon-kerberoast.
  - okta-unrelated      (OktaIM2:log, T1621, NEAR_MISS) -- distractor.
  - sysmon-t1078-fired  (windows:sysmon, T1078, COVERED)
  - okta-t1078-missed   (OktaIM2:log, T1078, MISSED) -- same technique as the
    sysmon T1078 row but a different class response -> coverage asymmetry.
"""

from __future__ import annotations

from typing import Any

from portal.modules.security.core.bully import signatures


class FixtureSnapshot:
    """knn ignores true nearest-neighbor semantics -- cousin_engine.grade
    scores every returned candidate via its own field-level decomposition,
    so returning the full record pool (optionally filtered) each time is
    sufficient and fully deterministic."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = list(records)

    def knn(self, query: str, k: int, filters: dict[str, Any] | None = None):
        pool = self.records
        if filters:
            pool = [r for r in pool if all(r.get(key) == value for key, value in filters.items())]
        return [(record, 0.01 * index) for index, record in enumerate(pool[:k])]

    def stats(self) -> dict[str, Any]:
        return {"row_count": len(self.records)}


def _engine_view(
    specimen_id: str,
    *,
    technique_ids: list[str],
    family: str,
    source_class: str,
    action_sequence: list[str],
    detector_outcomes: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "episode_view": {"episode_id": specimen_id, "target_host": "corpus-attack-data"},
        "telemetry_view": {
            "action_sequence": action_sequence,
            "event_graph": {"ordered": action_sequence},
            "parameter_families": {},
            "context_topology": {"family": family, "source_classes": [source_class]},
            "artifacts": {},
            "attack_mappings": [{"technique_id": t} for t in technique_ids],
            "telemetry_shape": {"sourcetypes": [source_class], "source_class": source_class},
            "detector_outcomes": detector_outcomes or {},
        },
    }


def make_specimen(
    specimen_id: str,
    *,
    technique_ids: list[str],
    family: str,
    source_class: str,
    action_sequence: list[str],
    detector_outcomes: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "specimen_id": specimen_id,
        "source_lane": "attack_data",
        "source_class": source_class,
        "engine_view": _engine_view(
            specimen_id,
            technique_ids=technique_ids,
            family=family,
            source_class=source_class,
            action_sequence=action_sequence,
            detector_outcomes=detector_outcomes,
        ),
    }


def specimen_to_record(specimen: dict[str, Any]) -> dict[str, Any]:
    engine_view = specimen["engine_view"]
    signature = signatures.build_signature(
        engine_view["episode_view"], engine_view["telemetry_view"]
    )
    return {
        **signatures.reference_record_fields(signature),
        "record_id": specimen["specimen_id"],
        "signature_id": specimen["specimen_id"],
        "kind": "specimen_parent",
        "source_class": specimen["source_class"],
    }


def build_corpus() -> dict[str, Any]:
    specimens = [
        make_specimen(
            "sysmon-kerberoast",
            technique_ids=["T1558.003"],
            family="attack:T1558.003",
            source_class="windows:sysmon",
            action_sequence=["logon", "ticket_request", "ticket_export", "exfil"],
            detector_outcomes={"detector-kerberoast": "missed"},
        ),
        make_specimen(
            "sysmon-unrelated",
            technique_ids=["T1059.001"],
            family="attack:T1059.001",
            source_class="windows:sysmon",
            action_sequence=["powershell_launch", "download_cradle"],
            detector_outcomes={"detector-psh": "fired"},
        ),
        make_specimen(
            "okta-kerberoast-cousin",
            technique_ids=["T1558.003"],
            family="attack:T1558.003",
            source_class="OktaIM2:log",
            action_sequence=["logon", "ticket_request", "service_account_ticket"],
            detector_outcomes={},
        ),
        make_specimen(
            "okta-unrelated",
            technique_ids=["T1621"],
            family="attack:T1621",
            source_class="OktaIM2:log",
            action_sequence=["mfa_fatigue_push"],
            detector_outcomes={"detector-mfa-fatigue": "partial"},
        ),
        make_specimen(
            "sysmon-t1078-fired",
            technique_ids=["T1078"],
            family="attack:T1078",
            source_class="windows:sysmon",
            action_sequence=["valid_account_logon", "admin_share_access"],
            detector_outcomes={"detector-valid-accounts": "fired"},
        ),
        make_specimen(
            "okta-t1078-missed",
            technique_ids=["T1078"],
            family="attack:T1078",
            source_class="OktaIM2:log",
            action_sequence=["okta_valid_account_logon", "impossible_travel"],
            detector_outcomes={"detector-valid-accounts-okta": "missed"},
        ),
        make_specimen(
            "sysmon-t1021-lateral",
            technique_ids=["T1021.002"],
            family="attack:T1021.002",
            source_class="windows:sysmon",
            action_sequence=["smb_session_setup", "admin_share_write", "service_create"],
            detector_outcomes={"detector-smb-lateral": "missed"},
        ),
        make_specimen(
            "okta-t1021-cousin",
            technique_ids=["T1021.002"],
            family="attack:T1021.002",
            source_class="OktaIM2:log",
            action_sequence=["smb_session_setup", "admin_share_write", "okta_session_token_reuse"],
            detector_outcomes={},
        ),
    ]
    return {
        "schema": "SPECIMEN_CORPUS_V2",
        "snapshot_hash": "fixture-corpus",
        "specimens": specimens,
        "per_lane_counts": {"attack_data": len(specimens), "replay_mutation": 0, "live_lab": 0},
    }


def build_snapshot(corpus: dict[str, Any]) -> FixtureSnapshot:
    records = [specimen_to_record(s) for s in corpus["specimens"]]
    return FixtureSnapshot(records)
