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


# ── reference closure (task §1.4) ──────────────────────────────────────────
# Two-pronged, per GraphCompliance: a regex arm for explicit references and a
# (deferred) small-model arm for implicit relative ones. Removing reference
# traversal cost the prior art -9.6pp F1, so every explicit reference must
# become a traversable edge with a resolved endpoint, not a retrieval hop.

_REF_PATTERNS: tuple[tuple[str, str], ...] = (
    ("standard_version", r"CIP[-‐‑]\d{3}-[0-9]+(?:\.[0-9a-z]+)?"),
    ("standard", r"CIP[-‐‑]\d{3}(?!-)"),
    ("requirement", r"Requirement[s]?\s+R\d+"),
    ("attachment_section", r"Attachment\s+\d+,?\s+Section\s+\d+"),
    ("part", r"Part[s]?\s+\d+(?:\.\d+)*"),
    ("section", r"(?<!Attachment )\bSection\s+\d+"),
    ("table", r"Table\s+[RN]?\d+"),
)
_REF_RE = re.compile("|".join(f"(?P<{k}>{v})" for k, v in _REF_PATTERNS), re.I)
_RELATIVE_RE = re.compile(
    r"\b(its parts|the preceding (?:Part|Section|Requirement)|"
    r"the following|this (?:Part|Section|standard)|"
    r"as identified (?:above|below)|described (?:above|below))\b",
    re.I,
)


def _std_effective_at(std_stem: str, valid_from: str | None, reg: Register) -> str | None:
    """Resolve a bare ``CIP-004`` to the version whose validity interval covers
    this node's ``valid_from`` (the reference is read as of when the referrer
    itself is enforceable)."""
    cands = sorted({n.standard for n in reg.nodes if n.standard.startswith(std_stem + "-")})
    if not cands:
        return None
    if valid_from:
        for full in cands:
            sample = next((n for n in reg.nodes if n.standard == full), None)
            live = (
                sample
                and sample.valid_from
                and sample.valid_from <= valid_from
                and not (sample.valid_to and sample.valid_to <= valid_from)
            )
            if live:
                return full
    return cands[-1]


def resolve_references(node: RegisterNode, reg: Register, ids: set[str]) -> list[dict[str, Any]]:
    """Explicit references in ``node``'s text, each resolved to a register node
    id (or a standard id for cross-standard pointers) with the surface text and
    char span. Unresolvable relative references are emitted with
    ``resolution='unresolved_relative'`` so the deferred small-model arm has a
    worklist rather than a silent hole."""
    text = node.verbatim_text
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for m in _REF_RE.finditer(text):
        kind = m.lastgroup
        surface = m.group(0)
        dst, res = _resolve_one(kind, surface, node, reg, ids)
        if dst == node.id or (kind, dst, res) in seen:
            continue
        seen.add((kind, dst, res))
        resolution = (res if (dst in ids or "-" in dst) else "dangling") if dst else res
        edges.append(
            {
                "src": node.id,
                "dst": dst,
                "rel": "REFERS_TO",
                "surface_text": surface,
                "char_start": m.start(),
                "char_end": m.end(),
                "resolution": resolution,
            }
        )
    for m in _RELATIVE_RE.finditer(text):
        edges.append(
            {
                "src": node.id,
                "dst": "",
                "rel": "REFERS_TO",
                "surface_text": m.group(0),
                "char_start": m.start(),
                "char_end": m.end(),
                "resolution": "unresolved_relative",
            }
        )
    return edges


def _first_in(ids: set[str], *cands: str) -> str:
    return next((c for c in cands if c in ids), "")


def _resolve_standard(kind: str, s: str, node: RegisterNode, reg: Register) -> tuple[str, str]:
    if kind == "standard_version":
        return s.upper(), "exact"
    full = _std_effective_at(s.upper(), node.valid_from, reg)
    return (full or s.upper()), ("standard_version" if full else "standard_stem")


def _resolve_one(
    kind: str, surface: str, node: RegisterNode, reg: Register, ids: set[str]
) -> tuple[str, str]:
    s = re.sub(r"[‐‑]", "-", surface).strip()
    std = node.standard
    if kind in ("standard_version", "standard"):
        return _resolve_standard(kind, s, node, reg)
    if kind == "requirement":
        rn = re.search(r"R\d+", s, re.I).group(0).upper()
        hit = _first_in(ids, f"{std} {rn}")
        # Most standards have no requirement-level node — the reference still
        # resolves to a real scope: the set of that requirement's Parts.
        if hit:
            return hit, "exact"
        if any(i.startswith(f"{std} {rn} Part ") for i in ids):
            return f"{std} {rn}", "requirement_group"
        return "", "unresolved_requirement"
    if kind == "attachment_section":
        mm = re.search(r"Attachment\s+(\d+),?\s+Section\s+(\d+)", s, re.I)
        a, sec = mm.group(1), mm.group(2)
        hit = _first_in(
            ids,
            f"{std} Attachment {a} Section {sec}",
            f"{std} Attachment {a} Part {sec}",
        )
        return (hit, "exact") if hit else (f"{std} Attachment {a} Section {sec}", "dangling")
    if kind == "part":
        pn = re.search(r"\d+(?:\.\d+)*", s).group(0)
        top = pn.split(".")[0]
        same_base = node.id.rsplit(" Part ", 1)[0] if " Part " in node.id else ""
        hit = _first_in(
            ids,
            f"{same_base} Part {pn}" if same_base else "",
            f"{std} R{top} Part {pn}",
            f"{std} Attachment 1 Part {pn}",
        )
        if hit:
            return hit, "exact"
        if any(i.startswith(f"{std} R{top} Part {pn}") for i in ids):
            return f"{std} R{top} Part {pn}", "part_group"
        return "", "unresolved_part"
    if kind == "section":
        # Bare "Section N" is only reliably resolvable inside an Attachment,
        # where the sibling section header is "<attach> Part N". A "Section N"
        # in a standard's body points at unextracted front-matter — leave it
        # for the relative-reference arm rather than mis-resolve it.
        sn = re.search(r"\d+", s).group(0)
        if " Part " in node.id and "Attachment" in node.id:
            base = node.id.rsplit(" Part ", 1)[0]
            hit = _first_in(ids, f"{base} Part {sn}", f"{base} Section {sn}")
            if hit:
                return hit, "exact"
        return "", "unresolved_section"
    if kind == "table":
        return "", "table_not_a_node"
    return "", "unknown"


def build_policy_graph(register: Register | None = None) -> PolicyGraph:
    import hashlib

    reg = register or Register.load()
    by_id = {n.id: n for n in reg.nodes}
    graph = PolicyGraph(
        built_from_register_sha=hashlib.sha256(
            json.dumps(reg.to_json(), sort_keys=True, default=str).encode()
        ).hexdigest()[:16],
    )
    ids = set(by_id)
    counts: dict[str, int] = {"premise": 0, "meta_cu": 0, "actor_cu": 0}
    by_rule: dict[str, int] = {}
    ref_res: dict[str, int] = {}
    for n in reg.nodes:
        parent = _parent_of(n, by_id)
        ntype, rule, evidence = classify_node(n, parent)
        counts[ntype] += 1
        by_rule[rule] = by_rule.get(rule, 0) + 1
        for e in resolve_references(n, reg, ids):
            graph.edges.append(e)
            ref_res[e["resolution"]] = ref_res.get(e["resolution"], 0) + 1
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
    refers_to = [e for e in graph.edges if e["rel"] == "REFERS_TO"]
    graph.typing_report = {
        "n_nodes": len(graph.nodes),
        "by_type": counts,
        "by_rule": dict(sorted(by_rule.items(), key=lambda kv: -kv[1])),
        "refers_to_edges": len(refers_to),
        "refers_to_src_nodes": len({e["src"] for e in refers_to}),
        "refers_to_by_resolution": dict(sorted(ref_res.items(), key=lambda kv: -kv[1])),
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
