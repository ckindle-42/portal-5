#!/usr/bin/env python3
"""Install helper for the media variant screen: candidate venvs and weights.

Apple-silicon only (CLAUDE.md rule 14) and data01-first: weight downloads run with
HF_HUB_CACHE=/Volumes/data01/hf-cache and unpack under the catalog's weights_root
(/Volumes/data01/media-screen). Hugging Face API sizes print before anything downloads.
Without --yes it prints the plan and sizes and stops; with it, steps run idempotently —
existing artifacts are left alone.

    uv run python scripts/proofs/media_variant_screen_install.py --medium video --yes
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from media_variant_screen import GIB  # noqa: E402

_CATALOG = yaml.safe_load((_HERE / "media_screen_catalog.yaml").read_text())
PINS = _CATALOG["pins"]
PATHS = {k: Path(v).expanduser() for k, v in _CATALOG["paths"].items()}
WEIGHT_REPOS = (
    ("FastVideo/FastMetal-1.3B-QAD", "FastMetal-1.3B-QAD"),
    ("FastVideo/FastMetal-5B-QAD", "FastMetal-5B-QAD"),
)
LM_REPO = "ACE-Step/acestep-5Hz-lm-0.6B"
SIZE_REPOS = (
    (
        "FLUX.2 klein 4B (incumbent repo; already cached on this host)",
        "black-forest-labs/FLUX.2-klein-4B",
    ),
    (
        "Iris-3B repo (holds turbo AND base; first generate downloads the turbo transformer"
        " ~5.6 GB + Qwen3-VL-4B TE ~8.2 GB per the mflux README)",
        "speridlabs/iris-3b",
    ),
)


def hf_size_gb(repo_id: str) -> float | None:
    """Total file bytes of a HF repo from the public API; None when unreachable."""
    url = f"https://huggingface.co/api/models/{repo_id}?blobs=true"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            payload = json.load(resp)
    except (OSError, ValueError):
        return None
    total = sum(int(s.get("size") or 0) for s in payload.get("siblings") or [])
    return total / GIB if total else None


def _print_sizes(entries: tuple[tuple[str, str], ...]) -> None:
    for label, repo in entries:
        size = hf_size_gb(repo)
        shown = f"{size:.2f} GB repo total" if size is not None else "size unavailable (HF API)"
        print(f"[sizes] {label}: {repo} — {shown}")


def _need_apple_silicon() -> None:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise SystemExit("media screen installs are arm64 macOS only (CLAUDE.md rule 14); aborting")


def _run(argv: list[str], cwd: Path | None = None, env_extra: dict[str, str] | None = None) -> int:
    print(f"$ {shlex.join(str(a) for a in argv)}" + (f"  # cwd={cwd}" if cwd else ""))
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run([str(a) for a in argv], cwd=cwd, env=env, check=False).returncode


def _maybe(
    argv: list[str],
    cwd: Path | None = None,
    env_extra: dict[str, str] | None = None,
    yes: bool = False,
) -> int:
    """Plan mode prints the command; execute mode runs it. Non-zero rc means stop."""
    line = shlex.join(str(a) for a in argv) + (f"  # cwd={cwd}" if cwd else "")
    if not yes:
        print(f"  would run: {line}")
        return 0
    return _run(argv, cwd=cwd, env_extra=env_extra)


def _dir_populated(path: Path) -> bool:
    return path.is_dir() and any(
        p.suffix in (".safetensors", ".json") or p.is_dir() for p in path.iterdir()
    )


def _git_head(checkout: Path) -> str | None:
    out = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return out.stdout.strip()[:12] or None


def _download(repo_id: str, local_dir: Path, venv_python: Path, yes: bool) -> int:
    """snapshot_download through a venv python that already has huggingface_hub."""
    code = (
        "import huggingface_hub;"
        f"huggingface_hub.snapshot_download({repo_id!r}, local_dir={str(local_dir)!r})"
    )
    argv = [str(venv_python), "-c", code]
    return _maybe(argv, env_extra={"HF_HUB_CACHE": str(PATHS["hf_cache"])}, yes=yes)


def _install_image(opts: argparse.Namespace) -> int:
    _need_apple_silicon()
    mflux = [
        "uv",
        "tool",
        "install",
        "--reinstall",
        "--from",
        f"git+https://github.com/mflux-community/mflux@{PINS['mflux']}",
        "mflux",
    ]
    if _maybe(mflux, yes=opts.yes):
        return 1
    for cli in (
        "mflux-generate-flux2",
        "mflux-generate-iris",
        "mflux-generate-z-image-turbo",
        "mflux-generate-qwen-2.1",
    ):
        if opts.yes and not (Path.home() / ".local/bin" / cli).exists():
            print(f"[image] warning: {cli} not in ~/.local/bin after install")
    _print_sizes(SIZE_REPOS)
    print(
        "[image] z-image/qwen repo ids resolve inside mflux at first generate;"
        " those sizes stream to the HF cache then."
    )
    return 0


def _install_video(opts: argparse.Namespace) -> int:
    _need_apple_silicon()
    if not Path("/Volumes/data01").exists():
        raise SystemExit("/Volumes/data01 is not mounted — the screen keeps weights on data01")
    data_root = PATHS["weights_root"]
    checkout = data_root / "FastVideo"
    venv = checkout / ".venv"
    pin = PINS["fastvideo"]
    if not (checkout / ".git").exists() and _maybe(
        [
            "git",
            "clone",
            "--branch",
            "main",
            "https://github.com/hao-ai-lab/FastVideo.git",
            str(checkout),
        ],
        yes=opts.yes,
    ):
        return 1
    head = _git_head(checkout) if (checkout / ".git").exists() else None
    if (
        head is not None
        and head != pin
        and _maybe(["git", "-C", str(checkout), "checkout", pin], yes=opts.yes)
    ):
        return 1
    if not (venv / "bin/python").exists() and _maybe(
        ["uv", "venv", "--python", "3.12", str(venv)], yes=opts.yes
    ):
        return 1
    if not next(venv.glob("lib/python3*/site-packages/fastvideo"), None):
        if _maybe(
            ["uv", "pip", "install", "--python", str(venv / "bin/python"), "-e", ".[mlx]"],
            cwd=checkout,
            yes=opts.yes,
        ):
            return 1
    _print_sizes(tuple((f"FastMetal weights ({repo_id})", repo_id) for repo_id, _ in WEIGHT_REPOS))
    for repo_id, dirname in WEIGHT_REPOS:
        local = data_root / dirname
        if _dir_populated(local):
            print(f"[video] {local} already populated — leaving it alone")
            continue
        if _download(repo_id, local, venv / "bin/python", opts.yes):
            return 1
    print(f"[video] screen commands use --model-root/--mlx-checkpoint under {data_root}")
    return 0


def _install_music(opts: argparse.Namespace) -> int:
    _need_apple_silicon()
    ace = PATHS["ace_root"]
    need = [
        ace / ".venv/bin/python",
        ace / "checkpoints/acestep-v15-turbo",
        ace / "checkpoints/acestep-v15-xl-turbo",
        ace / "checkpoints/acestep-5Hz-lm-1.7B",
    ]
    missing = [str(p) for p in need if not p.exists()]
    if missing:
        raise SystemExit(f"ACE-Step tree incomplete, screen needs it intact: {missing}")
    lm_dir = ace / "checkpoints" / "acestep-5Hz-lm-0.6B"
    if _dir_populated(lm_dir):
        print(f"[music] {lm_dir} already populated — leaving it alone")
        return 0
    _print_sizes(((f"acestep 5Hz 0.6B planner LM (into {lm_dir})", LM_REPO),))
    primary = [
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "acestep.model_downloader",
        "--model",
        "acestep-5Hz-lm-0.6B",
    ]
    if not opts.yes:
        print(f"  would run (primary, from {ace}): {shlex.join(primary)}")
        print(
            f"  would run (fallback): ace tree .venv python — huggingface_hub.snapshot_download("
            f"{LM_REPO!r}, local_dir={str(lm_dir)!r})"
        )
        return 0
    if _run(primary, cwd=ace) == 0 and _dir_populated(lm_dir):
        return 0
    print("[music] model_downloader path failed or wrote nothing; falling back to huggingface_hub")
    venv_python = ace / ".venv/bin/python"
    return 0 if _download(LM_REPO, lm_dir, venv_python, True) == 0 and _dir_populated(lm_dir) else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--medium", choices=("image", "video", "music", "all"), default="all")
    parser.add_argument(
        "--yes", action="store_true", help="execute; without it print the plan and sizes only"
    )
    opts = parser.parse_args()
    mediums = ("image", "video", "music") if opts.medium == "all" else (opts.medium,)
    installers = {"image": _install_image, "video": _install_video, "music": _install_music}
    rc = 0
    for medium in mediums:
        rc = rc or installers[medium](opts)
    if not opts.yes:
        print("\nplan only — re-run with --yes to execute")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
