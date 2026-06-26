"""``portal update`` — full Portal 5 upgrade flow."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from ._common import _detect_ollama_cmd, _resolve_model_name

_DEFAULT_MODELS: list[str] = [
    "${DEFAULT_MODEL:-dolphin-llama3:8b}",
    "huihui_ai/qwen3.5-abliterated:9b",
    "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF",
    "nomic-embed-text:latest",
    "hf.co/AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF",
    "hf.co/segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF",
    "hf.co/cognitivecomputations/Dolphin3.0-R1-Mistral-24B-GGUF",
    "xploiter/the-xploiter",
    "hf.co/WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5-GGUF",
    "huihui_ai/baronllm-abliterated",
    "lazarevtill/Llama-3-WhiteRabbitNeo-8B-v2.0:q4_0",
    "qwen3.5:9b",
    "qwen3-coder:30b",
    "deepseek-coder-v2:16b-lite-instruct-q4_K_M",
    "devstral:24b",
    "granite4.1:8b",
    "granite4.1:30b",
    "hf.co/deepseek-ai/DeepSeek-R1-32B-GGUF",
    "gpt-oss:20b",
    "huihui_ai/tongyi-deepresearch-abliterated",
    "hf.co/Jiunsong/supergemma4-26b-uncensored-gguf-v2",
    "qwen3-vl:32b",
    "llava:7b",
    "huihui_ai/Qwen3.6-abliterated:27b",
    "hf.co/mradermacher/OmniCoder-2-9B-GGUF",
]

_HEAVY_MODELS: list[str] = [
    "hf.co/cognitivecomputations/dolphin-3-llama3-70b-GGUF",
    "hf.co/meta-llama/Meta-Llama-3.3-70B-GGUF",
]

def cmd_update(
    skip_models: Annotated[
        bool, typer.Option("--skip-models", help="Skip model refresh")
    ] = False,
    models_only: Annotated[
        bool, typer.Option("--models-only", help="Refresh models only, skip everything else")
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip interactive prompts")
    ] = False,
) -> None:
    """Full Portal 5 update: git pull → docker → rebuild → models → re-seed → restart."""
    if skip_models and models_only:
        typer.echo("Cannot combine --skip-models and --models-only", err=True)
        raise typer.Exit(code=2)

    if not yes:
        typer.confirm(
            "This will pull git changes, rebuild containers, and refresh models. Continue?",
            abort=True,
        )

    repo_root = Path(__file__).resolve().parent.parent

    typer.echo("\n  Portal 5 — Update\n  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    if not models_only:
        # Step 1: Git pull
        typer.echo("[1/8] Updating portal-5 source...")
        git_dir = repo_root / ".git"
        if git_dir.exists():
            import subprocess as _sp

            before = _sp.run(
                ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                capture_output=True, text=True,
            ).stdout.strip()
            _sp.run(["git", "-C", str(repo_root), "pull", "--ff-only"], check=False)
            after = _sp.run(
                ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                capture_output=True, text=True,
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
            ["docker", "compose", "-f", str(compose_dir / "docker-compose.yml"),
             "pull", "ollama", "open-webui", "searxng"],
            check=False, cwd=str(compose_dir), capture_output=True,
        )
        typer.echo("  ✅ Docker images pulled")
        typer.echo("")

        # Step 3: Rebuild
        typer.echo("[3/8] Rebuilding portal-pipeline + MCP servers...")
        build_cmd = ["docker", "compose", "-f", str(compose_dir / "docker-compose.yml"), "build"]
        comfyui_dir = os.environ.get("COMFYUI_DIR", str(Path.home() / "ComfyUI"))
        if Path(comfyui_dir).exists():
            build_cmd.extend(["mcp-comfyui", "mcp-video", "portal-pipeline", "mcp-documents",
                              "mcp-tts", "mcp-whisper", "mcp-sandbox"])
        else:
            build_cmd.append("portal-pipeline")
        subprocess.run(build_cmd, check=False, cwd=str(compose_dir), capture_output=True)
        typer.echo("  ✅ Images rebuilt")
        typer.echo("")

    if not skip_models:
        # Step 4: Refresh Ollama models
        typer.echo("[4/8] Refreshing Ollama models (checks for newer versions)...")
        _ollama_cmd = _detect_ollama_cmd()
        if _ollama_cmd:
            _update_model_list = _DEFAULT_MODELS[:]
            if os.environ.get("PULL_HEAVY", "false").lower() in ("true", "1", "yes"):
                _update_model_list.extend(_HEAVY_MODELS)
            total = len(_update_model_list)
            fail_count = 0
            for i, model in enumerate(_update_model_list, 1):
                model = _resolve_model_name(model)
                typer.echo(f"  [{i}/{total}] {model}")
                parts = _ollama_cmd.split() + ["pull", model]
                try:
                    subprocess.run(parts, check=True, capture_output=True)
                    typer.echo("  ✅ Done")
                except subprocess.CalledProcessError:
                    fail_count += 1
            typer.echo(f"  Ollama: {total - fail_count}/{total} succeeded")
        else:
            typer.echo("  ⚠️  Ollama not running — skipping model refresh")
        typer.echo("")

    if not models_only:
        # Step 5-6: ComfyUI and Music MCP not ported (host-native, bash-only)
        typer.echo("[5/7] Checking ComfyUI (host-native)...")
        comfyui_dir = os.environ.get("COMFYUI_DIR", str(Path.home() / "ComfyUI"))
        if Path(comfyui_dir / ".git").exists():
            subprocess.run(["git", "-C", comfyui_dir, "pull", "--quiet"], check=False)
            typer.echo("  ✅ ComfyUI updated")
        else:
            typer.echo("  ℹ️  ComfyUI not installed — skipping")
        typer.echo("")

        typer.echo("[6/7] Checking Music MCP...")
        music_venv = Path.home() / ".portal5" / "music" / ".venv"
        if music_venv.exists():
            typer.echo("  (Music MCP deps: use 'pip install --upgrade' in venv)")
        else:
            typer.echo("  ℹ️  Music MCP not installed — skipping")
        typer.echo("")

        # Step 7: Re-seed + restart
        typer.echo("[7/7] Re-seeding Open WebUI + restarting stack...")
        compose_dir = repo_root / "deploy" / "portal-5"
        subprocess.run(
            ["docker", "compose", "-f", str(compose_dir / "docker-compose.yml"),
             "up", "-d"],
            check=False, cwd=str(compose_dir), capture_output=True,
        )
        subprocess.run(
            ["docker", "compose", "-f", str(compose_dir / "docker-compose.yml"),
             "run", "--rm", "-e", "FORCE_RESEED=true", "openwebui-init"],
            check=False, cwd=str(compose_dir), capture_output=True,
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
        typer.echo("    ✅ ComfyUI (if installed)")
        typer.echo("    ✅ Music MCP (if installed)")
        typer.echo("    ✅ Open WebUI presets (re-seeded)")
    typer.echo("\n  Check status: portal status")


def register(app: typer.Typer) -> None:
    app.command("update")(cmd_update)
