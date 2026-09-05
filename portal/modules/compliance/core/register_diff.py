"""Register diff at Part granularity (T4 Phase 1).

Given two register states for a standard, emit a **typed** diff. Structural
change (a Part added or removed) is a set difference; the case that matters most
is a Part that survives with **modified language** — a timeline moved, an
applicability widened, an evidence expectation tightened.

`LANGUAGE_CHANGED` is sub-classified so *"replaced shall with should"* and
*"corrected a typo"* do not produce the same alert:

    modality   — a deontic modal changed (shall <-> should/may)
    timeline   — a numeric duration/deadline changed
    evidence   — the measure text changed
    substantive — other wording changes that alter the obligation
    cosmetic   — punctuation / whitespace / trivial only (NOT raised as an
                 obligation change)

`RENUMBERED` needs a high similarity threshold; a low-confidence pairing is
`NEEDS_REVIEW` and a Part is never paired silently.

**Every diff row carries both verbatim spans**, old and new — the change is
auditable and a reviewer never trusts a summary of it. **Derive the diff from
the register; verify it against the implementation plan** (Phase 3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from portal.modules.compliance.core.cip_register import Register, RegisterNode

CHANGE_TYPES = (
    "PART_ADDED",
    "PART_REMOVED",
    "LANGUAGE_CHANGED",
    "APPLICABILITY_CHANGED",
    "TIMELINE_CHANGED",
    "EVIDENCE_CHANGED",
    "SEVERITY_CHANGED",
    "RENUMBERED",
)
_RENUMBER_HI = 0.90  # paired
_RENUMBER_LO = 0.60  # NEEDS_REVIEW below this it's a genuine add/remove

_DURATION_RE = re.compile(
    r"\b(\d{1,4})\s+(?:calendar\s+|business\s+|consecutive\s+)?"
    r"(day|days|month|months|year|years|hour|hours|week|weeks)\b",
    re.I,
)
_MODAL_RE = re.compile(r"\b(shall|must|will|should|may|strive to|endeavor to)\b", re.I)
_MANDATORY = {"shall", "must", "will"}


_TRAILING_GLUE_RE = re.compile(r"[;,.]?\s*[;,.]?\s*$")
_TRAILING_CONNECTOR_RE = re.compile(r"[;,.]?\s*\b(and|or)\b\s*[;,.]?\s*$", re.I)


def _casefold(s: str) -> str:
    return re.sub(r"[\s\W_]+", " ", s.lower()).strip()


def _trailing_connector(s: str) -> str | None:
    """The list connector (``and``/``or``) trailing this span, if any."""
    m = _TRAILING_CONNECTOR_RE.search(s.strip())
    return m.group(1).lower() if m else None


def _strip_trailing_glue(s: str) -> str:
    """Drop a trailing connector/punctuation ONLY — never used to decide
    whether the connector itself changed (see ``_cosmetic_equal``)."""
    stripped = _TRAILING_CONNECTOR_RE.sub("", s.strip())
    return _TRAILING_GLUE_RE.sub("", stripped)


def _cosmetic_equal(a: str, b: str) -> bool:
    """Equal once whitespace, punctuation and case are neutralised, and once a
    trailing list conjunction is dropped. NERC renumbers a nested topic list
    by moving the ``; and`` glue between items (the last item loses it, a new
    penultimate item gains it) — a connector APPEARING or DISAPPEARING alone
    is that ordinary glue shift, still cosmetic. A genuine swap between "and"
    and "or" on the SAME item — both sides carrying a connector that differs
    (F06) — is never cosmetic: it changes the obligation from conjunctive to
    disjunctive (or vice versa)."""
    ca, cb = _trailing_connector(a), _trailing_connector(b)
    if ca and cb and ca != cb:
        return False
    na = _casefold(_strip_trailing_glue(a.strip()))
    nb = _casefold(_strip_trailing_glue(b.strip()))
    return na == nb


def _durations(t: str) -> set[tuple[int, str]]:
    return {(int(m.group(1)), m.group(2).lower().rstrip("s")) for m in _DURATION_RE.finditer(t)}


def _modality(t: str) -> str:
    ms = {m.group(1).lower() for m in _MODAL_RE.finditer(t)}
    if ms & _MANDATORY:
        return "mandatory"
    if ms:
        return "non-binding"
    return "none"


@dataclass
class DiffRow:
    change_type: str
    part_id_old: str
    part_id_new: str
    old_span: str
    new_span: str
    sub_type: str = ""
    confidence: float = 1.0
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "change_type": self.change_type,
            "sub_type": self.sub_type,
            "part_id_old": self.part_id_old,
            "part_id_new": self.part_id_new,
            "old_span": self.old_span,
            "new_span": self.new_span,
            "confidence": round(self.confidence, 3),
            "detail": self.detail,
            "substantive": self.change_type != "LANGUAGE_CHANGED" or self.sub_type != "cosmetic",
        }


def _classify_language(old: RegisterNode, new: RegisterNode) -> DiffRow:
    base = {
        "part_id_old": old.id,
        "part_id_new": new.id,
        "old_span": old.verbatim_text,
        "new_span": new.verbatim_text,
    }
    if _cosmetic_equal(old.verbatim_text, new.verbatim_text):
        return DiffRow(
            "LANGUAGE_CHANGED", sub_type="cosmetic", detail="punctuation/whitespace only", **base
        )
    old_conn, new_conn = (
        _trailing_connector(old.verbatim_text),
        _trailing_connector(new.verbatim_text),
    )
    if (
        old_conn
        and new_conn
        and old_conn != new_conn
        and _casefold(_strip_trailing_glue(old.verbatim_text))
        == _casefold(_strip_trailing_glue(new.verbatim_text))
    ):
        # F06: an AND<->OR swap (or a connector appearing/disappearing) on an
        # OTHERWISE-unchanged list item is a pure logic change, never
        # cosmetic — it flips the obligation between conjunctive and
        # disjunctive. Scoped to the SAME item text so an unrelated full
        # rewrite that merely happens to also end in "and"/"or" is not
        # mislabelled "logic" instead of "substantive".
        return DiffRow(
            "LANGUAGE_CHANGED",
            sub_type="logic",
            detail=f"list connector changed: {old_conn or 'none'} -> {new_conn or 'none'} "
            "(alters the obligation's AND/OR structure)",
            **base,
        )
    do, dn = _durations(old.verbatim_text), _durations(new.verbatim_text)
    if do != dn and (do or dn):
        return DiffRow(
            "TIMELINE_CHANGED",
            sub_type="timeline",
            detail=f"{sorted(do)} -> {sorted(dn)}",
            **base,
        )
    mo, mn = _modality(old.verbatim_text), _modality(new.verbatim_text)
    if mo != mn:
        return DiffRow(
            "LANGUAGE_CHANGED", sub_type="modality", detail=f"modality {mo} -> {mn}", **base
        )
    return DiffRow(
        "LANGUAGE_CHANGED",
        sub_type="substantive",
        detail="wording changed with no modality/timeline signal",
        confidence=round(SequenceMatcher(None, old.verbatim_text, new.verbatim_text).ratio(), 3),
        **base,
    )


def diff_standard(old: Register, new: Register, standard_base: str) -> list[DiffRow]:  # noqa: PLR0912, C901 - one coherent pass over 8 change types + shift-insert + operand validation
    """Typed Part-level diff between the ``standard_base`` (e.g. ``CIP-003``)
    nodes of two register states. ``standard_base`` matches the versioned
    ``standard`` prefix, so ``CIP-003`` picks up ``CIP-003-8`` in ``old`` and
    ``CIP-003-9`` in ``new``."""
    # F06 / P1.6: explicitly validate one old revision and one new revision;
    # reject mixed-version operands rather than silently keying by
    # (requirement, part) across whatever versions happen to be present.
    o_versions = {n.standard for n in old.nodes if n.standard.startswith(standard_base)}
    n_versions = {n.standard for n in new.nodes if n.standard.startswith(standard_base)}
    if len(o_versions) > 1:
        raise ValueError(
            f"diff_standard: mixed old-side revisions of {standard_base}: {sorted(o_versions)}"
        )
    if len(n_versions) > 1:
        raise ValueError(
            f"diff_standard: mixed new-side revisions of {standard_base}: {sorted(n_versions)}"
        )
    if not o_versions or not n_versions:
        missing = "old" if not o_versions else "new"
        raise ValueError(f"diff_standard: no {missing}-side nodes found for {standard_base}")

    o = {(n.requirement, n.part): n for n in old.nodes if n.standard.startswith(standard_base)}
    n = {(n.requirement, n.part): n for n in new.nodes if n.standard.startswith(standard_base)}
    rows: list[DiffRow] = []

    old_text_index = {_casefold(v.verbatim_text): kk for kk, v in o.items() if v.verbatim_text}

    common = o.keys() & n.keys()
    for k in sorted(common):
        a, b = o[k], n[k]
        if a.verbatim_text != b.verbatim_text:
            # shift-insert: a Part list where inserting an item at position i
            # pushes every id >= i down one, so id N now holds what id N-1 held.
            src_k = old_text_index.get(_casefold(b.verbatim_text))
            if src_k and src_k != k and src_k not in n:
                rows.append(
                    DiffRow(
                        "RENUMBERED",
                        part_id_old=o[src_k].id,
                        part_id_new=b.id,
                        old_span=o[src_k].verbatim_text,
                        new_span=b.verbatim_text,
                        sub_type="paired",
                        confidence=1.0,
                        detail=f"{o[src_k].requirement} {o[src_k].part} -> {b.requirement} {b.part} "
                        f"(shift-insert; text identical)",
                    )
                )
                continue
            rows.append(_classify_language(a, b))
        if a.applicable_systems != b.applicable_systems and (
            a.applicable_systems or b.applicable_systems
        ):
            rows.append(
                DiffRow(
                    "APPLICABILITY_CHANGED",
                    part_id_old=a.id,
                    part_id_new=b.id,
                    old_span=a.applicable_systems,
                    new_span=b.applicable_systems,
                    detail="applicability set differs",
                )
            )
        if a.measure_text != b.measure_text and (a.measure_text or b.measure_text):
            rows.append(
                DiffRow(
                    "EVIDENCE_CHANGED",
                    part_id_old=a.id,
                    part_id_new=b.id,
                    old_span=a.measure_text,
                    new_span=b.measure_text,
                    detail="measure text differs",
                )
            )
        if a.vrf != b.vrf and (a.vrf or b.vrf):
            rows.append(
                DiffRow(
                    "SEVERITY_CHANGED",
                    part_id_old=a.id,
                    part_id_new=b.id,
                    old_span=f"VRF {a.vrf}",
                    new_span=f"VRF {b.vrf}",
                    detail=f"VRF {a.vrf} -> {b.vrf}",
                )
            )

    only_old = {k: v for k, v in o.items() if k not in n}
    only_new = {k: v for k, v in n.items() if k not in o}

    # renumber detection before add/remove
    paired_new: set = set()
    for _ko, vo in sorted(only_old.items()):
        best_k, best_r = None, 0.0
        for kn, vn in only_new.items():
            if kn in paired_new:
                continue
            r = SequenceMatcher(None, vo.verbatim_text, vn.verbatim_text).ratio()
            if r > best_r:
                best_k, best_r = kn, r
        if best_k and best_r >= _RENUMBER_LO:
            paired_new.add(best_k)
            vn = only_new[best_k]
            rows.append(
                DiffRow(
                    "RENUMBERED",
                    part_id_old=vo.id,
                    part_id_new=vn.id,
                    old_span=vo.verbatim_text,
                    new_span=vn.verbatim_text,
                    sub_type="paired" if best_r >= _RENUMBER_HI else "needs_review",
                    confidence=round(best_r, 3),
                    detail=f"{vo.requirement} {vo.part} -> {vn.requirement} {vn.part} (sim {best_r:.2f})",
                )
            )
        else:
            rows.append(
                DiffRow(
                    "PART_REMOVED",
                    part_id_old=vo.id,
                    part_id_new="",
                    old_span=vo.verbatim_text,
                    new_span="",
                    detail=f"{vo.requirement} {vo.part} absent in the new version",
                )
            )
    for kn, vn in sorted(only_new.items()):
        if kn in paired_new:
            continue
        # shift-insert tail: this new id holds text that lived at an older id
        # whose slot is now occupied by different text.
        src_k = old_text_index.get(_casefold(vn.verbatim_text))
        if src_k and src_k in n and n[src_k].verbatim_text != o[src_k].verbatim_text:
            rows.append(
                DiffRow(
                    "RENUMBERED",
                    part_id_old=o[src_k].id,
                    part_id_new=vn.id,
                    old_span=o[src_k].verbatim_text,
                    new_span=vn.verbatim_text,
                    sub_type="paired",
                    confidence=1.0,
                    detail=f"{o[src_k].requirement} {o[src_k].part} -> {vn.requirement} {vn.part} "
                    f"(shift-insert; text identical)",
                )
            )
            continue
        rows.append(
            DiffRow(
                "PART_ADDED",
                part_id_old="",
                part_id_new=vn.id,
                old_span="",
                new_span=vn.verbatim_text,
                detail=f"{vn.requirement} {vn.part} new in this version",
            )
        )
    return rows


def diff_summary(rows: list[DiffRow]) -> dict:
    from collections import Counter

    by_type = Counter(r.change_type for r in rows)
    return {
        "n_rows": len(rows),
        "by_change_type": dict(by_type),
        "substantive": sum(1 for r in rows if r.to_dict()["substantive"]),
        "cosmetic": sum(1 for r in rows if not r.to_dict()["substantive"]),
        "needs_review_pairings": [
            r.to_dict()
            for r in rows
            if r.change_type == "RENUMBERED" and r.sub_type == "needs_review"
        ],
    }
