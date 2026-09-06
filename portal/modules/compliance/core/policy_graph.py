"""The typed policy graph (TASK_COMPLIANCE_REASONING_V6 P2).

`cip_register.py` / `cip_extract.py` are the immutable extraction template and
are **not** touched. This module *augments* the persisted register in place:
every register node is classified into one of three types, following the
GraphCompliance CU taxonomy (arXiv:2510.26309 §3):

  - ``premise``  — non-deontic definitional / interpretive material: defined
    terms, role definitions, scope statements, evidence guidance, enumerated
    policy topics. Never itself judged; the system needs it to *read* the rules.
  - ``meta_cu``  — an applicability predicate: temporal / territorial scope,
    role qualification, covered-system scope. Evaluated first, gates whether an
    actor-CU is considered; never reported as a standalone finding.
  - ``actor_cu`` — an obligation, prohibition or permission addressed to a
    role-bearing actor. These, and only these, receive determinations.

Classification is deterministic and every node carries the rule that typed it
plus a verbatim evidence span — no tuned constants, no similarity scores. The
per-field CU decomposition (``{subject, constraint, condition, context}`` with
per-field char spans) and the fine-grained ``REFERS_TO`` reference closure are
layered on top of this typing in the same module (see ``decompose_actor_cu``
and ``resolve_references``).

Build: ``python -m portal.modules.compliance.core.policy_graph build``
Output: ``portal/modules/compliance/data/nerc_cip_policy_graph.json`` (derived,
rebuildable, idempotent).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from portal.modules.compliance.core.cip_register import REGISTER_PATH, Register, RegisterNode

_DATA = Path(__file__).resolve().parent.parent / "data"
POLICY_GRAPH_PATH = _DATA / "nerc_cip_policy_graph.json"

NodeType = Literal["premise", "meta_cu", "actor_cu"]

# ── lexical signals (documented, not tuned) ─────────────────────────────────

# A deontic operator addressed to an actor. "may" alone is a permission and is
# handled by the permission-structure pass, not here.
_MODAL = re.compile(r"\b(shall|must|may not|is required to|are required to|required to)\b", re.I)

# A NERC requirement-parts table cell / attachment element is written as a bare
# imperative or gerund clause governed by its requirement's "shall implement ...
# that collectively includes each of the applicable requirement parts" (or
# "... which shall include:") stem. Both verb forms appear in the corpus.
_IMPERATIVE = re.compile(
    r"^\s*(?:Section \d+\.[^:]*:\s*)?(?:Where technically feasible[,;] )?"
    r"(?:At least once (?:every|each) [^,]+, )?"
    r"(Identif\w+|Review|Have|Document\w*|Test\w*|Monitor\w*|Conduct|Updat\w+|"
    r"Issue|Provide|Implement\w*|Perform\w*|Authenticat\w+|Determin\w+|Mitigat\w+|"
    r"Includ\w+|Establish\w*|Maintain\w*|Develop\w*|Retain|Verif\w+|Protect\w*|"
    r"Deploy\w*|Disabl\w+|Enforc\w+|Restrict\w*|Detect\w*|Generat\w+|Manag\w+|"
    r"Evaluat\w+|Appl\w+|Requir\w+|Permit\w*|Use|Select\w*|Grant\w*|Revok\w+|"
    r"Assign\w*|Ensur\w+|Control\w*|Chang\w+|Limit\w*|Authoriz\w+|Remov\w+|"
    r"Initiat\w+|Reinforc\w+|Configur\w+|Coordinat\w+|Notif\w+|Report\w*|"
    r"Respon\w+|Contain\w*|Eradicat\w+|Recover\w*|Preserv\w+|Correct\w*|Take|"
    r"Stor\w+|Record\w*|Classif\w+|Alert\w*|Log|Patch\w*|Scan\w*|Method|"
    r"One or (?:more|a combination)|For (?:Transient|Removable|electronic|each)|"
    r"Prior to|Where )",
    re.I,
)

# Parent-requirement text that introduces an enumerated list of MANDATORY
# elements: every child Part is then an actor-CU regardless of its verb form.
_ENUMERATING_LEAD = re.compile(
    r"(shall (?:implement|have|develop|maintain|include)[^.]*?|"
    r"that (?:collectively )?include[s]?[^.]*?|which shall include|"
    r"as part of[^.]*?)\s*:?\s*$",
    re.I,
)

# Applicability / scope predicate language.
_META = re.compile(
    r"\b(applies to|is applicable to|For each asset containing|"
    r"with at least one asset identified|used to perform the functional "
    r"obligations|not included in (Section|High Impact)|"
    r"identified .* in Requirement R1|for its high impact and medium impact|"
    r"for high and medium impact)\b",
    re.I,
)

# Enumerated policy-topic label: a short noun phrase, optionally trailing
# "(CIP-0xx)" and "; and", with no verb — CIP-003 R1 Part 1.1.x / 1.2.x.
_TOPIC_LABEL = re.compile(
    r"^[A-Z][A-Za-z0-9 ,/&()‐‑-]{0,90}?(?:\s*\(CIP[‐‑-]?\s?\d{3}\))?"
    r"(?:;?\s*and)?\.?$"
)

_DEF_LEAD = re.compile(
    r"^(Each |Low Impact Rating|Medium Impact Rating|High Impact Rating|"
    r"An example of evidence|Examples? of)",
    re.I,
)


@dataclass
class PolicyNode:
    id: str
    node_type: NodeType
    typing_rule: str
    typing_evidence: str  # verbatim fragment that decided the type
    standard: str
    requirement: str
    part: str
    verbatim_text: str
    applicable_systems: str
    gated_by: list[str] = field(default_factory=list)  # meta_cu ids that gate this actor_cu
    depends_on: list[str] = field(default_factory=list)  # premise ids this node reads


@dataclass
class PolicyGraph:
    nodes: list[PolicyNode] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    typing_report: dict[str, Any] = field(default_factory=dict)
    built_from_register_sha: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "built_from_register_sha": self.built_from_register_sha,
            "typing_report": self.typing_report,
            "nodes": [asdict(n) for n in self.nodes],
            "edges": self.edges,
        }

    @classmethod
    def load(cls, path: Path | str = POLICY_GRAPH_PATH) -> PolicyGraph:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            nodes=[PolicyNode(**n) for n in d["nodes"]],
            edges=d.get("edges", []),
            typing_report=d.get("typing_report", {}),
            built_from_register_sha=d.get("built_from_register_sha", ""),
        )


def _has_modal(text: str) -> bool:
    return bool(_MODAL.search(text))


def classify_node(node: RegisterNode, parent: RegisterNode | None) -> tuple[NodeType, str, str]:
    """Return ``(node_type, rule, evidence)``. Deterministic. ``parent`` is the
    requirement-level node when one exists in the register (only ~22 do)."""
    text = node.verbatim_text.strip()
    sid = node.standard

    # 1. CIP-002 Attachment 1 — the impact-rating criteria. Pure definitions of
    #    what makes a system high / medium / low impact.
    if sid.startswith("CIP-002") and "Attachment 1" in node.id:
        return "premise", "impact_rating_criterion", text[:120]

    # 2. Definitional section header with no deontic force (Attachment section
    #    leads, evidence examples).
    m = _DEF_LEAD.match(text)
    if m and not _has_modal(text):
        return "premise", "definitional_or_evidence_lead", m.group(0)

    parent_text = parent.verbatim_text if parent is not None else ""

    # 3. CIP-003 R1 policy-topic label: the parent says a policy must "address
    #    the following topics"; the topic itself is subject matter, not a duty.
    if (
        node.part
        and re.search(r"address(?:es)? the following topics?", parent_text, re.I)
        and _TOPIC_LABEL.match(text)
    ):
        return "premise", "enumerated_policy_topic", text[:120]

    # 4. Applicability predicate — a meta-CU. Only when the node is *primarily*
    #    a scope statement: no deontic operator of its own, and the scope clause
    #    leads the text. A "... that identified X shall ..." Part carries both a
    #    qualifier and a duty — that is an actor-CU with an attached
    #    applicability condition (handled in decomposition), not a meta-CU.
    mm = _META.search(text)
    if mm and not _has_modal(text) and mm.start() < 45:
        return "meta_cu", "applicability_predicate", mm.group(0)

    # 5. Explicit own modal → an obligation / prohibition addressed to the actor.
    if _has_modal(text):
        return "actor_cu", "explicit_modal", _MODAL.search(text).group(0)

    # 6. Child Part under a parent that introduces an enumerated list of
    #    mandatory elements ("... a plan which shall include:", "... electronic
    #    access controls to:") — required regardless of verb form.
    if node.part and _ENUMERATING_LEAD.search(parent_text):
        return "actor_cu", "mandatory_enumerated_element", (parent_text[-70:].strip())

    # 7. Imperative / gerund clause whose parent requirement carries a modal.
    if parent is not None and _has_modal(parent_text) and _IMPERATIVE.match(text):
        return (
            "actor_cu",
            "imperative_fragment_under_modal_parent",
            _IMPERATIVE.match(text).group(1),
        )

    # 8. A numbered requirement Part in a requirement-parts table is normative by
    #    NERC's own structure: the requirement's "shall implement ... one or
    #    more documented process(es) that collectively include each of the
    #    applicable requirement parts" stem gives every cell its force, even
    #    when the register holds no separate requirement-level node. The premise
    #    rules above have already carved out the non-normative Parts (impact
    #    criteria, policy-topic labels, evidence examples, section headers).
    if node.part and (node.table_name or re.match(r"R\d+", node.requirement)):
        lead = _IMPERATIVE.match(text)
        return (
            "actor_cu",
            "requirement_part_normative_by_structure",
            (lead.group(1) if lead else text[:80]),
        )

    # 9. Everything else is non-deontic material the reader needs but never
    #    judges.
    return "premise", "non_deontic_fragment", text[:120]


def _parent_of(node: RegisterNode, by_id: dict[str, RegisterNode]) -> RegisterNode | None:
    """The nearest enclosing node for a Part, when the register has one.

    For ``X Part 4.6`` the parent is ``X Part 4`` (the section header); for a
    top-level ``X Part 4`` / ``X R2 Part 2.2`` it is ``X R2`` when that node
    exists (only ~22 requirement-level nodes are in the register)."""
    if not node.part:
        return None
    base = node.id.rsplit(" Part ", 1)[0]  # "CIP-003-8 R1" | "CIP-003-9 Attachment 1"
    segs = node.part.split(".")
    for k in range(len(segs) - 1, 0, -1):
        cand = by_id.get(f"{base} Part {'.'.join(segs[:k])}")
        if cand is not None:
            return cand
    return by_id.get(base) or by_id.get(f"{node.standard} {node.requirement}")


def build_policy_graph(register: Register | None = None) -> PolicyGraph:
    import hashlib

    reg = register or Register.load()
    by_id = {n.id: n for n in reg.nodes}
    graph = PolicyGraph(
        built_from_register_sha=hashlib.sha256(
            json.dumps(reg.to_json(), sort_keys=True, default=str).encode()
        ).hexdigest()[:16],
    )
    counts: dict[str, int] = {"premise": 0, "meta_cu": 0, "actor_cu": 0}
    by_rule: dict[str, int] = {}
    for n in reg.nodes:
        parent = _parent_of(n, by_id)
        ntype, rule, evidence = classify_node(n, parent)
        counts[ntype] += 1
        by_rule[rule] = by_rule.get(rule, 0) + 1
        graph.nodes.append(
            PolicyNode(
                id=n.id,
                node_type=ntype,
                typing_rule=rule,
                typing_evidence=evidence,
                standard=n.standard,
                requirement=n.requirement,
                part=n.part,
                verbatim_text=n.verbatim_text,
                applicable_systems=n.applicable_systems,
            )
        )
    graph.typing_report = {
        "n_nodes": len(graph.nodes),
        "by_type": counts,
        "by_rule": dict(sorted(by_rule.items(), key=lambda kv: -kv[1])),
    }
    return graph


def write_policy_graph(graph: PolicyGraph, path: Path | str = POLICY_GRAPH_PATH) -> None:
    Path(path).write_text(
        json.dumps(graph.to_json(), indent=1, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "build":
        g = build_policy_graph()
        write_policy_graph(g)
        r = g.typing_report
        print(f"policy graph: {r['n_nodes']} nodes  {r['by_type']}")
        for rule, k in r["by_rule"].items():
            print(f"  {rule:40} {k:3d}")
    else:
        print(f"register: {REGISTER_PATH}\npolicy graph: {POLICY_GRAPH_PATH}")
