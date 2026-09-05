"""TASK_COMPLIANCE_REASONING_V2 P5.2 — reviewed obligation-expression evaluation."""

from __future__ import annotations

import pytest

from portal.modules.compliance.core.comparison import ExpressionNode, evaluate_expression


def _atom(atom_id: str) -> ExpressionNode:
    return ExpressionNode(kind="ATOM", atom_id=atom_id)


def test_single_atom_reflects_its_own_status():
    node = _atom("A1")
    assert evaluate_expression(node, {"A1": "SUPPORTED"})[0] == "SUPPORTED"
    assert evaluate_expression(node, {"A1": "CONTRADICTED"})[0] == "CONTRADICTED"
    assert evaluate_expression(node, {"A1": "UNRESOLVED"})[0] == "UNRESOLVED"


def test_atom_with_no_recorded_status_is_unresolved_not_a_guess():
    node = _atom("MISSING")
    status, reason = evaluate_expression(node, {})
    assert status == "UNRESOLVED"
    assert "no status recorded" in reason


def test_all_of_requires_every_conjunct_supported():
    node = ExpressionNode(kind="ALL_OF", children=[_atom("A1"), _atom("A2")])
    assert evaluate_expression(node, {"A1": "SUPPORTED", "A2": "SUPPORTED"})[0] == "SUPPORTED"
    assert evaluate_expression(node, {"A1": "SUPPORTED", "A2": "UNRESOLVED"})[0] == "UNRESOLVED"


def test_all_of_any_contradiction_makes_the_whole_thing_contradicted():
    node = ExpressionNode(kind="ALL_OF", children=[_atom("A1"), _atom("A2")])
    status, _ = evaluate_expression(node, {"A1": "SUPPORTED", "A2": "CONTRADICTED"})
    assert status == "CONTRADICTED"


def test_any_of_needs_only_one_supported_branch():
    node = ExpressionNode(kind="ANY_OF", children=[_atom("A1"), _atom("A2")])
    assert evaluate_expression(node, {"A1": "CONTRADICTED", "A2": "SUPPORTED"})[0] == "SUPPORTED"


def test_any_of_every_branch_contradicted_is_contradicted():
    node = ExpressionNode(kind="ANY_OF", children=[_atom("A1"), _atom("A2")])
    status, _ = evaluate_expression(node, {"A1": "CONTRADICTED", "A2": "CONTRADICTED"})
    assert status == "CONTRADICTED"


def test_any_of_neither_supported_nor_all_contradicted_is_unresolved():
    node = ExpressionNode(kind="ANY_OF", children=[_atom("A1"), _atom("A2")])
    status, _ = evaluate_expression(node, {"A1": "CONTRADICTED", "A2": "UNRESOLVED"})
    assert status == "UNRESOLVED"


def test_at_least_n_supported_when_threshold_met():
    node = ExpressionNode(kind="AT_LEAST_N", n=2, children=[_atom("A1"), _atom("A2"), _atom("A3")])
    status, reason = evaluate_expression(
        node, {"A1": "SUPPORTED", "A2": "SUPPORTED", "A3": "UNRESOLVED"}
    )
    assert status == "SUPPORTED"
    assert "2 of 3" in reason


def test_at_least_n_contradicted_when_threshold_impossible():
    node = ExpressionNode(kind="AT_LEAST_N", n=2, children=[_atom("A1"), _atom("A2"), _atom("A3")])
    status, _ = evaluate_expression(
        node, {"A1": "CONTRADICTED", "A2": "CONTRADICTED", "A3": "SUPPORTED"}
    )
    assert status == "CONTRADICTED"  # only 1 branch remains viable, need 2


def test_at_least_n_unresolved_while_still_possible():
    node = ExpressionNode(kind="AT_LEAST_N", n=2, children=[_atom("A1"), _atom("A2")])
    status, _ = evaluate_expression(node, {"A1": "SUPPORTED", "A2": "UNRESOLVED"})
    assert status == "UNRESOLVED"


def test_nested_expression_evaluates_recursively():
    """(A1 AND A2) OR A3"""
    node = ExpressionNode(
        kind="ANY_OF",
        children=[ExpressionNode(kind="ALL_OF", children=[_atom("A1"), _atom("A2")]), _atom("A3")],
    )
    status, _ = evaluate_expression(
        node, {"A1": "SUPPORTED", "A2": "CONTRADICTED", "A3": "SUPPORTED"}
    )
    assert status == "SUPPORTED"  # the A3 branch alone is enough


def test_malformed_nodes_are_rejected_at_construction():
    with pytest.raises(ValueError, match="atom_id"):
        ExpressionNode(kind="ATOM")
    with pytest.raises(ValueError, match="n > 0"):
        ExpressionNode(kind="AT_LEAST_N", n=0, children=[_atom("A1")])
    with pytest.raises(ValueError, match="kind must be"):
        ExpressionNode(kind="XOR")


def test_node_with_no_children_is_unresolved_not_a_crash():
    node = ExpressionNode(kind="ALL_OF", children=[])
    status, reason = evaluate_expression(node, {})
    assert status == "UNRESOLVED"
    assert "no children" in reason
