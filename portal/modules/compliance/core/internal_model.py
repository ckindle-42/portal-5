"""Content-derived model of internal controls and implementation assertions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from portal.modules.compliance.core.obligations import decompose


@dataclass
class InternalAssertion:
    assertion_id: str
    relation_type: str
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
    anchor_id: str = ""
    source_text: str = ""
    binding_effect: str = "internally_mandatory"


def classify_document(text: str) -> str:
    header = text[:5000].lower()
    for cue, kind in (
        ("work instruction", "work_instruction"),
        ("procedure", "procedure"),
        ("process", "process"),
        ("policy", "policy"),
        ("standard", "standard"),
        ("evidence specification", "evidence_specification"),
    ):
        if cue in header:
            return kind
    if re.search(r"\b(form|attestation|completed by|record of)\b", header):
        return (
            "evidence_artifact"
            if re.search(r"\b(completed on|signed on|signature date|date completed)\b", header)
            else "evidence_specification"
        )
    return "unknown"


def extract_assertions(revision_id: str, text: str, *, anchor_id: str) -> list[InternalAssertion]:
    out = []
    for index, sentence in enumerate(re.split(r"(?<=[.!?])\s+|\n+", text)):
        sentence = " ".join(sentence.split()).strip()
        modal = re.search(r"\b(shall|must|required to)\b", sentence, re.I)
        operational = re.search(
            r"\b(maintains?|identif(?:y|ies)|reviews?|documents?|creates?|implements?|"
            r"evaluates?|approves?|performs?|tracks?|retains?|protects?|restricts?|"
            r"monitors?|tests?|updates?|validates?|installs?|mitigates?)\b",
            sentence,
            re.I,
        )
        if not modal and not operational:
            continue
        # Appendix traceability rows quote governing language; they are citations,
        # not evidence that the quoted control is implemented (A13).
        quote_only = bool(
            modal and re.search(r"\bCIP-\d{3}(?:-\d[^ ]*)?\b.{0,80}\bR\d+", sentence, re.I)
        )
        source = sentence
        if not modal and operational:
            # A controlled procedure's active operational prose is mandatory even
            # when authors use the indicative mood. Preserve its exact text while
            # giving the symmetric decomposer an explicit binding modality.
            source = sentence[: operational.start()] + "must " + sentence[operational.start() :]
        atoms = decompose(f"internal:{revision_id}:{index}", source, anchor_ids=[anchor_id])
        for atom in atoms:
            out.append(
                InternalAssertion(
                    assertion_id="ia-"
                    + hashlib.sha256(f"{revision_id}:{index}".encode()).hexdigest()[:16],
                    relation_type="REFERENCES" if quote_only else "IMPLEMENTS",
                    actor=atom.actor,
                    modality=atom.modality,
                    action=atom.action,
                    object=atom.object,
                    population=atom.population,
                    trigger=atom.trigger,
                    deadline_cadence=atom.deadline_cadence,
                    conditions=atom.conditions,
                    exceptions=atom.exceptions,
                    evidence_expectation=atom.evidence_expectation,
                    anchor_id=anchor_id,
                    source_text=sentence,
                )
            )
    return out
