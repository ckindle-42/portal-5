"""``portal agent <cmd>`` — operator surface for the platform agent loop.

`explain` runs a single grounded decide-turn from a goal-spec YAML (dry, no
executor) so operators can see what the loop would try. `proposed` lists the
loop's pending wiki writebacks (the CI gate view). Running a full loop needs a
module-supplied Executor + provider (slice 2 wiring), so `run` is intentionally
a guarded stub that points at the API rather than faking a live engagement.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ._apps import agent_app


@agent_app.command("explain")
def agent_explain(
    goal_file: Path = typer.Argument(  # noqa: B008
        ..., help="Goal-spec YAML: intent/scope/budget/domain_hint"
    ),
) -> None:
    """Dry single decide-turn against the platform core (deterministic ranker)."""
    import yaml

    from portal.platform.agent import Goal, validate_goal

    spec = yaml.safe_load(goal_file.read_text()) or {}
    goal = Goal(
        intent=spec.get("intent", ""),
        scope=spec.get("scope", {}),
        budget=spec.get("budget", {}),
        stop_when=spec.get("stop_when"),
        domain_hint=spec.get("domain_hint"),
    )
    problems = validate_goal(goal)
    if problems:
        typer.echo("INVALID GOAL:")
        for p in problems:
            typer.echo(f"  - {p}")
        raise typer.Exit(code=1)

    provider_path = spec.get("provider")
    if not provider_path:
        typer.echo(
            "No `provider:` in goal spec. The decide-turn is grounded — it needs a "
            "module CapabilityProvider (e.g. security). Add `provider: <module>` once "
            "slice-2 provider registration lands."
        )
        raise typer.Exit(code=2)

    typer.echo(f"Goal validated. provider={provider_path} (wiring lands in slice 2).")


@agent_app.command("proposed")
def agent_proposed(
    status: str = typer.Option("proposed", "--status", help="proposed | confirmed | rejected"),
) -> None:
    """List agent-loop wiki writebacks awaiting the gate (confirm/reject)."""
    from portal.platform.wiki.writeback import list_proposed

    units = list(list_proposed(status=status))
    if not units:
        typer.echo(f"no units with status={status}")
        return
    for u in units:
        pid = getattr(u, "proposed_id", None) or getattr(u, "id", "?")
        typer.echo(f"{pid}  {getattr(u, 'title', '')}")
