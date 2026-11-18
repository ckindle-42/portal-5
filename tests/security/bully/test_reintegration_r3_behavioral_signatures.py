"""R.3 -- behavioural signatures carry levelled features; retrieval is
behaviour-first, so a cross-vocabulary anchor is actually in the candidate set."""

from __future__ import annotations

from portal.modules.security.core.bully import pyramid, signatures


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
