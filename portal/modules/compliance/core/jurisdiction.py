"""The jurisdiction domain, in one place, because it is not a boolean.

``source_documents.jurisdiction`` carries at least five values in a live
store: ``"US"`` (a NERC standard, the glossary), ``"internal"`` (the
operator's own documents), ``"operator_note"`` (an operator's recorded
decision about a requirement), ``"derived"`` (module-synthesised), and ``""``
(a legacy row from migrate_legacy).

Fourteen call sites reduced that to ``== "internal"`` and put everything else
on the regulatory side. ``reading_material`` never did — it renders three
sides and gives ``operator_note`` its own heading. So the material handed to
the model was always right and the code scoring the answer was always wrong
about one of the three.

Measured: the ``interval`` case cites the 30-day operator note
(``csection-440a5cdf9a6b65292ef3``, jurisdiction ``operator_note``) as the
operator side. PROVE_THEN_SCALE_V1 §P1 recorded that PASS by hand, "both
sides quoted". The cell's ``cited_both_sides`` field recorded False at the
same commit and every commit since.

The prefix is not the side either: an operator note carries a ``csection-``
id. Prefix is spelling; jurisdiction is truth; and truth has three values.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "DERIVED_JURISDICTIONS",
    "OPERATOR_JURISDICTIONS",
    "OPERATOR_SQL_IN",
    "REGULATORY_JURISDICTIONS",
    "is_operator_side",
    "is_regulatory_side",
    "side_of",
    "unknown_jurisdictions",
]

OPERATOR_JURISDICTIONS = frozenset({"internal", "operator_note"})
REGULATORY_JURISDICTIONS = frozenset({"US"})
#: Deliberately neither side: a derived section is not evidence the operator
#: wrote and not text the regulator published.
DERIVED_JURISDICTIONS = frozenset({"derived"})

#: For the places that filter in SQL. Beside the set so the two cannot drift.
OPERATOR_SQL_IN = "('internal', 'operator_note')"


def _norm(value: Any) -> str:
    return str(value or "").strip()


def is_operator_side(jurisdiction: Any) -> bool:
    """True for the operator's documents AND the operator's notes."""
    return _norm(jurisdiction) in OPERATOR_JURISDICTIONS


def is_regulatory_side(jurisdiction: Any) -> bool:
    """True only for the standard's side.

    This is NOT ``not is_operator_side(...)``. An unrecognised jurisdiction is
    neither side, and saying so is the point: the old two-valued test made
    "unknown" mean "regulatory" silently, which is how ``operator_note``
    became regulatory for the life of the module.
    """
    return _norm(jurisdiction) in REGULATORY_JURISDICTIONS


def side_of(jurisdiction: Any) -> str:
    """``"operator"`` | ``"regulatory"`` | ``"derived"`` | ``"unknown"``.

    ``unknown`` is returned, never guessed. A caller needing a binary answer
    must decide what to do with unknown explicitly; that decision is never
    made here by defaulting.
    """
    value = _norm(jurisdiction)
    if value in OPERATOR_JURISDICTIONS:
        return "operator"
    if value in REGULATORY_JURISDICTIONS:
        return "regulatory"
    if value in DERIVED_JURISDICTIONS:
        return "derived"
    return "unknown"


def unknown_jurisdictions(repo: Any) -> list[dict[str, Any]]:
    """Every distinct jurisdiction the module does not classify.

    A store that grows a sixth value must fail a check loudly, not slide into
    "regulatory" the way ``operator_note`` did.
    """
    known = OPERATOR_JURISDICTIONS | REGULATORY_JURISDICTIONS | DERIVED_JURISDICTIONS
    try:
        rows = repo._conn.execute(
            "SELECT jurisdiction, COUNT(*) FROM source_documents GROUP BY jurisdiction"
        ).fetchall()
    except Exception:  # noqa: BLE001 - an unreadable store reports nothing, never guesses
        return []
    return [
        {"jurisdiction": _norm(r[0]), "n_documents": int(r[1])}
        for r in rows
        if _norm(r[0]) not in known
    ]
