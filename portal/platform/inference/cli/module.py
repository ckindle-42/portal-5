"""``portal module`` — enable or disable a module.

State is `config/portal.yaml` `modules.<name>.enabled`. ``--yes`` writes
that one line and re-runs sync-config. Wiki units are not modified.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

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
        _config_enabled_state,
        enabled_modules,
    )

    if name not in ALL_MODULES:
        typer.echo(f"❌ Unknown module: {name!r}. Known: {sorted(ALL_MODULES)}", err=True)
        raise typer.Exit(code=1)

    cfg = load_portal_config()
    config_state = _config_enabled_state(name)
    effective = name in enabled_modules()
    ws_ids = sorted(k for k, v in cfg.workspaces.items() if v.module == name)
    persona_slugs = sorted(p.slug for p in load_persona_map_safe().values() if p.module == name)
    mcp_ids = sorted(m.id for m in cfg.mcp_fleet if m.module == name)

    typer.echo(f"module:    {name}")
    typer.echo(f"enabled:   {effective}  (config modules.{name}: {config_state!r})")
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
    """Enable a module and start its services. --yes writes config/portal.yaml."""
    _set_module_state(name, True, actor, yes)


@module_app.command("disable")
def module_disable(
    name: str = typer.Argument(..., help="Module name, e.g. 'eval'"),
    actor: str = typer.Option("cli", "--actor", help="Who/what requested this change"),
    yes: bool = typer.Option(False, "--yes", help="Apply immediately, skip the confirm gate"),
) -> None:
    """Disable a module and stop its services. --yes writes config/portal.yaml."""
    _set_module_state(name, False, actor, yes)


@module_app.command("services")
def module_services_cmd(
    enabled: bool = typer.Option(False, "--enabled", help="List services of enabled modules"),
    disabled: bool = typer.Option(False, "--disabled", help="List services of disabled modules"),
    kind: str | None = typer.Option(None, "--kind", help="host or compose"),
    module: str | None = typer.Option(None, "--module", help="Limit to one module"),
    apply: bool = typer.Option(
        False, "--apply", help="Start enabled services and stop disabled ones"
    ),
    stop_only: bool = typer.Option(
        False, "--stop-only", help="With --apply, only stop disabled services"
    ),
    status: bool = typer.Option(False, "--status", help="Print module, config state, and runtime"),
) -> None:
    """Print or apply the module→service map (one ident per line)."""
    from portal.platform.inference.cli.module_services import run_services_cli

    run_services_cli(
        enabled=enabled,
        disabled=disabled,
        kind=kind,
        module=module,
        apply=apply,
        stop_only=stop_only,
        status=status,
    )


def load_persona_map_safe() -> dict[str, Any]:
    """load_persona_map() with the default personas dir — thin wrapper so
    module_list/module_status don't each repeat the import."""
    from portal.platform.inference.config import load_persona_map

    return load_persona_map()


def _modules_region(text: str) -> tuple[int, int]:
    marker = "\nmodules:\n"
    start = text.find(marker)
    if start < 0:
        raise ValueError("config/portal.yaml has no modules: block")
    body = start + len(marker)
    nxt = re.search(r"\n(?=[A-Za-z])", text[body:])
    end = body + nxt.start() if nxt else len(text)
    return body, end


def write_module_enabled(name: str, enabled: bool, path: Path | None = None) -> None:
    """Flip the one `modules.<name>.enabled` line. Does not touch the wiki."""
    from portal.platform.inference import config as cfg

    target = path or cfg.PORTAL_YAML
    text = target.read_text(encoding="utf-8")
    body, end = _modules_region(text)
    block = text[body:end]
    value = "true" if enabled else "false"
    pat = re.compile(rf"(^  {re.escape(name)}:\n    enabled: )(true|false)\s*$", re.M)
    new_block, n = pat.subn(rf"\g<1>{value}", block, count=1)
    if n != 1:
        raise ValueError(f"modules.{name}.enabled not found in {target}")
    target.write_text(text[:body] + new_block + text[end:], encoding="utf-8")
    cfg._CONFIG_CACHE.clear()


def _set_module_state(name: str, to_state: bool, actor: str, auto_confirm: bool) -> None:
    from portal.platform.wiki.adapters.modules import ALL_MODULES, enabled_modules

    if name not in ALL_MODULES:
        typer.echo(f"❌ Unknown module: {name!r}. Known: {sorted(ALL_MODULES)}", err=True)
        raise typer.Exit(code=1)

    from_state = name in enabled_modules()
    verb = "enabled" if to_state else "disabled"
    if from_state == to_state:
        typer.echo(f"'{name}' is already {verb}.")
    elif not auto_confirm:
        typer.echo(
            f"'{name}' would be {verb} (requested by {actor}). "
            "Re-run with --yes to write config/portal.yaml."
        )
        return
    else:
        try:
            write_module_enabled(name, to_state)
        except ValueError as exc:
            typer.echo(f"❌ {exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"✅ '{name}' {verb}.")
        from portal.platform.inference.sync_config import main as sync_config_main

        typer.echo("   Regenerating derived config (sync-config)...")
        sync_config_main()
    from portal.platform.inference.cli.module_services import apply_module

    for note in apply_module(name, start=to_state):
        typer.echo(f"   {note}")
