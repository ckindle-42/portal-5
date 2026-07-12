"""``portal module <cmd>`` — module enable/disable operations (M7 toggle layer,
BUILD_PROGRAM_COLLAPSE_V1.md Phase 9).

State lives in each unit-module-<name> wiki unit's fenced yaml `enabled:`
field (portal.platform.wiki.adapters.modules is the resolver, writeback_module is the
confirm-gated state-change path). Confirm-gated by default (auto_confirm=False,
same discipline as ``portal bench``/``portal wiki writeback``) — pass ``--yes``
to apply immediately. A confirmed change re-runs sync-config so
config/modules.generated.yaml, .mcp.json, and OWUI presets never drift from
the wiki's now-current state.
"""

from __future__ import annotations

import typer

from ._apps import module_app


@module_app.command("list")
def module_list() -> None:
    """List every module: enabled state, workspace/persona/mcp counts."""
    from portal.platform.inference.config import load_portal_config
    from portal.platform.wiki.adapters.modules import ALL_MODULES, enabled_modules

    cfg = load_portal_config()
    enabled = set(enabled_modules())

    ws_counts: dict[str, int] = dict.fromkeys(ALL_MODULES, 0)
    for spec in cfg.workspaces.values():
        if spec.module in ws_counts:
            ws_counts[spec.module] += 1

    persona_counts: dict[str, int] = dict.fromkeys(ALL_MODULES, 0)
    for persona in load_persona_map_safe().values():
        if persona.module in persona_counts:
            persona_counts[persona.module] += 1

    mcp_counts: dict[str, int] = dict.fromkeys(ALL_MODULES, 0)
    for m in cfg.mcp_fleet:
        if m.module in mcp_counts:
            mcp_counts[m.module] += 1

    typer.echo(f"{'module':<15} {'state':<12} {'workspaces':>10} {'personas':>9} {'mcp':>4}")
    for mod in sorted(ALL_MODULES):
        state = "enabled" if mod in enabled else "disabled"
        typer.echo(
            f"{mod:<15} {state:<12} {ws_counts[mod]:>10} {persona_counts[mod]:>9} {mcp_counts[mod]:>4}"
        )


@module_app.command("status")
def module_status(name: str = typer.Argument(..., help="Module name, e.g. 'eval'")) -> None:
    """Detailed view of one module: enabled state, workspace/persona ids, mcp ids."""
    from portal.platform.inference.config import load_portal_config
    from portal.platform.wiki.adapters.modules import (
        ALL_MODULES,
        _unit_enabled_state,
        enabled_modules,
    )

    if name not in ALL_MODULES:
        typer.echo(f"❌ Unknown module: {name!r}. Known: {sorted(ALL_MODULES)}", err=True)
        raise typer.Exit(code=1)

    cfg = load_portal_config()
    wiki_state = _unit_enabled_state(name)
    effective = name in enabled_modules()
    ws_ids = sorted(k for k, v in cfg.workspaces.items() if v.module == name)
    persona_slugs = sorted(p.slug for p in load_persona_map_safe().values() if p.module == name)
    mcp_ids = sorted(m.id for m in cfg.mcp_fleet if m.module == name)

    typer.echo(f"module:    {name}")
    typer.echo(f"enabled:   {effective}  (wiki unit-module-{name}: {wiki_state!r})")
    typer.echo(f"workspaces ({len(ws_ids)}): {', '.join(ws_ids) or '(none)'}")
    typer.echo(
        f"personas ({len(persona_slugs)}): {', '.join(persona_slugs[:10])}"
        f"{', …' if len(persona_slugs) > 10 else ''}"
    )
    typer.echo(f"mcp_fleet ({len(mcp_ids)}): {', '.join(mcp_ids) or '(none)'}")


@module_app.command("enable")
def module_enable(
    name: str = typer.Argument(..., help="Module name, e.g. 'eval'"),
    actor: str = typer.Option("cli", "--actor", help="Who/what requested this change"),
    yes: bool = typer.Option(False, "--yes", help="Apply immediately, skip the confirm gate"),
) -> None:
    """Enable a module (confirm-gated wiki write-back; --yes applies immediately)."""
    _set_module_state(name, True, actor, yes)


@module_app.command("disable")
def module_disable(
    name: str = typer.Argument(..., help="Module name, e.g. 'eval'"),
    actor: str = typer.Option("cli", "--actor", help="Who/what requested this change"),
    yes: bool = typer.Option(False, "--yes", help="Apply immediately, skip the confirm gate"),
) -> None:
    """Disable a module (confirm-gated wiki write-back; --yes applies immediately)."""
    _set_module_state(name, False, actor, yes)


def load_persona_map_safe() -> dict:
    """load_persona_map() with the default personas dir — thin wrapper so
    module_list/module_status don't each repeat the import."""
    from portal.platform.inference.config import load_persona_map

    return load_persona_map()


def _set_module_state(name: str, to_state: bool, actor: str, auto_confirm: bool) -> None:
    from portal.platform.wiki.adapters.modules import ALL_MODULES, enabled_modules
    from portal.platform.wiki.adapters.writeback_module import module_state_change

    if name not in ALL_MODULES:
        typer.echo(f"❌ Unknown module: {name!r}. Known: {sorted(ALL_MODULES)}", err=True)
        raise typer.Exit(code=1)

    from_state = name in enabled_modules()
    if from_state == to_state:
        verb = "enabled" if to_state else "disabled"
        typer.echo(f"'{name}' is already {verb} — no change.")
        return

    result = module_state_change(
        name, from_state=from_state, to_state=to_state, actor=actor, auto_confirm=auto_confirm
    )
    if result is None:
        typer.echo(
            f"❌ Could not propose state change for '{name}' "
            f"(unit-module-{name} not found in wiki).",
            err=True,
        )
        raise typer.Exit(code=1)

    status = result.get("status", "proposed")
    verb = "enabled" if to_state else "disabled"
    typer.echo(f"✅ '{name}' {verb} ({status}).")
    if status != "confirmed":
        typer.echo(
            "   Awaiting confirmation — see wiki proposal queue. Re-run with --yes to apply now."
        )
        return

    # Confirmed: re-run sync-config so modules.generated.yaml/.mcp.json/OWUI
    # presets never drift from the wiki's now-current state.
    from portal.platform.inference.sync_config import main as sync_config_main

    typer.echo("   Regenerating derived config (sync-config)...")
    sync_config_main()
