"""``portal module <cmd>`` — module enable/disable operations (M7 toggle layer).

State lives in each unit-module-<name> wiki unit's fenced yaml `enabled:`
field (portal.platform.wiki.adapters.modules is the resolver, writeback_module is the
confirm-gated state-change path). After a state change, callers should run
``portal sync-config`` to regenerate .mcp.json and OWUI presets to match.
"""

from __future__ import annotations

import typer

from ._apps import module_app


@module_app.command("list")
def module_list() -> None:
    """List every module and whether it's currently enabled."""
    from portal.platform.wiki.adapters.modules import ALL_MODULES, enabled_modules

    enabled = set(enabled_modules())
    for mod in sorted(ALL_MODULES):
        state = "✅ enabled" if mod in enabled else "⛔ disabled"
        typer.echo(f"{mod:<15} {state}")


@module_app.command("enable")
def module_enable(
    name: str = typer.Argument(..., help="Module name, e.g. 'eval'"),
    actor: str = typer.Option("cli", "--actor", help="Who/what requested this change"),
) -> None:
    """Enable a module (proposes a wiki write-back)."""
    _set_module_state(name, True, actor)


@module_app.command("disable")
def module_disable(
    name: str = typer.Argument(..., help="Module name, e.g. 'eval'"),
    actor: str = typer.Option("cli", "--actor", help="Who/what requested this change"),
) -> None:
    """Disable a module (proposes a wiki write-back)."""
    _set_module_state(name, False, actor)


def _set_module_state(name: str, to_state: bool, actor: str) -> None:
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

    result = module_state_change(name, from_state=from_state, to_state=to_state, actor=actor)
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
    if status == "proposed":
        typer.echo("   Awaiting confirmation — see wiki proposal queue.")
    typer.echo("   Run `portal sync-config` to regenerate .mcp.json and OWUI presets.")
