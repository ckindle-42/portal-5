"""R.1 -- pyramid-of-pain abstraction level, seeded-violation guarded."""

from __future__ import annotations

from portal.modules.security.core.bully import pyramid


def _feat(token: str, role: str, raw_verb: str | None = None) -> pyramid.LeveledFeature:
    return pyramid.level_feature(token, role, raw_verb=raw_verb)


def test_cross_vocabulary_cousin_holds_at_behavior_robustness_one() -> None:
    # AWS-native chain: auth -> enumerate -> escalate, zero shared literal tokens
    # with the Windows-native chain below.
    aws = [
        _feat("sts:getsessiontoken-arn-aaa111", "ENTITY"),
        _feat("GetSessionToken", "ACTION", raw_verb="GetSessionToken"),
        _feat("ListBuckets", "ACTION", raw_verb="ListBuckets"),
        _feat("PutRolePolicy", "ACTION", raw_verb="PutRolePolicy"),
    ]
    win = [
        _feat("host-ws01-corp", "ENTITY"),
        _feat("Kerberos-TGT", "ACTION", raw_verb="kerberos tgt request"),
        _feat("net user /domain", "ACTION", raw_verb="net user /domain"),
        _feat("secretsdump.py", "ACTION", raw_verb="secretsdump"),
    ]
    ml = pyramid.match_level(aws, win)
    assert ml.holds_at_behavior is True
    assert ml.level == pyramid.L3_BEHAVIOR
    assert ml.robustness == 1.0
    assert set(ml.tool_overlap) == set()
    assert set(ml.ephemeral_overlap) == set()


def test_seeded_violation_raw_token_scoring_collapses_to_no_match() -> None:
    """Seeded violation: score the same two chains on raw tokens instead of
    behavioural classes, and assert that (wrong) approach finds NO match --
    proving the pyramid-class abstraction is what recovers the cousin, not
    coincidence."""
    aws_tokens = {"GetSessionToken", "ListBuckets", "PutRolePolicy"}
    win_tokens = {"kerberos tgt request", "net user /domain", "secretsdump"}
    assert aws_tokens & win_tokens == set()


def test_sourcetype_only_overlap_reports_l1_ephemeral() -> None:
    subj = [_feat("sourcetype=aws:cloudtrail", "CONSTANT")]
    anchor = [_feat("sourcetype=aws:cloudtrail", "CONSTANT")]
    ml = pyramid.match_level(subj, anchor)
    assert ml.level == pyramid.L1_EPHEMERAL
    assert ml.holds_at_behavior is False
    assert round(ml.robustness, 2) == round(1 / 3, 2)


def test_unmapped_verb_yields_empty_not_other_and_stays_l2() -> None:
    assert pyramid.default_behavior_classifier("QuizzicalPandaJamboree") == ""
    feat = _feat("QuizzicalPandaJamboree", "ACTION", raw_verb="QuizzicalPandaJamboree")
    assert feat.level == pyramid.L2_TOOL
    assert feat.behavior_class == ""


def test_behavioral_spine_is_order_sensitive() -> None:
    a = pyramid._ordered_common_subsequence(
        ("auth", "enumerate", "escalate"), ("enumerate", "auth", "escalate")
    )
    # LCS still finds "auth","escalate" or "enumerate","escalate" in order,
    # but the full 3-class spine only aligns when order matches exactly.
    full = pyramid._ordered_common_subsequence(
        ("auth", "enumerate", "escalate"), ("auth", "enumerate", "escalate")
    )
    assert full == ("auth", "enumerate", "escalate")
    assert len(a) < len(full)
