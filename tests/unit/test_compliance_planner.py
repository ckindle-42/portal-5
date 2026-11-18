"""P7 the planner — the plan is the trace (checks Y17, Y18)."""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.planner import (
    QUESTION_PLANS,
    classify_question,
    execute_plan,
    plan_question,
)
from portal.modules.compliance.core.policy_graph import build_policy_graph

_TWELVE = {
    "Q01": "What does CIP-007-6 R2 Part 2.2 actually require right now?",
    "Q02": "Which of our procedures implement it?",
    "Q03": "Are our current procedures fully aligned with the latest version?",
    "Q04": "Where are gaps, inconsistencies, outdated language, or controls that no longer map?",
    "Q05": "Has a requirement changed since the procedure was written or last reviewed?",
    "Q06": "If we modify a procedure, what requirements and dependent controls could be affected?",
    "Q07": "What changes would bring a policy or procedure into better alignment?",
    "Q08": "Are we more restrictive than required, and is that intentional?",
    "Q09": "Where does the regulation permit flexibility our procedure does not use?",
    "Q10": "What documents, controls, evidence, systems or roles connect to a requirement?",
    "Q11": "If a new or revised standard becomes effective, which internal documents need review?",
    "Q12": "How should a proposed change be implemented while maintaining compliance?",
}


@pytest.fixture(scope="module")
def g():
    return build_policy_graph()


def test_all_twelve_questions_route_to_their_plan():
    for qid, text in _TWELVE.items():
        assert classify_question(text) == qid, (qid, text)
        steps, got = plan_question(text)
        assert got == qid
        assert [s.op for s in steps] == QUESTION_PLANS[qid]


def test_every_plan_op_is_one_of_the_six():
    six = {"resolve", "trace", "judge", "diff", "norms", "propose"}
    for ops in QUESTION_PLANS.values():
        assert set(ops) <= six


def test_answer_never_composed_from_an_unrun_step(g):
    # an op with no implementation records an error and never sets ran=True
    tr = execute_plan(_TWELVE["Q01"], "CIP-007-6 R2 Part 2.2", op_impls={})
    assert tr.steps[0].ran is False
    assert "error" in tr.steps[0].evidence
