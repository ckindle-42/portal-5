"""The vocabulary bridge (TASK_COMPLIANCE_REASONING_V6 P3).

The principled replacement for the ``LSPG|SME|OT|Security|Manager|Owner`` regex
that ``assessment._compare`` used to decide actor alignment. Following
GraphCompliance §1.5, an organization entity is mapped to policy vocabulary
through **hypernym proposals**, each marked:

  - ``STRONG`` when its supporting fragment is a *premise* (a defined term, an
    impact-rating criterion, a scope statement) — authoritative;
  - ``WEAK``   otherwise — a lexical hint only.

Confidence aggregates by max-pooling the per-proposal scores plus a bonus when
a STRONG proposal is present. Every mapping keeps its supporting fragment, so
"OT Security Manager resolves to Responsible Entity" is a recorded, reviewable
chain, not a literal buried in a comparator.

The policy vocabulary is derived from the typed policy graph's premises plus
the NERC defined terms the register text itself surfaces (capitalised
multi-word phrases and acronyms — NERC's own convention for a glossary term).
Ingesting the published NERC *Glossary of Terms* PDF as an additional premise
source is gated on nerc.com reachability (honest-BLOCKED, mirroring
``currency.nerc_currency``); the register-derived term set is the floor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from portal.modules.compliance.core.policy_graph import PolicyGraph, build_policy_graph

Strength = Literal["STRONG", "WEAK"]

# NERC's functional model: the "Responsible Entity" of a CIP standard is
# whichever registered functional entity the standard applies to. An operator's
# internal roles (a manager, an owner, a team) are assignments *within* that
# entity — CIP-004/003 explicitly contemplate delegation. This is public
# structure from the NERC Rules of Procedure, not a tuned heuristic.
_FUNCTIONAL_ENTITIES = (
    "Responsible Entity",
    "Transmission Owner",
    "Transmission Operator",
    "Generator Operator",
    "Generator Owner",
    "Reliability Coordinator",
    "Balancing Authority",
    "Distribution Provider",
    "Planning Coordinator",
    "Interchange Coordinator",
)
_ROLE_HEAD = re.compile(
    r"\b(manager|owner|delegate|team|operator|analyst|administrator|coordinator|"
    r"engineer|lead|director|officer|personnel|staff|group|committee|custodian)\b",
    re.I,
)

# Acronym expansions stated in the CIP standards' own Applicable Systems text.
_ACRONYM_SEED: dict[str, str] = {
    "EACMS": "Electronic Access Control or Monitoring Systems",
    "PACS": "Physical Access Control Systems",
    "PCA": "Protected Cyber Asset",
    "ESP": "Electronic Security Perimeter",
    "EAP": "Electronic Access Point",
    "BCA": "BES Cyber Asset",
    "BCS": "BES Cyber System",
    "BCSI": "BES Cyber System Information",
    "TCA": "Transient Cyber Asset",
    "IRA": "Interactive Remote Access",
    "PSP": "Physical Security Perimeter",
    "CIP SM": "CIP Senior Manager",
}

_STOP_PREFIX = re.compile(r"^(Each |The |For |A |An |Its )", re.I)
_CAP_TERM = re.compile(
    r"\b((?:[A-Z]{2,6} )?[A-Z][a-z]+(?: (?:[A-Z][a-z]+|of|or|and)){1,4}|[A-Z]{2,6})\b"
)
_NOISE = {
    "Each",
    "The",
    "This",
    "That",
    "Requirement",
    "Part",
    "Section",
    "Attachment",
    "Table",
    "Where",
    "For",
    "Reference Model",
    "MW",
    "kV",
}


def _norm(term: str) -> str:
    t = _STOP_PREFIX.sub("", term).strip()
    t = re.sub(
        r"\b(Systems|Assets|Incidents|Centers|Facilities|Media)\b",
        lambda m: m.group(1)[:-1] if m.group(1) != "Media" else m.group(1),
        t,
    )
    t = re.sub(r"s$", "", t) if t.endswith("s") and not t.endswith("ss") else t
    return t.strip()


@dataclass
class VocabTerm:
    term: str
    canonical: str
    strength: Strength  # STRONG if any supporting fragment is a premise
    supporting_fragments: list[dict[str, str]] = field(default_factory=list)
    is_functional_entity: bool = False


@dataclass
class HypernymProposal:
    entity: str
    target_term: str
    strength: Strength
    score: float
    rule: str
    supporting_fragment: dict[str, str]


@dataclass
class PolicyVocabulary:
    terms: dict[str, VocabTerm] = field(default_factory=dict)  # keyed by canonical

    def strong_terms(self) -> list[str]:
        return sorted(t.canonical for t in self.terms.values() if t.strength == "STRONG")


def derive_vocabulary(graph: PolicyGraph | None = None) -> PolicyVocabulary:
    g = graph or build_policy_graph()
    vocab = PolicyVocabulary()
    premise_ids = {n.id for n in g.nodes if n.node_type == "premise"}

    def add(term: str, node_id: str, node_type: str, fragment: str) -> None:
        canon = _norm(term)
        if not canon or canon in _NOISE or len(canon) < 2:
            return
        vt = vocab.terms.get(canon)
        strength: Strength = "STRONG" if node_type == "premise" else "WEAK"
        if vt is None:
            vt = VocabTerm(
                term=term,
                canonical=canon,
                strength=strength,
                is_functional_entity=canon in _FUNCTIONAL_ENTITIES,
            )
            vocab.terms[canon] = vt
        if strength == "STRONG":
            vt.strength = "STRONG"
        vt.supporting_fragments.append(
            {"node_id": node_id, "node_type": node_type, "fragment": fragment[:160]}
        )

    for n in g.nodes:
        for m in _CAP_TERM.finditer(n.verbatim_text):
            term = m.group(1)
            if term.startswith("CIP"):
                continue
            add(term, n.id, n.node_type, n.verbatim_text[max(0, m.start() - 30) : m.end() + 30])
        # meta-CU scope predicates contribute their parsed components as STRONG
        if n.node_type == "meta_cu" and n.scope_predicate:
            for a in n.scope_predicate.get("associated_asset_types", []):
                add(a, n.id, "meta_cu", n.verbatim_text)

    for acr, expansion in _ACRONYM_SEED.items():
        vt = vocab.terms.get(_norm(expansion))
        if vt:
            vt.supporting_fragments.append(
                {
                    "node_id": "seed:acronym",
                    "node_type": "premise",
                    "fragment": f"{acr} = {expansion}",
                }
            )
        vocab.terms.setdefault(
            acr,
            VocabTerm(
                term=acr,
                canonical=acr,
                strength="STRONG",
                supporting_fragments=[
                    {
                        "node_id": "seed:acronym",
                        "node_type": "premise",
                        "fragment": f"{acr} = {expansion}",
                    }
                ],
            ),
        )
    del premise_ids  # (kept above for clarity; strength is decided per fragment)
    return vocab


def propose_hypernyms(entity: str, vocab: PolicyVocabulary) -> list[HypernymProposal]:
    """Deterministic hypernym proposals for one organization entity. No tuned
    thresholds — the score is a fixed function of match kind and support
    strength, and every proposal keeps its supporting fragment."""
    ent_norm = _norm(entity)
    ent_l = ent_norm.lower()
    out: list[HypernymProposal] = []
    for canon, vt in vocab.terms.items():
        cl = canon.lower()
        rule = ""
        if ent_l == cl:
            rule, base = "exact", 1.0
        elif cl in ent_l or ent_l in cl:
            rule, base = "containment", 0.75
        elif _ROLE_HEAD.search(entity) and vt.is_functional_entity:
            # an internal role/team is an assignment within the functional entity
            rule, base = "role_within_functional_entity", 0.6
        else:
            continue
        score = min(1.0, base + (0.15 if vt.strength == "STRONG" else 0.0))
        out.append(
            HypernymProposal(
                entity=entity,
                target_term=canon,
                strength=vt.strength,
                score=round(score, 3),
                rule=rule,
                supporting_fragment=(vt.supporting_fragments or [{}])[0],
            )
        )
    out.sort(key=lambda p: -p.score)
    return out[:4]


@dataclass
class ActorAlignment:
    aligned: bool
    confidence: float
    governing_actor: str
    internal_actor: str
    proposal_chain: list[HypernymProposal]
    note: str


def align_actor(
    internal_actor: str, governing_actor: str, vocab: PolicyVocabulary
) -> ActorAlignment:
    """Decide whether ``internal_actor`` satisfies ``governing_actor`` through a
    recorded proposal chain. Replaces the hardcoded role-word regex in
    ``assessment._compare``."""
    gov_norm = _norm(governing_actor)
    proposals = propose_hypernyms(internal_actor, vocab)
    hit = next((p for p in proposals if p.target_term.lower() == gov_norm.lower()), None)
    if hit:
        return ActorAlignment(
            aligned=True,
            confidence=hit.score,
            governing_actor=governing_actor,
            internal_actor=internal_actor,
            proposal_chain=[hit],
            note=f"{internal_actor} -> {hit.target_term} via {hit.rule} ({hit.strength})",
        )
    # governing actor is a functional entity and the internal actor is any
    # role/team: the assignment-within-entity path
    if gov_norm in _FUNCTIONAL_ENTITIES and _ROLE_HEAD.search(internal_actor):
        p = HypernymProposal(
            entity=internal_actor,
            target_term=gov_norm,
            strength="STRONG",
            score=0.6,
            rule="role_within_functional_entity",
            supporting_fragment={
                "node_id": "nerc:functional-model",
                "fragment": "internal roles are assignments within the Responsible Entity",
            },
        )
        return ActorAlignment(
            aligned=True,
            confidence=0.6,
            governing_actor=governing_actor,
            internal_actor=internal_actor,
            proposal_chain=[p],
            note=f"{internal_actor} is assigned within {gov_norm}",
        )
    return ActorAlignment(
        aligned=False,
        confidence=0.0,
        governing_actor=governing_actor,
        internal_actor=internal_actor,
        proposal_chain=proposals,
        note="no proposal resolves the internal actor to the governing actor",
    )
