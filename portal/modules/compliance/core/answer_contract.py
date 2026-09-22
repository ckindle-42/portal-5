"""The answer contract: what the material presented, in machine-readable form.

``reading_material.render`` knows every section's id, side and address — it
uses all of it to build the message — and then returns prose plus counts and
discards the rest. Every component that later JUDGES an answer about that
material re-derives those semantics from scratch. Counted at e45ee1f4:

    7   independent regexes for "what is a section id", with three different
        definitions of the hex length ({8,}, {20}, +)
    14  independent decisions of "is this the operator side"
    30  independent decisions of "is this a valid requirement address"

They disagree, and nothing in the module ever compares them. Every defect
CLOSEOUT_V1 hit was one of those disagreements:

* the renderer gives an operator note its own heading; the scorer decided a
  note was not operator, because it tested ``jurisdiction == "internal"`` and
  a note is ``"operator_note"``. The ``interval`` case has been scored FAIL
  since 97330066 while the hand verdict recorded PASS.
* the standard writes ``R2.4`` in its own text; ``parse_ref`` rejected
  ``R2.4`` as "not a regulatory address".
* the renderer emitted a 20-character id; one dropped character voided the
  citation and blocked the close.

None is a reading failure. Each is a judge disagreeing with the material
about what the material said.

The point is not that this is a better implementation of the same rules. It
is that there is now exactly one place where "what counts as a citation, a
side, an address" is decided, and it is the place that built the material.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

__all__ = ["AnswerContract", "SECTION_ID_PATTERN", "Token", "build_contract"]

#: ONE definition, replacing seven. Deliberately permissive on length so a
#: malformed id is CAPTURED and reported unresolvable, never silently skipped
#: by a regex that demanded exactly 20 and therefore never saw it. The bare
#: pattern (no boundaries, no group) is exported so a caller that needs its
#: own capture group or its own boundary treatment — reader.py serves answers
#: with no contract in scope — builds on the same definition instead of a
#: second one.
SECTION_ID_PATTERN = r"[ci]section-[0-9a-f]{6,}(?:#\d+)?"
_SECTION_TOKEN = re.compile(rf"\b{SECTION_ID_PATTERN}\b", re.I)
_HANDLE_TOKEN = re.compile(r"\b([RON])(\d{1,3})\b")
#: the side-letter + 6-hex token ``addressing.cite_as`` puts beside every
#: section id in a tool payload — short enough to copy without error, stable
#: per section, and resolved here by UNIQUE PREFIX (an ambiguous prefix
#: resolves to nothing, never to a guess).
_CITEAS_TOKEN = re.compile(r"\b([RON])-([0-9a-f]{6})\b", re.I)

_HANDLE_PREFIX = {"regulatory": "R", "operator": "O", "operator_note": "N"}

#: edit distance at which an unresolved token reads as a MISTYPED RESTATEMENT
#: of a resolving citation rather than a different section being cited. The
#: measured case (CIP-007-6 unused_latitude, PROVE_THE_MODULE_V1 §P5) dropped
#: three characters mid-hash: ``…c8bc217ac`` typed as ``…c217ac``. Absorption
#: only ever applies to a token that resolves to NOTHING — a different REAL
#: section resolves and is judged as itself — so a 3-edit window never
#: re-labels a real citation of another section; it only recognises a
#: mistyped restatement of support the answer already carries.
_VARIANT_DISTANCE = 3


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > _VARIANT_DISTANCE:
        return _VARIANT_DISTANCE + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _mistyped_variant_of(token: str, resolving_tokens: list[str]) -> bool:
    """True when ``token`` is a small-edit copy of one of the ids that DID
    resolve in this answer — a restatement of present support, never a repair:
    the token itself stays unresolved and is reported as typed."""
    body = re.sub(r"[^0-9a-zA-Z]", "", token.split("#")[0]).lower()
    for other in resolving_tokens:
        other_body = re.sub(r"[^0-9a-zA-Z]", "", other.split("#")[0]).lower()
        if body[:1] != other_body[:1]:  # c…/i… — a different side is not a typo
            continue
        if _levenshtein(body, other_body) <= _VARIANT_DISTANCE:
            return True
    return False


@dataclass(frozen=True)
class Token:
    """One citable thing, as the material presented it."""

    handle: str
    section_id: str
    side: str  # operator | regulatory | derived | unknown
    #: the population's own label, which distinguishes an operator DOCUMENT
    #: from an operator NOTE even though both are the operator side
    kind: str = ""
    document: str = ""


@dataclass
class AnswerContract:
    """What this rendering offered, and what an answer about it may say."""

    ref: str
    canonical_ref: str
    tokens: dict[str, Token] = field(default_factory=dict)  # handle -> Token
    by_section_id: dict[str, Token] = field(default_factory=dict)  # id -> Token
    addresses: dict[str, str] = field(default_factory=dict)  # spelling -> canonical

    def resolve(self, token: str) -> Token | None:
        """A handle, a raw section id, or a ``cite_as`` prefix token. Unknown
        resolves to None — never to a near neighbour. Repairing a citation by
        similarity could attach a claim to the wrong document, which is worse
        than refusing it."""
        raw = str(token or "").strip().lstrip("[").rstrip("]")
        if not raw:
            return None
        hit = self.tokens.get(raw.upper())
        if hit is not None:
            return hit
        citeas = _CITEAS_TOKEN.fullmatch(raw)
        if citeas is not None:
            letter, prefix = citeas.group(1).upper(), citeas.group(2).lower()
            matches = [
                t
                for sid, t in self.by_section_id.items()
                if sid.rsplit("-", 1)[-1].startswith(prefix) and t.side[0].upper() == letter
            ]
            return matches[0] if len(matches) == 1 else None
        return self.by_section_id.get(raw.split("#")[0].lower())

    def side(self, token: str) -> str | None:
        found = self.resolve(token)
        return found.side if found else None

    def cited(self, answer: str) -> dict[str, Any]:
        """Every citation in an answer, resolved against what was presented.

        Unresolved is reported, never dropped: a dropped-character id is
        exactly what blocked CLOSEOUT_V1 §P8, and a regex requiring 20 hex
        characters would not even have seen it.
        """
        text = str(answer or "")
        seen: dict[str, Token] = {}
        unresolved: list[str] = []

        for pattern in (_SECTION_TOKEN, _HANDLE_TOKEN, _CITEAS_TOKEN):
            for m in pattern.finditer(text):
                raw = m.group(0)
                found = self.resolve(raw)
                if found is None:
                    unresolved.append(raw)
                else:
                    seen[found.section_id] = found

        by_side: dict[str, list[str]] = {}
        for tok in seen.values():
            by_side.setdefault(tok.side, []).append(tok.section_id)
        return {
            "resolved": sorted(seen),
            "by_side": {k: sorted(v) for k, v in sorted(by_side.items())},
            "unresolved": sorted(dict.fromkeys(unresolved)),
            "operator": sorted(by_side.get("operator", [])),
            "regulatory": sorted(by_side.get("regulatory", [])),
            "both_sides": bool(by_side.get("operator") and by_side.get("regulatory")),
        }

    def is_address(self, text: str) -> str | None:
        """Canonical form of a requirement address as THIS material spelled it,
        or None. ``R2.4`` is the standard's own shorthand and resolves; a
        malformed address does not."""
        raw = " ".join(str(text or "").split())
        return self.addresses.get(raw) or self.addresses.get(raw.upper())

    def cited_claims(self, answer: str) -> dict[str, Any]:
        """Per-claim grounding (LOAD_AND_CONVERSE_V1 §P5).

        The token-level check — *does every token resolve* — failed an answer in
        which every claim was supported: CIP-007-6 unused_latitude cited the
        correct section id and, one bullet later, the same id with two
        characters dropped. Every claim was grounded; the stray mistyped
        restatement voided the whole answer. The objective this replaces it
        with has two halves, and both are enforced:

        * an answer whose every claim carries a resolving citation PASSES — a
          claim unit (one line of the answer; markdown answers make the bullet
          the natural claim) is grounded when it cites a token that resolves,
          or when its only unresolved token is a small-edit variant of a
          resolving id cited ELSEWHERE IN THE SAME ANSWER — a mistyped
          restatement of support that is present and resolving, not support of
          its own;
        * an answer containing a citation that supports nothing FAILS — a claim
          whose citations are ALL unresolved with no resolving counterpart
          anywhere in the answer is a claim standing on a section the store
          cannot name.

        The unresolved token is never mapped onto its resolving neighbour: it
        stays in ``unresolved``, reported as it was typed. Support is only ever
        attributed to the id that actually resolves. Repairing the token would
        attach a claim to whatever the repair chose — that is the failure this
        instrument exists to refuse.
        """
        text = str(answer or "")
        tokens_by_line: list[tuple[str, list[str], list[str]]] = []
        resolving_raw: list[str] = []
        unresolved_everywhere: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            resolved_here: list[str] = []
            unresolved_here: list[str] = []
            for pattern in (_SECTION_TOKEN, _HANDLE_TOKEN, _CITEAS_TOKEN):
                for m in pattern.finditer(stripped):
                    raw = m.group(0)
                    if self.resolve(raw) is not None:
                        resolved_here.append(raw)
                        resolving_raw.append(raw)
                    else:
                        unresolved_here.append(raw)
                        unresolved_everywhere.append(raw)
            tokens_by_line.append((stripped, resolved_here, unresolved_here))

        claims: list[dict[str, Any]] = []
        for line, resolved_here, unresolved_here in tokens_by_line:
            if not resolved_here and not unresolved_here:
                continue  # a line that cites nothing is not a citation-bearing claim
            supported = bool(resolved_here) or any(
                _mistyped_variant_of(raw, resolving_raw) for raw in unresolved_here
            )
            claims.append(
                {
                    "claim": line,
                    "resolved": sorted(dict.fromkeys(resolved_here)),
                    "unresolved": sorted(dict.fromkeys(unresolved_here)),
                    "grounded": supported,
                }
            )

        unsupported = [c for c in claims if not c["grounded"]]
        return {
            "claims": claims,
            "n_claims": len(claims),
            "n_ungrounded": len(unsupported),
            "unsupported_lines": [c["claim"] for c in unsupported],
            "unresolved": sorted(dict.fromkeys(unresolved_everywhere)),
            "grounded": bool(claims) and not unsupported,
        }


#: What ``requirement_scope.population`` already calls each side, mapped to the
#: side an ANSWER is judged on. This is the load-bearing line of the module:
#: the population assigns these STRUCTURALLY — regulatory from the standard's
#: own join, operator from ``reading_assembly.linked_internal``, operator_note
#: from the notes path — and never consults ``jurisdiction`` at all. The lower
#: layer already had the right answer; the judges re-derived a worse one.
_POPULATION_SIDE = {
    "regulatory": "regulatory",
    "operator": "operator",
    "operator_note": "operator",
}


def build_contract(
    ref: str,
    canonical_ref: str,
    sections: list[dict[str, Any]],
    addresses: dict[str, str] | None = None,
) -> AnswerContract:
    """Build from the same rows the renderer just laid out.

    ``sections`` entries carry the population's own ``side``
    (``regulatory`` | ``operator`` | ``operator_note``) plus ``section_id``.
    The side is taken from there, NOT re-derived from ``jurisdiction``:
    ``reading_material`` contains zero references to jurisdiction, and the
    population's label is the one the material was actually built from.

    ``jurisdiction`` is accepted when present (store rows carry it) and used
    only as a fallback for callers that have no population in scope.
    """
    contract = AnswerContract(ref=ref, canonical_ref=canonical_ref, addresses=dict(addresses or {}))
    counters: dict[str, int] = {}
    for row in sections:
        section_id = str(row.get("section_id") or "").strip().lower()
        if not section_id:
            continue
        kind = str(row.get("side") or "")
        if kind in _POPULATION_SIDE:
            side = _POPULATION_SIDE[kind]
        else:
            # No population in scope — fall back to the jurisdiction domain.
            from portal.modules.compliance.core.jurisdiction import side_of

            jur = str(row.get("jurisdiction") or "")
            side = side_of(jur)
            kind = "operator_note" if jur == "operator_note" else side
        counters[kind] = counters.get(kind, 0) + 1
        token = Token(
            handle=f"{_HANDLE_PREFIX.get(kind, 'X')}{counters[kind]}",
            section_id=section_id,
            side=side,
            kind=kind,
            document=str(row.get("document_title") or row.get("logical_id") or ""),
        )
        contract.tokens[token.handle.upper()] = token
        contract.by_section_id[section_id] = token
    return contract
