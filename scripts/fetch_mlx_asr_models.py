#!/usr/bin/env python3
"""Fetch the MLX ASR models the host audio services load (:8918 and :8924).

The services run with HF_HUB_OFFLINE=1 (scripts/native-mcp-service.sh), so this
is the only path by which their weights can appear. One-time and idempotent: a
model already cached is verified and skipped, a missing one is downloaded into
the same cache the services read.

    ./launch.sh pull-asr-models              # via the operator CLI
    python3 scripts/fetch_mlx_asr_models.py  # direct
    python3 scripts/fetch_mlx_asr_models.py --check   # verify only, no network

Model ids mirror the service defaults; the MLX_* env overrides (which an operator
may have repointed) take precedence so this fetches what the service will load.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# (service, env override, default model id) — three models, two services.
CATALOG: tuple[tuple[str, str, str], ...] = (
    ("mlx-transcribe :8924", "MLX_PARAKEET_MODEL", "mlx-community/parakeet-tdt-0.6b-v3"),
    ("mlx-transcribe :8924", "MLX_DIARIZE_MODEL", "mlx-community/diar_sortformer_4spk-v1-fp32"),
    ("mlx-speech :8918", "MLX_QWEN3_ASR", "mlx-community/Qwen3-ASR-1.7B-8bit"),
)
WEIGHT_SUFFIXES = (".safetensors", ".bin", ".npz", ".gguf", ".pt")


def cache_dir(override: str | None = None) -> Path:
    """The HF hub cache to download into — the one the services resolve."""
    if override:
        return Path(override).expanduser()
    for var in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        if os.getenv(var):
            return Path(os.environ[var]).expanduser()
    home = os.getenv("HF_HOME")
    if not home:
        xdg = os.getenv("XDG_CACHE_HOME", str(Path.home() / ".cache"))
        home = str(Path(xdg) / "huggingface")
    return Path(home).expanduser() / "hub"


def repo_dir(model_id: str, cache: Path) -> Path:
    return (
        Path(model_id)
        if os.path.isdir(model_id)
        else cache / f"models--{model_id.replace('/', '--')}"
    )


def verify_snapshot(snapshot: Path) -> tuple[bool, str]:
    """A snapshot is usable when it holds at least one non-empty weights file."""
    files = [p for p in snapshot.rglob("*") if p.is_file()]
    weights = [p for p in files if p.suffix in WEIGHT_SUFFIXES and p.stat().st_size > 0]
    total_mb = sum(p.stat().st_size for p in files) / 1e6
    if not weights:
        return False, f"no weights in {snapshot.name} ({len(files)} files, {total_mb:.1f} MB)"
    return True, f"{len(files)} files, {total_mb:.1f} MB"


def cached_snapshot(model_id: str, cache: Path) -> tuple[Path | None, str]:
    """Newest verified snapshot for the model, or (None, reason)."""
    if os.path.isdir(model_id):
        ok, detail = verify_snapshot(Path(model_id))
        return (Path(model_id), detail) if ok else (None, detail)
    snapshots = repo_dir(model_id, cache) / "snapshots"
    if not snapshots.is_dir():
        return None, f"not in {cache}"
    found = sorted((p for p in snapshots.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    detail = "no snapshot dirs"
    for snap in reversed(found):
        ok, detail = verify_snapshot(snap)
        if ok:
            return snap, detail
    return None, detail


def download(model_id: str, cache: Path) -> Path:
    """Snapshot-download into `cache`; HF_HUB_OFFLINE is cleared for this call only."""
    for var in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        os.environ.pop(var, None)
    from huggingface_hub import snapshot_download  # imported after the offline flags clear

    cache.mkdir(parents=True, exist_ok=True)
    return Path(snapshot_download(model_id, cache_dir=str(cache)))


def resolve_models(explicit: list[str]) -> list[tuple[str, str]]:
    if explicit:
        return [("explicit", m) for m in explicit]
    return [(service, os.getenv(var) or default) for service, var, default in CATALOG]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("models", nargs="*", help="model ids (default: the service defaults)")
    parser.add_argument("--check", action="store_true", help="verify only; never download")
    parser.add_argument("--cache-dir", default=None, help="HF hub cache (default: env/default)")
    args = parser.parse_args(argv)

    cache = cache_dir(args.cache_dir)
    print(f"HF hub cache: {cache}   (HF_HUB_OFFLINE={os.getenv('HF_HUB_OFFLINE', 'unset')})")
    failed = 0
    for service, model_id in resolve_models(args.models):
        snap, detail = cached_snapshot(model_id, cache)
        if snap is not None:
            print(f"  = {model_id} [{service}] already cached — {detail}")
            continue
        if args.check:
            print(f"  ✗ {model_id} [{service}] MISSING — {detail}")
            failed += 1
            continue
        print(f"  → {model_id} [{service}] downloading ({detail})...")
        try:
            path = download(model_id, cache)
        except Exception as e:  # noqa: BLE001 - report and keep going to the next model
            print(f"  ✗ {model_id} [{service}] download failed: {e}")
            failed += 1
            continue
        ok, detail = verify_snapshot(path)
        if ok:
            print(f"  ✓ {model_id} [{service}] — {detail} → {path}")
        else:
            print(f"  ✗ {model_id} [{service}] downloaded but unusable — {detail}")
            failed += 1

    if failed:
        print(f"✗ {failed} model(s) missing or unverifiable")
        return 1
    print("✓ all ASR models cached and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
