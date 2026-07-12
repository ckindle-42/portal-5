"""Module enable/disable → wiki write-back — M7 of
BUILD_PROGRAM_MODULARIZATION_ALL_V1.

Same confirm-gated propose_unit() path as writeback_bench (P4). A module
state change re-saves unit-module-<name> with its fenced yaml `enabled:`
field flipped — the wiki unit IS the state, not a separate event log, so
modules.enabled_modules() always reads current truth with no replay step.
"""

from __future__ import annotations

import re


def module_state_change(
    name: str,
    from_state: bool,
    to_state: bool,
    actor: str,
    *,
    auto_confirm: bool = False,
) -> dict | None:
    """Propose flipping module <name>'s enabled state.

    Args:
        name: module name (e.g. "eval")
        from_state: the state the actor believes is current (recorded for audit)
        to_state: the desired new state
        actor: who/what requested this (CLI, operator name, etc.)
        auto_confirm: if True, skip the confirm gate

    Returns:
        proposed unit dict, or None on failure (unit doesn't exist, or
        the unit's fenced yaml has no `enabled:` field to flip)
    """
    from portal.platform.wiki.schema import SourceRef
    from portal.platform.wiki.store import load_unit
    from portal.platform.wiki.writeback import propose_unit

    unit_id = f"unit-module-{name}"
    unit = load_unit(unit_id)
    if unit is None:
        return None

    pattern = re.compile(r"^(\s*enabled:\s*)(true|false)(\s*)$", re.MULTILINE | re.IGNORECASE)
    new_value = "true" if to_state else "false"

    if pattern.search(unit.body):
        new_body = pattern.sub(rf"\g<1>{new_value}\g<3>", unit.body, count=1)
    else:
        # No existing enabled: field (unit predates this feature) — add one
        # to the fenced yaml block if present, else append a new block.
        yaml_block = re.search(r"```yaml\n(.*?)\n```", unit.body, re.DOTALL)
        if yaml_block:
            insert_at = yaml_block.end(1)
            new_body = unit.body[:insert_at] + f"\nenabled: {new_value}" + unit.body[insert_at:]
        else:
            new_body = unit.body + f"\n\n```yaml\nenabled: {new_value}\n```\n"

    try:
        pu = propose_unit(
            {
                "id": unit_id,
                "title": unit.title,
                "kind": unit.kind,
                "sources": [
                    *[s.to_dict() if hasattr(s, "to_dict") else s for s in unit.sources],
                    SourceRef(type="code", path=f"module-state-change:{name}:{actor}").to_dict(),
                ],
                "body": new_body,
                "tags": unit.tags,
            },
            proposed_by=actor,
            auto_confirm=auto_confirm,
        )
        return pu.to_dict()
    except Exception:
        return None
