"""Reviewed obligation-expression evaluation (P5.2).

Given already-classified per-atom statuses (SUPPORTED/CONTRADICTED/
UNRESOLVED — however they were produced: SME review, a future bounded-LLM
comparison, or a test fixture), evaluates the compound boolean structure a
requirement's text expresses: every mandatory ``ALL_OF`` conjunct must be
addressed; an ``ANY_OF`` alternative needs at least one supported branch;
``AT_LEAST_N`` needs ``n`` supported branches. Unparsed or ambiguous logic
stays ``UNRESOLVED`` — it is never silently treated as satisfied (design
§6.2: "every mandatory conjunction must be addressed; allowed alternatives
require their selection conditions... Unparsed or ambiguous logic remains
unresolved").

Producing the per-atom SUPPORTED/CONTRADICTED/UNRESOLVED classification from
free text (the actual field-level obligation-vs-implementation comparison,
design §6.2's "compare actor, action, object...") requires either the
obligation-atom extraction this task's P3 does not implement, or bounded LLM
calls per design §6.2/§6.3 ("Use bounded LLM calls only for evidence-backed
proposals and semantic comparisons... Preserve model/prompt/rule versions,
input evidence hashes"). Neither is attempted in this session; this module
is the deterministic logic those future classifications feed into.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Status = Literal["SUPPORTED", "CONTRADICTED", "UNRESOLVED"]
EXPRESSION_KINDS = ("ATOM", "ALL_OF", "ANY_OF", "AT_LEAST_N")


@dataclass
class ExpressionNode:
    kind: str  # one of EXPRESSION_KINDS
    atom_id: str = ""  # required when kind == "ATOM"
    children: list[ExpressionNode] = field(default_factory=list)
    n: int = 0  # required when kind == "AT_LEAST_N"

    def __post_init__(self) -> None:
        if self.kind not in EXPRESSION_KINDS:
            raise ValueError(f"kind must be one of {EXPRESSION_KINDS}, got {self.kind!r}")
        if self.kind == "ATOM" and not self.atom_id:
            raise ValueError("an ATOM node requires atom_id")
        if self.kind == "AT_LEAST_N" and self.n <= 0:
            raise ValueError("an AT_LEAST_N node requires n > 0")


def evaluate_expression(node: ExpressionNode, atom_status: dict[str, Status]) -> tuple[Status, str]:
    """(status, rationale). Never raises for a well-formed node (validated at
    construction); ``UNRESOLVED`` is the honest default whenever the input
    can't settle the question, rather than guessing SUPPORTED."""
    if node.kind == "ATOM":
        status = atom_status.get(node.atom_id)
        if status is None:
            return "UNRESOLVED", f"no status recorded for atom {node.atom_id}"
        return status, f"atom {node.atom_id} is {status}"

    if not node.children:
        return "UNRESOLVED", f"{node.kind} node has no children — cannot evaluate"
    statuses = [evaluate_expression(c, atom_status)[0] for c in node.children]

    if node.kind == "ALL_OF":
        if any(s == "CONTRADICTED" for s in statuses):
            return "CONTRADICTED", "at least one mandatory conjunct is contradicted"
        if all(s == "SUPPORTED" for s in statuses):
            return "SUPPORTED", "every mandatory conjunct is supported"
        return "UNRESOLVED", "at least one mandatory conjunct is unresolved"

    if node.kind == "ANY_OF":
        if any(s == "SUPPORTED" for s in statuses):
            return "SUPPORTED", "at least one alternative branch is supported"
        if all(s == "CONTRADICTED" for s in statuses):
            return "CONTRADICTED", "every alternative branch is contradicted"
        return "UNRESOLVED", "no branch is supported yet, and not every branch is contradicted"

    # AT_LEAST_N
    n_supported = sum(1 for s in statuses if s == "SUPPORTED")
    n_contradicted = sum(1 for s in statuses if s == "CONTRADICTED")
    if n_supported >= node.n:
        return "SUPPORTED", f"{n_supported} of {len(statuses)} branches supported (need {node.n})"
    remaining_viable = len(statuses) - n_contradicted
    if remaining_viable < node.n:
        return (
            "CONTRADICTED",
            f"only {remaining_viable} branches remain viable, need {node.n}",
        )
    return (
        "UNRESOLVED",
        f"{n_supported} of {len(statuses)} branches supported so far (need {node.n})",
    )
