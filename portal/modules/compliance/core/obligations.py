"""Symmetric, source-anchored obligation decomposition."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

_MODAL = re.compile(r"\b(shall not|must not|shall|must|may not|required to)\b", re.I)
_CADENCE = re.compile(
    r"\b(?:within|at least once every|no less than)\s+\d+\s+(?:calendar\s+|business\s+)?(?:hours?|days?|months?|years?)\b",
    re.I,
)


@dataclass
class ObligationAtom:
    atom_id: str
    node_id: str
    actor: str = ""
    modality: str = ""
    action: str = ""
    object: str = ""
    population: str = ""
    trigger: str = ""
    deadline_cadence: str = ""
    conditions: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    evidence_expectation: str = ""
    source_anchor_ids: list[str] = field(default_factory=list)
    interpretation_status: str = "accepted"

    def to_record(self) -> dict[str, Any]:
        return self.__dict__.copy()


def decompose(
    node_id: str, text: str, *, lead_in: str = "", anchor_ids: list[str] | None = None
) -> list[ObligationAtom]:
    """Decompose modal clauses, inheriting a parent lead-in for fragments."""
    source = " ".join(text.split())
    modal = _MODAL.search(source)
    if not modal and lead_in:
        inherited = _MODAL.search(lead_in)
        if inherited:
            source = f"{lead_in.rstrip(':;,.')} {source}"
            modal = _MODAL.search(source)
    if not modal:
        # A Part under a modal requirement is normally a fragment. Preserve it
        # as an atom with proposed interpretation instead of inventing force.
        atom_id = f"atom-{hashlib.sha256((node_id + source).encode()).hexdigest()[:16]}"
        words = source.split()
        return [
            ObligationAtom(
                atom_id,
                node_id,
                action=" ".join(words[: min(4, len(words))]),
                object=" ".join(words[min(4, len(words)) :]),
                source_anchor_ids=anchor_ids or [],
                interpretation_status="proposed",
            )
        ]
    actor = source[: modal.start()].strip(" ,:;")
    remainder = source[modal.end() :].strip(" ,:;")
    condition: list[str] = []
    exception: list[str] = []
    for cue, target in (
        (" if ", condition),
        (" when ", condition),
        (" unless ", exception),
        (" except ", exception),
    ):
        match = re.search(rf"\b{re.escape(cue.strip())}\b", remainder, re.I)
        if match:
            target.append(remainder[match.start() :].strip())
    action_words = remainder.split()
    action = " ".join(action_words[: min(4, len(action_words))])
    obj = " ".join(action_words[min(4, len(action_words)) :])
    cadence_match = _CADENCE.search(source)
    cadence = cadence_match.group(0) if cadence_match else ""
    atom_id = f"atom-{hashlib.sha256((node_id + source).encode()).hexdigest()[:16]}"
    return [
        ObligationAtom(
            atom_id,
            node_id,
            actor,
            modal.group(0).upper(),
            action,
            obj,
            deadline_cadence=cadence,
            conditions=condition,
            exceptions=exception,
            evidence_expectation="documented evidence"
            if re.search(r"\b(document|record|retain|evidence)\b", source, re.I)
            else "",
            source_anchor_ids=anchor_ids or [],
        )
    ]


def expression_for(atoms: list[ObligationAtom], text: str) -> dict[str, Any]:
    kind = (
        "ANY_OF"
        if re.search(r"\b(or|either)\b", text, re.I) and not re.search(r"\band\b", text, re.I)
        else "ALL_OF"
    )
    return {"kind": kind, "children": [{"kind": "ATOM", "atom_id": atom.atom_id} for atom in atoms]}
