"""Two-clock selection over the canonical store (END_TO_END Phase 5).

``valid_at`` — what applied in the world.
``known_at`` — what the store believed at that moment.

Every selection here reads the canonical tables (effectivity_assertions,
document_revisions, relationship_assertions) and applies BOTH clocks:

* ``valid_from <= valid_at < valid_to`` (an unknown ``valid_from`` is never
  "always true" — F02), and
* ``recorded_from <= known_at < recorded_to`` (``recorded_from`` is NOT NULL
  on every row — a row must know when the system started believing it).

A fact that was already true but not yet recorded answers differently from a
fact that was recorded and true: the former is ``UNKNOWN_KNOWLEDGE`` (the
late-recorded shape, lesson L21), the latter is selected. Corrections close
the prior row's ``recorded_to`` and never mutate it, so replay before/after a
correction is a pure query.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from portal.modules.compliance.core.temporal import parse_iso_date


def _clock_params(valid_at: str | None, known_at: str | None) -> tuple[str, str]:
    valid = parse_iso_date(valid_at, field="valid_at") if valid_at else ""
    known = known_at or ""
    return valid, known


def select_revision_effectivity(
    conn: sqlite3.Connection,
    *,
    family: str,
    valid_at: str,
    known_at: str = "",
) -> dict[str, Any]:
    """Resolve which standard revision(s) of ``family`` govern at ``valid_at``
    as known at ``known_at`` (default: latest recorded knowledge).

    Effectivity is read from the canonical ``effectivity_assertions`` of the
    family's requirement nodes — never from filenames or a static register
    snapshot. Node ids carry the revision identity (``CIP-007-6 R2 Part 2.1``
    → version ``6``), so the selection survives the store's mixed revision-id
    schemes. Returns the selected revisions with their sourced intervals,
    plus the as-known disclosure: a revision effective at ``valid_at`` whose
    effectivity was only recorded AFTER ``known_at`` is reported as
    ``UNKNOWN_KNOWLEDGE``, not silently included or dropped.
    """
    valid, known = _clock_params(valid_at, known_at)
    rows = conn.execute(
        """SELECT rn.node_id, ea.valid_from, ea.valid_to, ea.recorded_from, ea.recorded_to
           FROM requirement_nodes rn
           JOIN effectivity_assertions ea ON ea.node_id = rn.node_id
           WHERE rn.node_id LIKE ? || '-%'""",
        (family,),
    ).fetchall()
    by_version: dict[str, dict[str, Any]] = {}
    for node_id, v_from, v_to, r_from, r_to in rows:
        rest = node_id[len(family) + 1 :]
        version = rest.split(" ", 1)[0]
        entry = by_version.setdefault(version, {"intervals": []})
        if v_from:
            entry["intervals"].append((v_from, v_to, r_from, r_to))
    revision_ids = {
        version: [
            r[0]
            for r in conn.execute(
                "SELECT revision_id FROM standard_revisions WHERE family = ? AND version = ?",
                (family, version),
            ).fetchall()
        ]
        for version in by_version
    }

    current, future, historical, unknown_knowledge = [], [], [], []
    for version, entry in sorted(by_version.items()):
        intervals = entry["intervals"]
        if not intervals:
            continue  # no sourced effectivity — never guessed
        revision = {
            "family": family,
            "version": version,
            "revision_ids": sorted(revision_ids.get(version, [])),
            "valid_from": min(i[0] for i in intervals),
            "valid_to": max((i[1] for i in intervals if i[1]), default=None),
            "recorded_from": min(i[2] for i in intervals),
        }
        # knowledge state at known_at: a row is VISIBLE when the requested
        # knowledge time falls inside its recording interval ("" = latest
        # knowledge, which also drops superseded rows whose recorded_to has
        # been closed by a correction — they are no longer believed).
        visible = [
            (v_from, v_to)
            for v_from, v_to, r_from, r_to in intervals
            if (not known or r_from <= known) and (r_to is None or r_to > known)
        ]
        # did the store know ANYTHING about this revision by known_at?
        knew_anything = (not known) or any(r_from <= known for *_x, r_from, _r_to in intervals)
        if not knew_anything or not visible:
            # true then, but this store did not know it yet (late-recorded),
            # or every row it knew has since been corrected away
            revision["as_known"] = "UNKNOWN_KNOWLEDGE"
            revision["detail"] = (
                f"effectivity recorded from {revision['recorded_from']}, after the "
                f"requested known_at {known}"
                if not knew_anything
                else f"no effectivity row believed at the requested known_at {known}"
            )
            unknown_knowledge.append(revision)
            continue
        effective_now = any(
            v_from <= valid and (v_to is None or v_to > valid) for v_from, v_to in visible
        )
        if effective_now:
            revision["as_known"] = "SELECTED"
            current.append(revision)
        elif (
            valid >= revision["valid_from"]
            and revision["valid_to"]
            and valid >= revision["valid_to"]
        ):
            revision["as_known"] = "SUPERSEDED_OR_RETIRED"
            historical.append(revision)
        else:
            revision["as_known"] = "FUTURE"
            future.append(revision)
    return {
        "family": family,
        "valid_at": valid,
        "known_at": known or "latest recorded knowledge",
        "selected": current,
        "future": future,
        "historical": historical,
        "unknown_knowledge": unknown_knowledge,
    }


def temporal_exclusion_census(
    conn: sqlite3.Connection,
    *,
    valid_at: str | None,
    known_at: str | None,
    statuses: tuple[str, ...] = ("approved",),
) -> dict[str, int]:
    """How many relationship rows each clock excludes, so an empty temporal
    result is explained instead of silently reading as 'nothing relates'."""
    valid, known = _clock_params(valid_at, known_at)
    placeholders = ",".join("?" for _ in statuses)
    base = f"SELECT count(*) FROM relationship_assertions WHERE status IN ({placeholders})"
    total = conn.execute(base, statuses).fetchone()[0]
    census: dict[str, int] = {"in_scope": total, "excluded_unknown_validity": 0}
    if valid:
        census["excluded_unknown_validity"] = conn.execute(
            base + " AND valid_from IS NULL", statuses
        ).fetchone()[0]
    return census


def store_nodes_for_revisions(
    conn: sqlite3.Connection, revision_ids: set[str], *, exclude_standards: set[str] = ()
) -> dict[str, dict[str, Any]]:
    """Canonical-store duty text for revisions the pinned register does not
    carry (e.g. the future CIP-007-7.1): the requirement_nodes of those
    revisions with their verbatim atom clauses — never invented text."""
    if not revision_ids:
        return {}
    placeholders = ",".join("?" for _ in revision_ids)
    rows = conn.execute(
        f"""SELECT rn.node_id, rn.requirement, rn.part,
                   COALESCE(oa.clause_text, '') AS clause_text
            FROM requirement_nodes rn
            LEFT JOIN obligation_atoms oa ON oa.node_id = rn.node_id
            WHERE rn.standard_revision_id IN ({placeholders})
            ORDER BY rn.node_id, oa.atom_id""",
        tuple(revision_ids),
    ).fetchall()
    parts: dict[str, dict[str, Any]] = {}
    for node_id, requirement, part, clause in rows:
        standard_id = node_id.rsplit(" Part ", 1)[0]
        if any(standard_id.startswith(exc) for exc in exclude_standards):
            continue
        entry = parts.setdefault(
            node_id,
            {
                "id": node_id,
                "standard": standard_id,
                "requirement": requirement,
                "part": part,
                "clauses": [],
                "source": "canonical store decomposition (revision not in the pinned register)",
            },
        )
        if clause:
            entry["clauses"].append(clause)
    return parts


def withhold_unknown_knowledge(
    parts: list[dict[str, Any]], selection: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split resolved parts into (kept, withheld) under the requested
    ``known_at``: a part whose revision's effectivity was not yet recorded at
    the requested knowledge time is NOT served as known — the withheld list
    names it and why (late-recorded fact, L21)."""
    if not selection or not selection.get("unknown_knowledge"):
        return parts, []
    unknown = {u["version"]: u for u in selection["unknown_knowledge"]}
    kept: list[dict[str, Any]] = []
    withheld: list[dict[str, Any]] = []
    for part in parts:
        standard = str(part.get("standard", ""))
        version = standard.rsplit("-", 1)[1] if standard else ""
        fact = unknown.get(version)
        if fact:
            withheld.append(
                {
                    "id": part["id"],
                    "version": version,
                    "as_known": "UNKNOWN_KNOWLEDGE",
                    "detail": fact["detail"],
                }
            )
        else:
            kept.append(part)
    return kept, withheld
