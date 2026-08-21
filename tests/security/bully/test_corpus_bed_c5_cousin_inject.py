"""C.5 -- inject cousins of answer-key-confirmed BOTS techniques via Lane B.

Seeded: every injected cousin's parent technique is drawn from the answer
key; a RESCHEMA cousin shares no literal action token with its parent; the
`| delete` rollback tag is unique per cousin and accounts for exactly the
events that cousin shipped.
"""

from __future__ import annotations

from portal.modules.security.core.bully import corpus_bed, cousin_inject
from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY

_CE, _CL = 1534737600.0, 1534824000.0  # botsv3's real single-day range


def test_every_cousin_parent_technique_is_in_the_bots_answer_key() -> None:
    cousins = corpus_bed.plan_cousins(list(BOTS_ANSWER_KEY), corpus_earliest=_CE, corpus_latest=_CL)
    answer_key_techniques = {e.technique for e in BOTS_ANSWER_KEY}
    assert cousins  # the plan is non-empty
    assert all(c.parent_technique in answer_key_techniques for c in cousins)


def test_reschema_cousin_shares_no_literal_action_token_with_parent() -> None:
    entry = BOTS_ANSWER_KEY[0]  # T1558.004, wineventlog:security
    cousins = corpus_bed.plan_cousins(
        [entry],
        transformations=("RESCHEMA",),
        corpus_sourcetypes=("wineventlog:security", "aws:cloudtrail", "stream:dns"),
        corpus_earliest=_CE,
        corpus_latest=_CL,
    )
    assert len(cousins) == 1
    cousin = cousins[0]
    rendered_actions = {
        cousin_inject.render_cousin_event(cousin, step_index=i)["action"]
        for i in range(len(cousin.behavioural_spine))
    }
    assert rendered_actions.isdisjoint(set(entry.behavioural_spine))


def test_reidentity_cousin_keeps_parent_vocabulary() -> None:
    """REIDENTITY varies the principal, not the vocabulary -- its rendered
    actions ARE the parent's own spine tokens, unlike RESCHEMA/REVOCABULARY."""
    entry = BOTS_ANSWER_KEY[0]
    cousins = corpus_bed.plan_cousins(
        [entry], transformations=("REIDENTITY",), corpus_earliest=_CE, corpus_latest=_CL
    )
    cousin = cousins[0]
    rendered_actions = {
        cousin_inject.render_cousin_event(cousin, step_index=i)["action"]
        for i in range(len(cousin.behavioural_spine))
    }
    assert rendered_actions == set(entry.behavioural_spine)


def test_inject_cousins_evidence_origin_unique_per_cousin_and_count_exact(monkeypatch) -> None:
    calls: list[dict] = []

    def _fake_ship_batch(events, **kwargs):
        calls.append({"n": len(events), **kwargs})
        return {"ok": True, "count": len(events)}

    monkeypatch.setattr(cousin_inject, "ship_batch", _fake_ship_batch)

    cousins = corpus_bed.plan_cousins(
        list(BOTS_ANSWER_KEY),
        transformations=("REVOCABULARY", "RESCHEMA"),
        corpus_sourcetypes=("wineventlog:security", "stream:http", "xmlwineventlog:sysmon"),
        corpus_earliest=_CE,
        corpus_latest=_CL,
    )
    reports = cousin_inject.inject_cousins(
        cousins, dry_run=True, corpus_earliest=_CE, corpus_latest=_CL
    )

    assert len(reports) == len(cousins)
    origins_seen = [c["evidence_origin"] for c in calls]
    # every ship_batch call's evidence_origin is scoped to exactly one cousin
    assert len(origins_seen) == len(set(origins_seen)) or all(
        o.startswith("corpus:cousin:") for o in origins_seen
    )
    by_cousin_origin: dict[str, int] = {}
    for call in calls:
        by_cousin_origin[call["evidence_origin"]] = (
            by_cousin_origin.get(call["evidence_origin"], 0) + call["n"]
        )
    for report in reports:
        tag = f"corpus:cousin:{report.cousin_id}"
        # a `| delete` on this tag removes EXACTLY this cousin's events --
        # no more, no less.
        assert by_cousin_origin.get(tag, 0) == report.n_events
        assert report.n_events == len(cousins[reports.index(report)].behavioural_spine)


def test_scatter_cousin_splits_events_across_target_sourcetypes(monkeypatch) -> None:
    calls: list[dict] = []

    def _fake_ship_batch(events, **kwargs):
        calls.append({"n": len(events), **kwargs})
        return {"ok": True}

    monkeypatch.setattr(cousin_inject, "ship_batch", _fake_ship_batch)

    entry = corpus_bed.AnswerKeyEntry(
        dataset="botsv3",
        technique="T1558.004",
        behavioural_spine=("a", "b", "c", "d"),
        sourcetypes=("wineventlog:security",),
    )
    cousins = corpus_bed.plan_cousins(
        [entry],
        transformations=("SCATTER",),
        corpus_sourcetypes=("wineventlog:security", "aws:cloudtrail", "stream:dns"),
        corpus_earliest=_CE,
        corpus_latest=_CL,
    )
    cousin_inject.inject_cousins(cousins, dry_run=True, corpus_earliest=_CE, corpus_latest=_CL)

    sourcetypes_shipped = {c["sourcetype"] for c in calls}
    assert len(sourcetypes_shipped) > 1  # split across several real sourcetypes
