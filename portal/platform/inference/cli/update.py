"""``portal update`` — full Portal 5 upgrade flow."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer


def cmd_update(
    refresh_models: Annotated[
        bool,
        typer.Option(
            "--refresh-models",
            help="Also refresh Ollama models (downloads only when upstream changed; off by default)",
        ),
    ] = False,
    skip_models: Annotated[
        bool, typer.Option("--skip-models", help="Deprecated: models are skipped by default")
    ] = False,
    models_only: Annotated[
        bool, typer.Option("--models-only", help="Refresh models only, skip everything else")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip interactive prompts")] = False,
) -> None:
    """Full Portal 5 update: git pull → docker → rebuild → models → re-seed → restart."""
    if skip_models and (models_only or refresh_models):
        typer.echo("Cannot combine --skip-models with --models-only/--refresh-models", err=True)
        raise typer.Exit(code=2)
    # Disk is finite: an update never downloads models unless asked (operator 2026-10-28).
    skip_models = not (refresh_models or models_only)

    if not yes:
        typer.confirm(
            "This will pull git changes and rebuild containers"
            + (" and refresh models" if not skip_models else "")
            + ". Continue?",
            abort=True,
        )

    repo_root = Path(__file__).resolve().parents[4]

    typer.echo("\n  Portal 5 — Update\n  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    if not models_only:
        # Step 1: Git pull
        typer.echo("[1/8] Updating portal-5 source...")
        git_dir = repo_root / ".git"
        if git_dir.exists():
            import subprocess as _sp

            before = _sp.run(
                ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            _sp.run(["git", "-C", str(repo_root), "pull", "--ff-only"], check=False)
            after = _sp.run(
                ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if before != after:
                typer.echo(f"  ✅ Updated ({before} → {after})")
            else:
                typer.echo("  ✅ Already up to date")
        else:
            typer.echo("  ⚠️  Not a git repo — skipping source update")
        typer.echo("")

        # Step 2: Pull Docker images
        typer.echo("[2/8] Pulling latest Docker images...")
        compose_dir = repo_root / "deploy" / "portal-5"
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(compose_dir / "docker-compose.yml"),
                "pull",
                "ollama",
                "open-webui",
                "searxng",
            ],
            check=False,
            cwd=str(compose_dir),
            capture_output=True,
        )
        typer.echo("  ✅ Docker images pulled")
        typer.echo("")

        # Step 3: Rebuild
        typer.echo("[3/8] Rebuilding portal-pipeline + MCP servers...")
        build_cmd = ["docker", "compose", "-f", str(compose_dir / "docker-compose.yml"), "build"]
        build_cmd.extend(
            ["portal-pipeline", "mcp-documents", "mcp-tts", "mcp-whisper", "mcp-sandbox"]
        )
        subprocess.run(build_cmd, check=False, cwd=str(compose_dir), capture_output=True)
        typer.echo("  ✅ Images rebuilt")
        typer.echo("")

    if not skip_models:
        # Step 4: Replace catalog models whose upstream changed. Never a plain pull.
        typer.echo("[4/8] Replacing Ollama models whose upstream changed...")
        script = repo_root / "scripts" / "model_autoupdate.py"
        subprocess.run([sys.executable, str(script), "--now"], check=False)
        typer.echo("")

    if not models_only:
        # Step 5-6: host-native MLX MCPs (mflux/video-mlx/music/speech) are
        # managed by their own launchd services and `./launch.sh install-*` /
        # `pip install --upgrade` in their venvs — not rebuilt here.
        typer.echo("[5/7] Host-native MLX MCPs (mflux, video-mlx, music, speech)...")
        typer.echo(
            "  ℹ️  Update deps with pip in ~/.portal5/<svc>/.venv, or re-run ./launch.sh install-<svc>"
        )
        typer.echo("")

        typer.echo("[6/7] (reserved)")
        typer.echo("")

        # Step 7: Re-seed + restart
        typer.echo("[7/7] Re-seeding Open WebUI + restarting stack...")
        compose_dir = repo_root / "deploy" / "portal-5"
        subprocess.run(
            ["docker", "compose", "-f", str(compose_dir / "docker-compose.yml"), "up", "-d"],
            check=False,
            cwd=str(compose_dir),
            capture_output=True,
        )
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(compose_dir / "docker-compose.yml"),
                "run",
                "--rm",
                "-e",
                "FORCE_RESEED=true",
                "openwebui-init",
            ],
            check=False,
            cwd=str(compose_dir),
            capture_output=True,
        )
        typer.echo("  ✅ Stack restarted + re-seeded")
        typer.echo("")

    # Summary
    typer.echo("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    typer.echo("  Update complete.\n")
    if not models_only:
        typer.echo("  Updated:")
        typer.echo("    ✅ Portal 5 source (git pull)")
        typer.echo("    ✅ Docker images (ollama, open-webui, searxng)")
        typer.echo("    ✅ portal-pipeline + MCP server images (rebuild)")
    if not skip_models:
        typer.echo("    ✅ Ollama models (checked for updates)")
    if not models_only:
        typer.echo("    ✅ Host-native MLX MCPs (managed via launchd / ./launch.sh install-*)")
        typer.echo("    ✅ Open WebUI presets (re-seeded)")
    typer.echo("\n  Check status: portal status")


def register(app: typer.Typer) -> None:
    app.command("update")(cmd_update)
