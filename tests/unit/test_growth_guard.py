"""Enforce the C3 engine and behavioural-persona growth guard."""

from __future__ import annotations

from pathlib import Path

from portal.platform.inference.config import (
    load_bench_workspaces_raw,
    load_persona_map,
    load_portal_config,
)


def _catalog():
    return load_portal_config(include_bench=True)


def _one_line_reason(reason: str | None) -> bool:
    return bool(reason and reason.strip() and len(reason.splitlines()) == 1)


def test_declared_engines_equal_the_exposed_set() -> None:
    """The declared engine set must equal the exposed non-bench set."""
    cfg = _catalog()
    exposed = {
        wid
        for wid, spec in cfg.workspaces.items()
        if spec.expose_to_owui and spec.module != "eval" and not wid.startswith("bench-")
    }
    declared = {wid for wid, spec in cfg.workspaces.items() if spec.engine}
    unguarded = exposed - declared
    assert not unguarded, (
        f"user-facing engines without engine: true + engine_reason: {sorted(unguarded)} — "
        "a new user-facing engine must declare itself (C3)"
    )
    phantom = declared - exposed
    assert not phantom, (
        f"engine: true on non-user-facing lanes: {sorted(phantom)} — "
        "the declaration must match the exposed set exactly (C3)"
    )


def test_every_declared_engine_has_a_one_line_reason() -> None:
    cfg = _catalog()
    no_reason = [
        wid
        for wid, spec in cfg.workspaces.items()
        if spec.engine and not _one_line_reason(spec.engine_reason)
    ]
    assert not no_reason, f"engine: true without a one-line engine_reason: {sorted(no_reason)}"


def test_bench_lanes_never_declare_engine() -> None:
    bench_ids = set(load_bench_workspaces_raw(Path.cwd()))
    declared_bench = {wid for wid in bench_ids if _catalog().workspaces[wid].engine}
    assert not declared_bench, f"bench lanes must stay out of the engine guard: {declared_bench}"


def test_behavioural_personas_declare_a_reason() -> None:
    personas = load_persona_map(include_bench=True)
    unguarded = []
    for slug, persona in personas.items():
        behavioural = (
            persona.tools_allow is not None or bool(persona.tools_deny) or persona.tool_choice
        )
        if behavioural and not _one_line_reason(persona.persona_reason):
            unguarded.append(slug)
    assert not unguarded, (
        f"behavioural personas without a one-line persona_reason: {sorted(unguarded)}"
    )
