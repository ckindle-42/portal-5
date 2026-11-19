"""Section 6 — the lab path, contributed by the security module's own query builders.

The platform never imports module code: the security plugin offers its section as hop
dicts through the plugin seam, and this adapter turns them into typed hops.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from portal.platform import plugins

from .model import Hop, Status, short

SECTION = "lab"
ADAPTER = "lab section"


def _to_hop(raw: Any) -> Hop:
    if not isinstance(raw, dict):
        raise ValueError(f"hop is {type(raw).__name__}, not a dict")
    name = short(raw.get("name") or "?", 40)
    status = Status(str(raw.get("status") or "").upper())
    return Hop(
        name,
        status,
        short(raw.get("observed", "")),
        short(raw.get("expected", "")),
        short(raw.get("detail", "")),
    )


def contributed(
    section: str,
    adapter: str,
    expected: str,
    sections: dict[str, Callable[[], list[dict[str, str]]]] | None = None,
) -> list[Hop]:
    """The contributed hops; absence or malformed output is a FAIL, never a skip."""
    provided = plugins.trace_sections() if sections is None else sections
    run = provided.get(section)
    if run is None:
        return [Hop(adapter, Status.FAIL, f"no module contributes '{section}'", expected)]
    try:
        raws = run()
    except Exception as exc:  # noqa: BLE001 - an unreachable hop is the finding
        return [Hop(adapter, Status.FAIL, short(f"{type(exc).__name__}: {exc}", 70), "completes")]
    try:
        hops = [_to_hop(raw) for raw in raws]
    except (TypeError, ValueError) as exc:
        return [Hop(adapter, Status.FAIL, short(str(exc), 70), "well-formed hops")]
    return hops or [Hop(adapter, Status.FAIL, "section produced no hops", "at least one hop")]


def run(
    sections: dict[str, Callable[[], list[dict[str, str]]]] | None = None,
) -> list[Hop]:
    """The contributed lab hops; absence or malformed output is a FAIL, never a skip."""
    return contributed(SECTION, ADAPTER, "security module", sections)
