"""R.3 -- behavioural signatures carry levelled features; retrieval is
behaviour-first, so a cross-vocabulary anchor is actually in the candidate set."""

from __future__ import annotations

from portal.modules.security.core.bully import cousin_engine, pyramid, signatures


def _build(action_sequence: list[str], **extra) -> signatures.BehaviorSignature:
    episode_view = {"episode_id": "ep-1", "target_host": "h1"}
    telemetry_view = {"action_sequence": action_sequence, **extra}
    return signatures.build_signature(episode_view, telemetry_view)


def test_signature_carries_levelled_features_and_behavior_spine() -> None:
    sig = _build(["AssumeRole", "ListBuckets", "AddRoleToInstanceProfile"])
    assert sig.behavior_spine == ("auth", "enumerate", "escalate")
    assert len(sig.levelled_features) == 3
    assert all(f["level"] == pyramid.L3_BEHAVIOR for f in sig.levelled_features)


def test_unmapped_verbs_do_not_pollute_the_spine() -> None:
    sig = _build(["QuizzicalPandaJamboree"])
    assert sig.behavior_spine == ()
    assert sig.levelled_features[0]["level"] == pyramid.L2_TOOL


class _BehaviorSpineOnlySnapshot:
    """A retrieval fixture that ONLY returns the AWS anchor on the
    behaviour-spine query -- token/semantic/attack/family/motif queries all
    return nothing, simulating true cross-vocabulary disjointness."""

    def __init__(self, anchor_record: dict) -> None:
        self.anchor_record = anchor_record
        self.queries: list[str] = []

    def knn(self, query, k, filters=None):
        self.queries.append(query)
        if query.startswith("behavior spine:"):
            return [(self.anchor_record, 0.4)]
        return []

    def stats(self):
        return {"row_count": 1}


def test_cross_vocabulary_anchor_retrieved_by_behavioral_spine() -> None:
    """Seeded violation: under token-only retrieval (semantic/attack/family/
    motif, which this fixture deliberately starves) the AWS anchor is NEVER
    retrieved for a Windows-native subject -- only the behaviour-spine axis
    recovers it."""
    aws_anchor_sig = _build(["AssumeRole", "ListBuckets", "AddRoleToInstanceProfile"])
    anchor_record = signatures.reference_record_fields(aws_anchor_sig)
    anchor_record["record_id"] = "anchor-aws-1"

    win_subject = _build(["kerberos tgt request", "net user /domain", "secretsdump"])
    snapshot = _BehaviorSpineOnlySnapshot(anchor_record)

    receipt = cousin_engine.retrieve_candidate_axes(win_subject, snapshot, k=8)

    assert receipt.sources["behavior_spine"] == 1
    candidate_ids = {c["record"].get("record_id") for c in receipt.candidates}
    assert "anchor-aws-1" in candidate_ids
