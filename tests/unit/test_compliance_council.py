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
    cited = json.dumps(
        {"determination": "CONTRADICTED", "cited_refs": ["CIP-007-6 R2 Part 2.2"], "rationale": "x"}
    )
    uncited = json.dumps({"determination": "CONTRADICTED", "cited_refs": [], "rationale": "x"})
    offpacket = json.dumps(
        {"determination": "CONTRADICTED", "cited_refs": ["CIP-099-1 R9"], "rationale": "x"}
    )
    r = run_council(
        _PACKET, _SEATS, seat_fn=_fake({"m-granite": cited, "m-qwen": uncited, "m-glm": offpacket})
    )
    dropped = [o for o in r.opinions if o.dropped]
    assert {o.seat_id for o in dropped} == {"s2", "s3"}
    # only one valid vote, quorum 2 not met -> ESCALATE
    assert r.determination == "ESCALATE"
    assert r.sme_decision_kind == "S04_INTERPRETATION_DISPUTE"


def test_split_council_escalates_as_s04():
    a = json.dumps(
        {"determination": "SUPPORTED", "cited_refs": ["CIP-007-6 R2 Part 2.2"], "rationale": "x"}
    )
    b = json.dumps(
        {"determination": "CONTRADICTED", "cited_refs": ["CIP-007-6 R2 Part 2.2"], "rationale": "x"}
    )
    c = json.dumps(
        {"determination": "PARTIAL", "cited_refs": ["CIP-007-6 R2 Part 2.2"], "rationale": "x"}
    )
    r = run_council(_PACKET, _SEATS, seat_fn=_fake({"m-granite": a, "m-qwen": b, "m-glm": c}))
    assert r.determination == "ESCALATE"
    assert r.sme_decision_kind == "S04_INTERPRETATION_DISPUTE"


def test_insufficient_is_not_a_vote():
    ins = json.dumps(
        {"determination": "INSUFFICIENT", "cited_refs": [], "rationale": "packet incomplete"}
    )
    sup = json.dumps(
        {"determination": "SUPPORTED", "cited_refs": ["CIP-007-6 R2 Part 2.2"], "rationale": "x"}
    )
    r = run_council(_PACKET, _SEATS, seat_fn=_fake({"m-granite": ins, "m-qwen": ins, "m-glm": sup}))
    # 1 vote, quorum 2 -> ESCALATE, silence never becomes a guess
    assert r.determination == "ESCALATE"


def test_exception_override_overturns_a_violation():
    contra = json.dumps(
        {
            "determination": "CONTRADICTED",
            "finding_type": "CONTRADICTION",
            "cited_refs": ["CIP-007-6 R2 Part 2.2"],
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
                "cited_refs": ["CIP-007-6 R2 Part 2.2"],
                "rationale": "x",
            }
        )

    run_council(_PACKET, _SEATS, seat_fn=fn)
    for u in seen:
        assert "prior_determination" not in u and "gold" not in u.lower()
        assert "approval" not in u.lower()
