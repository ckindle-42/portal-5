"""The council (TASK_COMPLIANCE_REASONING_V6 P5).

V4's mechanics, unchanged: sealed packets, cite-or-drop, quorum computed in
code, dissent recorded as ``S04_INTERPRETATION_DISPUTE``. Two things are new
for V6:

  - judgment is **listwise over the CU plan** — one model call per governing
    anchor, the seat seeing every candidate at once so it can weigh the
    relationships among them, not one call per atom;
  - a **second, separate call performs the exception override** against the
    reference closure whenever the first call judges the CU unmet.

The packet is the structured JSON ``GateResult.to_council_packet()`` produces —
never raw document text (the KG-representation literature finds structured JSON
beats prose for fact-intensive judgment). Inference from silence is forbidden
in the seat contract and tested: an ambiguous or under-evidenced packet returns
``insufficient``, never a guess.

The model call is injected (``seat_fn``); the default talks to Ollama. No seat
ever sees another seat's answer, the prior determination, the approval state or
a gold label.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

SeatFn = Callable[[str, str, str], str]  # (model, system, user) -> raw text

_DETERMINATIONS = ("SUPPORTED", "PARTIAL", "CONTRADICTED", "ABSENT", "INSUFFICIENT")
_UNMET = ("PARTIAL", "CONTRADICTED", "ABSENT")
_FINDING_TYPES = ("", "GAP", "CONTRADICTION", "OUTDATED_LANGUAGE", "WEAK_MAPPING")

_SEAT_SYSTEM = (
    "You are one sealed seat on a compliance review council. You receive a "
    "PRE-ANALYZED problem as JSON: one governing compliance unit already "
    "decomposed into subject/constraint/condition/context, its applicability "
    "state, its reference closure, its exception clauses, and a list of "
    "candidate internal commitments each already checked for actor alignment "
    "and (where a quantity exists) constraint direction.\n"
    "Decide whether the candidates, taken together, satisfy the governing "
    "unit. RULES:\n"
    "- Judge only this governing unit. Do not invent obligations.\n"
    "- A candidate the gate marked MORE_RESTRICTIVE or EQUIVALENT SATISFIES "
    "the constraint — stricter is never a violation.\n"
    "- Do NOT infer from silence. If the packet lacks evidence you need, or "
    "applicability is UNKNOWN/CONFLICTED, return INSUFFICIENT.\n"
    "- ABSENT = the packet is complete and no candidate addresses the unit.\n"
    "- Cite only refs that appear in the packet.\n"
    'Return ONE JSON object: {"determination":'
    '"SUPPORTED|PARTIAL|CONTRADICTED|ABSENT|INSUFFICIENT",'
    '"finding_type":null|"GAP"|"CONTRADICTION"|"OUTDATED_LANGUAGE"|"WEAK_MAPPING",'
    '"cited_refs":["..."],"confidence":0.0-1.0,"rationale":"one sentence"}'
)

_OVERRIDE_SYSTEM = (
    "You are checking one thing only: a compliance unit was judged NOT met. "
    "You are given that unit and the full text of every unit reachable through "
    "its reference edges. Decide whether any of those referenced units is a "
    "valid exception, derogation or 'unless' that OVERRIDES the violation for "
    "this actor.\n"
    "Do not re-judge the original question. Do not infer from silence.\n"
    'Return ONE JSON object: {"overrides": true|false, '
    '"exception_ref": "<ref or null>", "rationale": "one sentence"}'
)


@dataclass
class SeatOpinion:
    seat_id: str
    model: str
    determination: str = "INSUFFICIENT"
    finding_type: str = ""
    cited_refs: list[str] = field(default_factory=list)
    confidence: float = 0.0
    rationale: str = ""
    valid: bool = False
    dropped: str = ""  # "" | reason a cite-or-drop / parse rule dropped this seat

    @property
    def votes(self) -> bool:
        return self.valid and not self.dropped and self.determination != "INSUFFICIENT"


@dataclass
class CouncilResult:
    anchor: str
    determination: str  # a _DETERMINATIONS value, or "ESCALATE"
    finding_type: str
    quorum_required: int
    roster: int
    votes: dict[str, int]
    dissent: list[str]  # seat ids that voted against the decision — S04 material
    opinions: list[SeatOpinion]
    citations: list[str]
    override: dict[str, Any] | None = None
    rationale: str = ""

    @property
    def sme_decision_kind(self) -> str:
        return "S04_INTERPRETATION_DISPUTE" if self.determination == "ESCALATE" else ""


def _packet_allowlist(packet: dict[str, Any]) -> set[str]:
    refs = {packet["governing_unit"]["ref"]}
    refs |= set(packet.get("reference_closure", []))
    for c in packet.get("candidates", []):
        if c.get("commitment_id"):
            refs.add(c["commitment_id"])
    return refs


def _parse_seat(seat_id: str, model: str, raw: str, allowlist: set[str]) -> SeatOpinion:
    op = SeatOpinion(seat_id=seat_id, model=model)
    obj = _json_object(raw)
    if obj is None:
        op.dropped = "no JSON object"
        return op
    det = str(obj.get("determination", "")).upper()
    if det not in _DETERMINATIONS:
        op.dropped = f"invalid determination {det!r}"
        return op
    ft = obj.get("finding_type") or ""
    ft = str(ft).upper() if ft else ""
    if ft not in _FINDING_TYPES:
        ft = ""
    cited = [str(r) for r in (obj.get("cited_refs") or []) if r]
    op.determination = det
    op.finding_type = ft
    op.cited_refs = cited
    try:
        op.confidence = max(0.0, min(1.0, float(obj.get("confidence", 0.0))))
    except (TypeError, ValueError):
        op.confidence = 0.0
    op.rationale = str(obj.get("rationale", ""))[:400]
    op.valid = True
    # cite-or-drop: a determination resting on a ref outside the packet is dropped
    off = [r for r in cited if not _ref_in_allowlist(r, allowlist)]
    if det in ("SUPPORTED", "PARTIAL", "CONTRADICTED") and (not cited or off):
        op.dropped = f"cite-or-drop: {'no citation' if not cited else f'off-packet {off}'}"
    return op


def _ref_in_allowlist(ref: str, allowlist: set[str]) -> bool:
    r = re.sub(r"\s+", " ", ref).strip().lower()
    return any(r == a.lower() or r in a.lower() or a.lower() in r for a in allowlist)


def _json_object(text: str) -> dict[str, Any] | None:
    t = text.strip()
    if t.startswith("```"):
        t = "\n".join(t.splitlines()[1:])
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    try:
        v = json.loads(t)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        s, e = t.find("{"), t.rfind("}")
        if s < 0 or e <= s:
            return None
        try:
            v = json.loads(t[s : e + 1])
            return v if isinstance(v, dict) else None
        except json.JSONDecodeError:
            return None


def _ollama_seat(model: str, system: str, user: str) -> str:
    import urllib.request

    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0, "num_predict": 700},
    }
    req = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310 - fixed localhost
        return (json.load(r).get("message") or {}).get("content", "") or ""


def run_council(
    packet: dict[str, Any],
    seats: list[dict[str, str]],
    *,
    seat_fn: SeatFn | None = None,
    quorum: float = 0.66,
    reference_texts: dict[str, str] | None = None,
) -> CouncilResult:
    """Listwise judgment over one anchor's CU plan, quorum in code, then an
    exception-override second call if the decision is unmet.

    ``seats`` is a list of ``{"id","label","model"}``. ``seat_fn`` is injected
    for tests; the default talks to Ollama. ``reference_texts`` maps a
    reference-closure ref to its verbatim text for the override call."""
    fn = seat_fn or _ollama_seat
    anchor = packet["governing_unit"]["ref"]
    allowlist = _packet_allowlist(packet)
    user = json.dumps(packet, indent=2, ensure_ascii=False)

    opinions: list[SeatOpinion] = []
    for seat in seats:
        try:
            raw = fn(seat["model"], _SEAT_SYSTEM, user)
        except Exception as exc:  # noqa: BLE001 - a failed seat is a non-vote, not a crash
            op = SeatOpinion(seat_id=seat["id"], model=seat["model"], dropped=f"seat error: {exc}")
            opinions.append(op)
            continue
        opinions.append(_parse_seat(seat["id"], seat["model"], raw, allowlist))

    roster = len(seats)
    required = math.ceil((quorum * roster) - 1e-9)
    voting = [o for o in opinions if o.votes]
    counts = Counter(o.determination for o in voting)
    votes = {d: counts.get(d, 0) for d in _DETERMINATIONS}
    top = max(votes.values(), default=0)
    leaders = [d for d, c in votes.items() if c == top and c > 0]

    if len(leaders) == 1 and top >= required:
        decision = leaders[0]
        rationale = f"{decision} reached {top}/{roster} votes (needed {required})"
    else:
        decision = "ESCALATE"
        rationale = f"no determination reached {required}/{roster} votes — S04"

    finding_type = ""
    if decision in _UNMET:
        ft_counts = Counter(
            o.finding_type for o in voting if o.determination == decision and o.finding_type
        )
        finding_type = ft_counts.most_common(1)[0][0] if ft_counts else ""

    dissent = [o.seat_id for o in voting if o.determination != decision]
    citations = sorted({r for o in voting for r in o.cited_refs if _ref_in_allowlist(r, allowlist)})

    override = None
    if decision in _UNMET and packet.get("reference_closure"):
        override = _run_override(packet, decision, seats, fn, reference_texts or {})
        if override and override.get("overrides"):
            decision = "SUPPORTED"
            finding_type = ""
            rationale += f"; overturned by exception {override.get('exception_ref')}"

    return CouncilResult(
        anchor=anchor,
        determination=decision,
        finding_type=finding_type,
        quorum_required=required,
        roster=roster,
        votes=votes,
        dissent=dissent,
        opinions=opinions,
        citations=citations,
        override=override,
        rationale=rationale,
    )


def _run_override(
    packet: dict[str, Any],
    decision: str,
    seats: list[dict[str, str]],
    fn: SeatFn,
    reference_texts: dict[str, str],
) -> dict[str, Any] | None:
    material = {
        "governing_unit": packet["governing_unit"],
        "judged": decision,
        "referenced_units": [
            {"ref": r, "text": reference_texts.get(r, "(text not supplied)")}
            for r in packet["reference_closure"]
        ],
        "exception_clauses": packet.get("exception_clauses", []),
    }
    user = json.dumps(material, indent=2, ensure_ascii=False)
    yes = 0
    ref = None
    n = 0
    for seat in seats:
        try:
            obj = _json_object(fn(seat["model"], _OVERRIDE_SYSTEM, user))
        except Exception:  # noqa: BLE001
            continue
        if not obj:
            continue
        n += 1
        if obj.get("overrides") is True:
            yes += 1
            ref = ref or obj.get("exception_ref")
    if n == 0:
        return None
    return {"overrides": yes > n / 2, "exception_ref": ref, "yes": yes, "asked": n}
