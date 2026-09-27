"""P5 the council — sealed seats, cite-or-drop, quorum in code (checks Y09, Y04).

Model calls are injected as a fake so CI needs no network.
"""

from __future__ import annotations

import json

from portal.modules.compliance.core.council import run_council

_PACKET = {
    "governing_unit": {
        "ref": "CIP-007-6 R2 Part 2.2",
        "constraint": {
            "text": "evaluate security patches for applicability",
            "quantity": {"value": 35, "unit": "day", "direction": "max_interval"},
        },
        "subject": {"text": "Responsible Entity", "implied": True},
        "condition": [],
    },
    "applicability": {"state": "APPLIES", "reason": "in scope"},
    "reference_closure": ["CIP-007-6 R2 Part 2.1"],
    "exception_clauses": [],
    "candidates": [
        {
            "commitment_id": "c1",
            "text": "OT Security evaluates patches every 21 calendar days.",
            "actor_aligned": True,
            "quantity_outcome": "MORE_RESTRICTIVE",
        },
    ],
    "backstop_surplus": [],
}

_SEATS = [
    {"id": "s1", "label": "granite", "model": "m-granite"},
    {"id": "s2", "label": "qwen", "model": "m-qwen"},
    {"id": "s3", "label": "glm", "model": "m-glm"},
]


def _fake(responses: dict[str, str]):
    def fn(model: str, system: str, user: str) -> str:
        if "checking one thing only" in system:  # override call
            return responses.get(f"{model}:override", '{"overrides": false, "exception_ref": null}')
        return responses[model]

    return fn


def _vote(determination: str, cited_refs: list[str], rationale: str = "x") -> str:
    return json.dumps(
        {
            "determination": determination,
            "finding_type": None,
            "cited_refs": cited_refs,
            "confidence": 0.8,
            "rationale": rationale,
        }
    )


def test_unanimous_supported_with_citation():
    good = json.dumps(
        {
            "determination": "SUPPORTED",
            "finding_type": None,
            "cited_refs": ["CIP-007-6 R2 Part 2.2"],
            "confidence": 0.9,
            "rationale": "ok",
        }
    )
    r = run_council(
        _PACKET, _SEATS, seat_fn=_fake({"m-granite": good, "m-qwen": good, "m-glm": good})
    )
    assert r.determination == "SUPPORTED"
    assert r.quorum_required == 2
    assert r.votes["SUPPORTED"] == 3
    assert r.dissent == []


def test_cite_or_drop_removes_uncited_seat():
    cited = _vote("CONTRADICTED", ["CIP-007-6 R2 Part 2.2"])
    uncited = _vote("CONTRADICTED", [])
    offpacket = _vote("CONTRADICTED", ["CIP-099-1 R9"])
    r = run_council(
        _PACKET, _SEATS, seat_fn=_fake({"m-granite": cited, "m-qwen": uncited, "m-glm": offpacket})
    )
    dropped = [o for o in r.opinions if o.dropped]
    assert {o.seat_id for o in dropped} == {"s2", "s3"}
    # only one valid vote, quorum 2 not met -> ESCALATE
    assert r.determination == "ESCALATE"
    assert r.sme_decision_kind == "S04_INTERPRETATION_DISPUTE"


def test_split_council_escalates_as_s04():
    a = _vote("SUPPORTED", ["CIP-007-6 R2 Part 2.2"])
    b = _vote("CONTRADICTED", ["CIP-007-6 R2 Part 2.2"])
    c = _vote("PARTIAL", ["CIP-007-6 R2 Part 2.2"])
    r = run_council(_PACKET, _SEATS, seat_fn=_fake({"m-granite": a, "m-qwen": b, "m-glm": c}))
    assert r.determination == "ESCALATE"
    assert r.sme_decision_kind == "S04_INTERPRETATION_DISPUTE"


def test_insufficient_is_not_a_vote():
    ins = _vote("INSUFFICIENT", [], "packet incomplete")
    sup = _vote("SUPPORTED", ["CIP-007-6 R2 Part 2.2"])
    r = run_council(_PACKET, _SEATS, seat_fn=_fake({"m-granite": ins, "m-qwen": ins, "m-glm": sup}))
    # 1 vote, quorum 2 -> ESCALATE, silence never becomes a guess
    assert r.determination == "ESCALATE"


def test_missing_seat_output_does_not_shrink_quorum_denominator():
    supported = _vote("SUPPORTED", ["CIP-007-6 R2 Part 2.2"])

    def fn(model, system, user):
        if model == "m-granite":
            return supported
        if model == "m-qwen":
            return ""
        raise TimeoutError("controlled missing-seat timeout")

    r = run_council(_PACKET, _SEATS, seat_fn=fn)
    assert r.roster == 3
    assert r.quorum_required == 2
    assert r.votes["SUPPORTED"] == 1
    assert sum(r.votes.values()) == 1
    assert r.determination == "ESCALATE"


def test_all_seats_failing_escalates_without_affirmative_vote():
    def fn(model, system, user):
        raise TimeoutError("controlled all-seat failure")

    r = run_council(_PACKET, _SEATS, seat_fn=fn)
    assert r.roster == 3
    assert r.quorum_required == 2
    assert r.votes == {
        "SUPPORTED": 0,
        "PARTIAL": 0,
        "CONTRADICTED": 0,
        "ABSENT": 0,
        "INSUFFICIENT": 0,
    }
    assert r.determination == "ESCALATE"
    assert all(
        not opinion.valid and opinion.dropped.startswith("seat error:") for opinion in r.opinions
    )


def test_json_inside_reasoning_prose_is_not_salvaged_as_a_vote():
    embedded = (
        "I considered the possible outputs, including "
        '{"determination":"SUPPORTED","cited_refs":["CIP-007-6 R2 Part 2.2"],'
        '"rationale":"example only"}, but this is not a final JSON answer.'
    )
    r = run_council(_PACKET, _SEATS, seat_fn=_fake({seat["model"]: embedded for seat in _SEATS}))
    assert r.determination == "ESCALATE"
    assert r.quorum_required == 2
    assert all(not opinion.valid for opinion in r.opinions)


def test_malformed_contract_and_nonexact_reference_are_not_votes():
    malformed = json.dumps(
        {
            "determination": "SUPPORTED",
            "finding_type": "null",
            "cited_refs": ["CIP-007-6 R2 Part 2.2"],
            "confidence": 0.9,
            "rationale": "example",
        }
    )
    fuzzy_reference = _vote("SUPPORTED", ["premise mentioning CIP-007-6 R2 Part 2.2"])
    r = run_council(
        _PACKET,
        _SEATS,
        seat_fn=_fake(
            {
                "m-granite": malformed,
                "m-qwen": fuzzy_reference,
                "m-glm": malformed,
            }
        ),
    )
    assert r.determination == "ESCALATE"
    assert r.quorum_required == 2
    assert all(not opinion.votes for opinion in r.opinions)


def test_exception_override_overturns_a_violation():
    contra = json.dumps(
        {
            "determination": "CONTRADICTED",
            "finding_type": "CONTRADICTION",
            "cited_refs": ["CIP-007-6 R2 Part 2.2"],
            "confidence": 0.8,
            "rationale": "too slow",
        }
    )
    overr = json.dumps(
        {
            "overrides": True,
            "exception_ref": "CIP-007-6 R2 Part 2.1",
            "rationale": "derogation applies",
        }
    )
    r = run_council(
        _PACKET,
        _SEATS,
        seat_fn=_fake(
            {
                "m-granite": contra,
                "m-qwen": contra,
                "m-glm": contra,
                "m-granite:override": overr,
                "m-qwen:override": overr,
                "m-glm:override": overr,
            }
        ),
        reference_texts={"CIP-007-6 R2 Part 2.1": "Exception language ..."},
    )
    assert r.override and r.override["overrides"]
    assert r.determination == "SUPPORTED"
    assert "overturned by exception" in r.rationale


def test_no_seat_sees_another_seats_answer():
    # the fake is called once per seat with only (model, system, user); the
    # packet passed as `user` must never contain a prior determination field.
    seen = []

    def fn(model, system, user):
        seen.append(user)
        return json.dumps(
            {
                "determination": "SUPPORTED",
                "finding_type": None,
                "cited_refs": ["CIP-007-6 R2 Part 2.2"],
                "confidence": 0.8,
                "rationale": "x",
            }
        )

    run_council(_PACKET, _SEATS, seat_fn=fn)
    for u in seen:
        assert "prior_determination" not in u and "gold" not in u.lower()
        assert "approval" not in u.lower()
