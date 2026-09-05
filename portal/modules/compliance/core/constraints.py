"""Typed constraint comparison with comparator direction (P5.3).

F05 already stopped tiers.py from silently converting between units, but a
conflict/uncertainty signal is not the same as knowing WHICH SIDE is
stricter — that requires knowing whether the constraint is a MAXIMUM
interval (shorter is stricter: "review at least once every N days") or a
MINIMUM retention (longer is stricter: "retain records for at least N days").
Design §6.2: "A shorter maximum deadline can be stricter, while a shorter
minimum retention period can be weaker."
"""

from __future__ import annotations

from dataclasses import dataclass

CONSTRAINT_KINDS = ("max_interval", "min_retention")
RESULTS = ("MORE_RESTRICTIVE", "LESS_RESTRICTIVE", "EQUIVALENT", "INCOMPARABLE")


@dataclass(frozen=True)
class Quantity:
    """A single numeric quantity with its unit and calendar/business
    qualifier — the same shape ``tiers.py``'s ``_quant_claims`` produces, so
    a caller can feed a parsed claim straight in."""

    value: int
    unit: str  # day | week | month | year | hour
    qualifier: str | None = None  # "business" | "calendar" | None (== calendar)

    @property
    def normalized_qualifier(self) -> str:
        return "business" if self.qualifier == "business" else "calendar"

    @property
    def key(self) -> tuple[str, str]:
        return (self.unit, self.normalized_qualifier)


def compare_constraint(kind: str, governing: Quantity, internal: Quantity) -> tuple[str, str]:
    """(result, reason). ``kind`` selects the comparator direction:

    - ``max_interval``: the governing value is an UPPER bound on how long you
      may wait ("at least once every N days"). A SMALLER internal value is
      MORE restrictive (does it more often); a LARGER internal value would
      violate the maximum outright — VIOLATION is a P5.6 finding concern, not
      this function's job, so a larger internal interval is still classified
      LESS_RESTRICTIVE here, and the caller decides whether that also
      constitutes non-compliance.
    - ``min_retention``: the governing value is a LOWER bound on how long you
      must keep something ("retain for at least N days"). A LARGER internal
      value is MORE restrictive; a SMALLER one is LESS_RESTRICTIVE.

    Different units/qualifiers (F05) are never converted — INCOMPARABLE."""
    if kind not in CONSTRAINT_KINDS:
        raise ValueError(f"kind must be one of {CONSTRAINT_KINDS}, got {kind!r}")
    if governing.key != internal.key:
        return (
            "INCOMPARABLE",
            f"governing uses {governing.key}, internal uses {internal.key} — "
            "no reviewed conversion rule (F05)",
        )
    if governing.value == internal.value:
        return "EQUIVALENT", "same value, same unit/qualifier"
    smaller_is_stricter = kind == "max_interval"
    internal_is_smaller = internal.value < governing.value
    stricter = internal_is_smaller if smaller_is_stricter else not internal_is_smaller
    if stricter:
        return (
            "MORE_RESTRICTIVE",
            f"internal {internal.value} {internal.unit} vs governing {governing.value} "
            f"{governing.unit} ({kind}) — internal is stricter",
        )
    return (
        "LESS_RESTRICTIVE",
        f"internal {internal.value} {internal.unit} vs governing {governing.value} "
        f"{governing.unit} ({kind}) — internal is looser",
    )
