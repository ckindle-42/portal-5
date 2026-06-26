"""portal CLI — typed entry point for Portal 5 operator commands.

Stage 2 of M5: high-logic commands from launch.sh are ported here one by one;
launch.sh delegates to ``portal <cmd>`` so there is one implementation.

Currently implemented:
- ``portal config show``       — print the resolved portal.yaml config as JSON
- ``portal sync-config``       — regenerate derived artifacts from portal.yaml
- ``portal workspace init``    — initialize $AI_OUTPUT_DIR structure
- ``portal workspace status``  — print workspace paths, sizes, file counts
- ``portal workspace show``    — show workspace mount paths
- ``portal models pull``       — pull models from Ollama/HuggingFace registry
- ``portal models refresh``    — force re-pull all installed models

Usage:
    portal --help
    portal config show
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from portal_pipeline.config import load_portal_config

app = typer.Typer(
    name="portal",
    help="Portal 5 operator CLI — typed commands over the portal.yaml config.",
    no_args_is_help=True,
)

# ── Config sub-app ────────────────────────────────────────────────────────────

config_app = typer.Typer(help="Config introspection commands.")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show(
    raw: Annotated[bool, typer.Option("--raw", help="Emit raw YAML values (no env override)")] = False,
) -> None:
    """Print the resolved portal.yaml config as pretty-printed JSON."""
    cfg = load_portal_config()
    data = {
        "ollama_url": cfg.ollama_url,
        "request_timeout": cfg.request_timeout,
        "workspaces": list(cfg.workspaces.keys()),
        "workspace_count": len(cfg.workspaces),
        "mcp_fleet_count": len(cfg.mcp_fleet),
        "mcp_fleet": [
            {
                "id": s.id,
                "name": s.name,
                "port": s.port,
                "expose_to_pipeline": s.expose_to_pipeline,
            }
            for s in cfg.mcp_fleet
        ],
    }
    typer.echo(json.dumps(data, indent=2))


# ── sync-config ───────────────────────────────────────────────────────────────


@app.command("sync-config")
def sync_config(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would change without writing")
    ] = False,
) -> None:
    """Regenerate derived artifacts from config/portal.yaml.

    Produces:
      config/backends.yaml workspace_routing block
      .mcp.json (Claude Code MCP list)
      imports/openwebui/workspaces/workspace_*.json

    Idempotent — safe to run after every edit to portal.yaml.
    """
    from portal_pipeline.sync_config import main as _sync_main

    if dry_run:
        typer.echo("sync-config: --dry-run (not yet implemented in sync_config)")
        typer.echo("  Run without --dry-run to apply changes.")
        raise typer.Exit(code=0)

    sys.exit(_sync_main())


# ── Workspace sub-app ─────────────────────────────────────────────────────────

workspace_app = typer.Typer(help="Workspace operations.")
app.add_typer(workspace_app, name="workspace")


@workspace_app.command("init")
def workspace_init() -> None:
    """Initialize ${AI_OUTPUT_DIR} structure (uploads + generated/*)."""
    ws_root = Path(os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))
    subdirs = [
        "uploads",
        "generated/transcripts",
        "generated/documents",
        "generated/images",
        "generated/videos",
        "generated/music",
        "generated/speech",
    ]
    for sub in subdirs:
        (ws_root / sub).mkdir(parents=True, exist_ok=True)
    try:
        ws_root.chmod(0o775)
    except OSError:
        pass
    typer.echo(f"✅ Workspace structure created")
    typer.echo(f"   {ws_root}/")
    for sub in subdirs:
        typer.echo(f"   {ws_root / sub}/")


@workspace_app.command("status")
def workspace_status() -> None:
    """Print workspace state — paths, sizes, file counts."""
    ws_root = Path(os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))
    if not ws_root.exists():
        typer.echo(f"❌ Workspace not initialized at: {ws_root}", err=True)
        typer.echo("   Run: portal workspace init", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Workspace: {ws_root}")
    typer.echo("")
    typer.echo(f"{'Path':<30} {'Files':>10} {'Size':>10}")
    typer.echo(f"{'─'*30} {'─'*10} {'─'*10}")

    dirs = [
        "uploads",
        "generated/transcripts",
        "generated/documents",
        "generated/images",
        "generated/videos",
        "generated/music",
        "generated/speech",
    ]
    for d in dirs:
        dp = ws_root / d
        if dp.exists():
            n = sum(1 for _ in dp.rglob("*") if _.is_file())
            s = sum(_.stat().st_size for _ in dp.rglob("*") if _.is_file())
            s_str = _fmt_size(s)
            typer.echo(f"{d:<30} {n:>10} {s_str:>10}")
    typer.echo("")

    total_s = sum(
        _.stat().st_size for _ in ws_root.rglob("*") if _.is_file()
    )
    typer.echo(f"Total: {_fmt_size(total_s)}")


@workspace_app.command("show")
def workspace_show() -> None:
    """Show workspace mount paths (host + container)."""
    ws_root = Path(os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))
    typer.echo(f"Workspace root (host):     {ws_root}")
    typer.echo("Workspace root (container): /workspace")
    typer.echo(f"OWUI uploads (host):       {ws_root / 'uploads'}/")
    typer.echo("OWUI uploads (container):  /app/backend/data/uploads/")
    typer.echo("")
    typer.echo("Generated subdirs:")
    for cat in ["transcripts", "documents", "images", "videos", "music", "speech"]:
        typer.echo(f"  {cat}: {ws_root / 'generated' / cat}/")


# ── Models sub-app ────────────────────────────────────────────────────────────

models_app = typer.Typer(help="Model registry operations.")
app.add_typer(models_app, name="models")


# ── HuggingFace model registry ────────────────────────────────────────────────
# Ported from scripts/lib/models.sh case statements. Migrate to portal.yaml
# when the model registry schema lands (M5 follow-up).
_HF_MODEL_SPECS: dict[str, dict] = {
    "AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF": {
        "actual_repo": "AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF",
        "filename": "baronllm-llama3.1-v1-q6_k.gguf",
        "ollama_name": "baronllm:q6_k",
        "gated": True,
    },
    "segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF": {
        "actual_repo": "segolilylabs/Lily-Cybersecurity-7B-v0.2-GGUF",
        "filename": "Lily-7B-Instruct-v0.2.Q4_K_M.gguf",
        "ollama_name": "lily-cybersecurity:7b-q4_k_m",
    },
    "cognitivecomputations/Dolphin3.0-R1-Mistral-24B-GGUF": {
        "actual_repo": "bartowski/cognitivecomputations_Dolphin3.0-R1-Mistral-24B-GGUF",
        "filename": "cognitivecomputations_Dolphin3.0-R1-Mistral-24B-Q4_K_M.gguf",
        "ollama_name": "dolphin3-r1-mistral:24b-q4_k_m",
    },
    "WhiteRabbitNeo/WhiteRabbitNeo-33B-v1.5-GGUF": {
        "actual_repo": "dranger003/WhiteRabbitNeo-33B-v1.5-iMat.GGUF",
        "filename": "ggml-whiterabbitneo-33b-v1.5-q4_k_m.gguf",
        "ollama_name": "whiterabbitneo:33b-v1.5-q4_k_m",
    },
    "mradermacher/OmniCoder-2-9B-GGUF": {
        "actual_repo": "mradermacher/OmniCoder-2-9B-GGUF",
        "filename": "OmniCoder-2-9B.Q4_K_M.gguf",
        "ollama_name": "omnicoder2:9b-q4_k_m",
    },
    "MiniMaxAI/MiniMax-M2.1-GGUF": {
        "actual_repo": "bartowski/MiniMaxAI_MiniMax-M2.1-GGUF",
        "filename": "MiniMaxAI_MiniMax-M2.1-Q4_K_M.gguf",
        "ollama_name": "",
        "skip_reason": "138 GB at Q4_K_M — requires ~160 GB RAM; skip by default",
    },
    "deepseek-ai/DeepSeek-R1-32B-GGUF": {
        "actual_repo": "bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF",
        "filename": "DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf",
        "ollama_name": "deepseek-r1:32b-q4_k_m",
    },
    "Jiunsong/supergemma4-26b-uncensored-gguf-v2": {
        "actual_repo": "Jiunsong/supergemma4-26b-uncensored-gguf-v2",
        "filename": "supergemma4-26b-uncensored-fast-v2-Q4_K_M.gguf",
        "ollama_name": "supergemma4-26b-uncensored:q4_k_m",
    },
    "cognitivecomputations/dolphin-3-llama3-70b-GGUF": {
        "actual_repo": "bartowski/dolphin-2.9.1-llama3-70b-GGUF",
        "filename": "dolphin-2.9.1-llama-3-70b-Q4_K_M.gguf",
        "ollama_name": "dolphin-llama3:70b-q4_k_m",
    },
    "meta-llama/Meta-Llama-3.3-70B-GGUF": {
        "actual_repo": "bartowski/Llama-3.3-70B-Instruct-GGUF",
        "filename": "Llama-3.3-70B-Instruct-Q4_K_M.gguf",
        "ollama_name": "llama3.3:70b-q4_k_m",
    },
}

# Default model list for pull-all (mirrors MODELS array in models.sh)
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


def _detect_ollama_cmd() -> str | None:
    """Return the ollama command to use (native or docker exec), or None."""
    # Check native Ollama
    import urllib.request as _ur

    try:
        r = _ur.urlopen("http://localhost:11434/api/tags", timeout=3)
        r.close()
        if subprocess.run(["which", "ollama"], capture_output=True).returncode == 0:
            return "ollama"
    except Exception:
        pass
    # Check Docker Ollama
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5,
        )
        if "portal5-ollama" in result.stdout:
            return "docker exec portal5-ollama ollama"
    except Exception:
        pass
    return None


def _model_exists_in_ollama(model_name: str, ollama_cmd: str) -> bool:
    """Check if a model is already loaded in Ollama."""
    parts = ollama_cmd.split() + ["list"]
    try:
        result = subprocess.run(parts, capture_output=True, text=True, timeout=10)
        for line in result.stdout.lower().splitlines():
            if model_name.lower() in line:
                return True
    except Exception:
        pass
    return False


def _pull_native(model: str, ollama_cmd: str) -> bool:
    """Pull a native Ollama registry model."""
    parts = ollama_cmd.split() + ["pull", model]
    typer.echo(f"  Pulling: {model}")
    try:
        subprocess.run(parts, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _pull_hf_model(repo_id: str, ollama_cmd: str) -> bool:
    """Pull a HuggingFace model via Python API + ollama create."""
    spec = _HF_MODEL_SPECS.get(repo_id)
    if spec is None:
        typer.echo(f"  ⚠️  No verified spec for {repo_id} — attempting direct ollama pull")
        return _pull_native(f"hf.co/{repo_id}", ollama_cmd)

    if spec.get("skip_reason"):
        typer.echo(f"  ⚠️  Skipping {repo_id}: {spec['skip_reason']}")
        return True  # Not a failure

    ollama_name = spec["ollama_name"]
    actual_repo = spec["actual_repo"]
    filename = spec["filename"]
    gated = spec.get("gated", False)

    # Check if already in Ollama
    if _model_exists_in_ollama(ollama_name, ollama_cmd):
        typer.echo(f"  ✅ Already in Ollama as {ollama_name} — skipping")
        return True

    # Token check for gated repos
    if gated and not os.environ.get("HF_TOKEN"):
        typer.echo(f"  ❌ {actual_repo} requires HF_TOKEN (gated repo)")
        typer.echo(f"     1. Accept terms: https://huggingface.co/{actual_repo}")
        typer.echo("     2. Create token: https://huggingface.co/settings/tokens")
        typer.echo("     3. Add to .env:  HF_TOKEN=hf_...")
        return False

    # Download via Python
    try:
        from huggingface_hub import hf_hub_download  # noqa: PLC0415
    except ImportError:
        typer.echo("  Installing huggingface_hub...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "huggingface_hub>=0.28", "--quiet"],
            check=True,
        )

    typer.echo(f"  Fetching from HuggingFace: {actual_repo}")
    typer.echo(f"  File: {filename}")

    token = os.environ.get("HF_TOKEN") or None
    try:
        from huggingface_hub import hf_hub_download  # noqa: PLC0415

        gguf_path = hf_hub_download(
            repo_id=actual_repo,
            filename=filename,
            token=token,
        )
    except Exception as e:
        typer.echo(f"  ❌ Download failed: {e}")
        typer.echo(f"     Retry manually:")
        typer.echo(f"       hf hub download {actual_repo} {filename}")
        typer.echo(f"     Then import: ./launch.sh import-gguf <path> {ollama_name}")
        return False

    if not gguf_path or not Path(gguf_path).exists():
        typer.echo(f"  ❌ Download failed — file not found after download")
        return False

    typer.echo(f"  ✅ Ready: {Path(gguf_path).name}")

    # Import via ollama create
    typer.echo(f"  Importing as: {ollama_name}")
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".modelfile", delete=False
    ) as mf:
        mf.write(f"FROM {gguf_path}\nPARAMETER temperature 0.7\nPARAMETER num_ctx 8192\n")
        modelfile_path = mf.name

    try:
        parts = ollama_cmd.split() + ["create", ollama_name, "-f", modelfile_path]
        subprocess.run(parts, check=True)
        typer.echo(f"  ✅ Imported: {ollama_name}")
        return True
    except subprocess.CalledProcessError:
        typer.echo(f"  ❌ ollama create failed — GGUF kept at: {gguf_path}")
        return False
    finally:
        Path(modelfile_path).unlink(missing_ok=True)


def _resolve_model_name(raw: str) -> str:
    """Resolve ${VAR:-default} env var references in model names."""
    import re as _re

    def _repl(m):
        var, default = m.group(1), m.group(2)
        return os.environ.get(var, default)

    return _re.sub(r"\$\{(\w+):-([^}]+)\}", _repl, raw)


@models_app.command("pull")
def models_pull(
    model_ids: Annotated[
        list[str] | None,
        typer.Argument(help="Model IDs to pull. Omit to pull all default models."),
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Re-pull even if present")] = False,
    skip_gated: Annotated[
        bool, typer.Option("--skip-gated", help="Skip models marked gated=true")
    ] = False,
) -> None:
    """Pull models from HuggingFace or Ollama registry into Ollama.

    Model definitions for hf.co/ repos are read from the built-in registry.
    Native Ollama registry models use ``ollama pull`` directly.

    Without arguments, pulls all default models.
    """
    ollama_cmd = _detect_ollama_cmd()
    if ollama_cmd is None:
        typer.echo("No Ollama available. Run: ./launch.sh install-ollama", err=True)
        raise typer.Exit(code=1)

    # Resolve model list
    targets = model_ids or _DEFAULT_MODELS
    targets = [_resolve_model_name(m) for m in targets]

    typer.echo("=== Portal 5: Pulling AI models ===")
    typer.echo("This may take 30-90 minutes depending on connection speed.\n")
    typer.echo(
        "[portal-5] HuggingFace models: using hf hub download "
        "(bypasses Ollama auth issues)"
    )
    typer.echo(
        "   For gated models, first accept terms at huggingface.co"
        " then set HF_TOKEN in .env\n"
    )

    total = len(targets)
    failed = 0
    for i, model in enumerate(targets, 1):
        typer.echo(f"[{i}/{total}] {model}")
        ok = _pull_one(model, ollama_cmd, force=force, skip_gated=skip_gated)
        if ok:
            typer.echo("  ✅ Done")
        else:
            failed += 1
        typer.echo("")

    # Heavy models
    if os.environ.get("PULL_HEAVY", "false").lower() in ("true", "1", "yes"):
        typer.echo("Pulling heavy 70B models (PULL_HEAVY=true)...")
        for model in _HEAVY_MODELS:
            typer.echo(f"  Pulling: {model} (~35GB)")
            ok = _pull_one(model, ollama_cmd, force=force, skip_gated=skip_gated)
            typer.echo("  ✅ Done" if ok else "  ❌ Failed")
            if not ok:
                failed += 1
    else:
        typer.echo(
            "Skipping 70B models (set PULL_HEAVY=true in .env to pull ~35GB models)"
        )
        for m in _HEAVY_MODELS:
            typer.echo(f"  - {m}")

    typer.echo(f"\n=== Pull complete: {total - failed}/{total} succeeded ===")

    if failed:
        raise typer.Exit(code=1)


def _pull_one(model: str, ollama_cmd: str, *, force: bool = False, skip_gated: bool = False) -> bool:
    """Pull a single model. Returns True on success."""
    if model.startswith("hf.co/"):
        repo_id = model[len("hf.co/"):]
        spec = _HF_MODEL_SPECS.get(repo_id, {})
        if skip_gated and spec.get("gated"):
            typer.echo(f"  ⏭️  Skipping gated model: {repo_id}")
            return True  # Not a failure
        return _pull_hf_model(repo_id, ollama_cmd)
    else:
        return _pull_native(model, ollama_cmd)


@models_app.command("refresh")
def models_refresh() -> None:
    """Force re-pull of every currently-installed model.

    Shortcut for ``portal models pull --force`` on the full default model list.
    """
    models_pull(model_ids=None, force=True, skip_gated=False)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _fmt_size(size: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}P"


def main() -> None:
    app()


if __name__ == "__main__":
    main()
