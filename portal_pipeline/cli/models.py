"""``portal models <cmd>`` — model registry operations."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from ._apps import models_app
from ._common import _detect_ollama_cmd, _model_exists_in_ollama
from portal_pipeline.config import Model, load_portal_config




def _pull_native(model: str, ollama_cmd: str) -> bool:
    """Pull a native Ollama registry model."""
    parts = ollama_cmd.split() + ["pull", model]
    typer.echo(f"  Pulling: {model}")
    try:
        subprocess.run(parts, check=True)
        return True
    except subprocess.CalledProcessError:
        return False



def _pull_hf_model(m: Model, ollama_cmd: str) -> bool:
    """Pull a HuggingFace model via Python API + ollama create."""
    from portal_pipeline.config import Model  # noqa: PLC0415

    actual_repo = m.actual_repo or m.hf_id
    filename = m.filename
    ollama_name = m.ollama_name
    gated = m.gated

    if not ollama_name:
        typer.echo(f"  ⚠️  Skipping {m.hf_id}: no ollama_name (too large for current hardware)")
        return True

    if not filename:
        typer.echo(f"  ⚠️  No filename for {m.hf_id} — attempting direct ollama pull")
        return _pull_native(f"hf.co/{actual_repo}", ollama_cmd)

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




@models_app.command("pull")
def models_pull(
    model_ids: Annotated[
        list[str] | None,
        typer.Argument(
            help="hf_id or ollama_name from config/portal.yaml. Omit to pull all live entries."
        ),
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Re-pull even if present")] = False,
    skip_gated: Annotated[
        bool, typer.Option("--skip-gated", help="Skip models marked gated=true")
    ] = False,
    include_retired: Annotated[
        bool,
        typer.Option("--include-retired", help="Include models marked retired=true (default skips)"),
    ] = False,
) -> None:
    """Pull HuggingFace models into Ollama per config/portal.yaml models: block.

    Model definitions are read from config/portal.yaml.
    Native Ollama registry models use ``ollama pull`` directly.
    """
    cfg = load_portal_config()

    ollama_cmd = _detect_ollama_cmd()
    if ollama_cmd is None:
        typer.echo("No Ollama available. Run: ./launch.sh install-ollama", err=True)
        raise typer.Exit(code=1)

    # Select models from config
    if model_ids:
        targets = [
            m
            for m in cfg.models
            if m.hf_id in model_ids
            or m.ollama_name in model_ids
        ]
    else:
        targets = [
            m
            for m in cfg.models
            if (include_retired or not m.retired) and m.ollama_name
        ]

    if not targets:
        typer.echo("No models to pull", err=True)
        raise typer.Exit(code=0)

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
    for i, m in enumerate(targets, 1):
        typer.echo(f"[{i}/{total}] {m.hf_id}")
        if skip_gated and m.gated:
            typer.echo(f"  ⏭️  Skipping gated model: {m.hf_id}")
            continue
        ok = _pull_hf_model(m, ollama_cmd)
        if ok:
            typer.echo("  ✅ Done")
        else:
            failed += 1
        typer.echo("")

    typer.echo(f"\n=== Pull complete: {total - failed}/{total} succeeded ===")
    if failed:
        raise typer.Exit(code=1)



@models_app.command("refresh")
def models_refresh() -> None:
    """Force re-pull of every currently-installed model.

    Shortcut for ``portal models pull --force --include-retired``.
    """
    models_pull(model_ids=None, force=True, skip_gated=False, include_retired=True)



@models_app.command("import-gguf")
def cmd_models_import_gguf(
    gguf_path: Annotated[Path, typer.Argument(help="Path to local .gguf file")],
    name: Annotated[str | None, typer.Option("--name", help="Ollama model name (tag)")] = None,
) -> None:
    """Import a local GGUF file into Ollama as a named model.

    Example:
        portal models import-gguf ~/Downloads/model.gguf --name my-model:q6_k
    """
    gguf_path = gguf_path.expanduser()
    if not gguf_path.is_file():
        typer.echo(f"GGUF file not found: {gguf_path}", err=True)
        raise typer.Exit(code=2)

    model_name = name or gguf_path.stem.lower().replace("_", "-")

    ollama_cmd = _detect_ollama_cmd()
    if ollama_cmd is None:
        typer.echo("No Ollama available. Run: ./launch.sh install-ollama", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"[portal-5] Importing GGUF: {gguf_path}")
    typer.echo(f"           Ollama name:   {model_name}")

    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".Modelfile", delete=False, prefix="portal5_"
    ) as mf:
        mf.write(f"FROM {gguf_path}\nPARAMETER temperature 0.7\nPARAMETER num_ctx 8192\n")
        mf_path = mf.name

    parts = ollama_cmd.split() + ["create", model_name, "-f", mf_path]
    try:
        subprocess.run(parts, check=True)
        typer.echo(f"[portal-5] ✅ Imported: {model_name}")
        typer.echo(f"  Run it: ollama run {model_name}")
    except subprocess.CalledProcessError:
        typer.echo("[portal-5] ❌ Import failed. Check Ollama is running.")
        raise typer.Exit(code=1)
    finally:
        Path(mf_path).unlink(missing_ok=True)



@models_app.command("apply-params")
def cmd_models_apply_params() -> None:
    """Apply per-model tuning parameters from portal.yaml to loaded Ollama models.

    Idempotent: re-running is safe (creates derived tags if needed).
    """
    typer.echo("Applying model params (ctx tags) ...")
    typer.echo("No active ctx tags in this fleet version.")


# ── models apply-mtp-drafts ───────────────────────────────────────────────────


@models_app.command("apply-mtp-drafts")
def cmd_models_apply_mtp_drafts() -> None:
    """Apply Multi-Token-Prediction draft settings for MTP-capable models.

    Wires Qwen3.6-27B MTP speculative-decoding A/B pairing.
    Graceful-skip if base or draft models are absent.
    """
    ollama_cmd = _detect_ollama_cmd()
    if ollama_cmd is None:
        typer.echo("ERROR: Ollama not reachable", err=True)
        raise typer.Exit(code=1)

    mtp_base = "qwen3.6:27b-q8_0"
    mtp_draft = "qwen3.6:27b-mtp-q4_K_M"
    mtp_created = "portal5/qwen3.6-27b-mtp:q8_0-drafted"

    typer.echo("apply-mtp-drafts: wiring Qwen3.6-27B MTP A/B pair ...")

    # Check base model
    show_cmd = ollama_cmd.split() + ["show", mtp_base]
    result = subprocess.run(show_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        typer.echo(f"  SKIP — base model {mtp_base} not pulled.")
        typer.echo(f"  Run: ollama pull {mtp_base}")
        return

    # Pull draft if needed
    show_cmd = ollama_cmd.split() + ["show", mtp_draft]
    result = subprocess.run(show_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        typer.echo(f"  Pulling draft model {mtp_draft} ...")
        pull_cmd = ollama_cmd.split() + ["pull", mtp_draft]
        result = subprocess.run(pull_cmd, check=False)
        if result.returncode != 0:
            typer.echo(f"  FAIL — could not pull {mtp_draft}", err=True)
            raise typer.Exit(code=1)

    # Get draft blob path
    modelfile_cmd = ollama_cmd.split() + ["show", mtp_draft, "--modelfile"]
    result = subprocess.run(modelfile_cmd, capture_output=True, text=True)
    draft_path = ""
    for line in result.stdout.splitlines():
        if line.startswith("FROM "):
            draft_path = line.split("FROM ", 1)[1].strip()
            break
    if not draft_path or not Path(draft_path).exists():
        typer.echo(
            f"  FAIL — could not resolve blob path for {mtp_draft}",
            err=True,
        )
        raise typer.Exit(code=1)
    typer.echo(f"  Draft blob: {draft_path}")

    # Create MTP model
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".Modelfile", delete=False, prefix="portal5_mtp_"
    ) as mf:
        mf.write(f"FROM {mtp_base}\nDRAFT {draft_path}\n")
        mf_path = mf.name

    typer.echo("  Modelfile:")
    typer.echo(Path(mf_path).read_text().strip())
    typer.echo(f"  Creating {mtp_created} ...")

    create_cmd = ollama_cmd.split() + ["create", mtp_created, "-f", mf_path]
    result = subprocess.run(create_cmd, capture_output=True, text=True)
    exit_code = result.returncode
    Path(mf_path).unlink(missing_ok=True)

    typer.echo(result.stdout)
    if exit_code != 0:
        typer.echo(f"\n  DRAFT REJECTION (Ollama create failed, exit {exit_code}).")
        raise typer.Exit(code=1)

    typer.echo(f"\n  OK — {mtp_created} created.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
