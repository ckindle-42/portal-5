#!/usr/bin/env python3
"""Install oMLX in a stable venv backed by a signed python.org interpreter."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

DEFAULT_VENV = Path.home() / "omlx-live" / "venv"
RELEASE_API = "https://api.github.com/repos/jundot/omlx/releases/tags/v{}"
LATEST_API = "https://api.github.com/repos/jundot/omlx/releases/latest"
PYTHON_VERSIONS = ("3.13", "3.12", "3.11")


def venv_path(value: str | None = None) -> Path:
    return Path(value or os.environ.get("OMLX_VENV_PATH") or DEFAULT_VENV).expanduser()


def _run(cmd: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _checked_run(cmd: list[str], run=_run) -> subprocess.CompletedProcess:
    result = run(cmd)
    if result.returncode:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
    return result


def verify_framework_python(python: Path, run=_run) -> None:
    machine = _checked_run(
        [str(python), "-c", "import platform; print(platform.machine())"], run
    ).stdout.strip()
    signature = run(["codesign", "-dv", "--verbose=4", str(python)])
    if (
        machine != "arm64"
        or signature.returncode
        or "Developer ID" not in (signature.stdout + signature.stderr)
    ):
        raise RuntimeError(f"python.org framework interpreter is not signed ARM64: {python}")


def find_framework_python(run=_run) -> Path:
    for version in PYTHON_VERSIONS:
        python = Path(
            f"/Library/Frameworks/Python.framework/Versions/{version}/bin/python{version}"
        )
        if not python.is_file():
            continue
        try:
            verify_framework_python(python, run)
            return python
        except RuntimeError:
            continue
    raise RuntimeError(
        "No signed ARM64 python.org Python 3.11, 3.12, or 3.13 framework was found.\n"
        "Install a macOS universal2 Python from https://www.python.org/downloads/macos/ "
        "(do not install it with Homebrew). Then confirm that one of these exists and "
        "is Developer ID signed:\n"
        "  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13\n"
        "  /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12\n"
        "  /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11\n"
        "Rerun: uv run python scripts/omlx_venv_install.py"
    )


def latest_release_version() -> str:
    request = urllib.request.Request(LATEST_API, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed GitHub API
        return str(json.loads(response.read().decode())["tag_name"]).removeprefix("v")


def _python_tag(python: Path, run=_run) -> str:
    result = _checked_run(
        [
            str(python),
            "-c",
            "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')",
        ],
        run,
    )
    tag = result.stdout.strip()
    if tag not in {"cp311", "cp312", "cp313"}:
        raise RuntimeError(f"unsupported oMLX wheel interpreter: {tag}")
    return tag


def _release_asset(version: str, tag: str) -> tuple[str, str]:
    release_url = RELEASE_API.format(version.removeprefix("v"))
    request = urllib.request.Request(release_url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed GitHub API
        release = json.loads(response.read().decode())
    expected = f"omlx-{version.removeprefix('v')}-{tag}-{tag}-macosx_15_0_universal2.whl"
    for asset in release.get("assets", []):
        if asset.get("name") == expected:
            return expected, str(asset["browser_download_url"])
    raise RuntimeError(f"GitHub release {version} has no {expected} wheel")


def _verify_venv(python: Path, version: str, run=_run) -> None:
    result = _checked_run(
        [
            str(python),
            "-c",
            "import importlib.metadata as m, platform; "
            "print(platform.machine()); print(m.version('omlx'))",
        ],
        run,
    )
    values = result.stdout.splitlines()
    wanted = version.removeprefix("v")
    if len(values) != 2 or values[0] != "arm64" or values[1] != wanted:
        raise RuntimeError(f"oMLX venv verification failed: {result.stdout.strip()!r}")


def install_release_wheel(version: str, python: Path, run=_run) -> None:
    tag = _python_tag(python, run)
    name, url = _release_asset(version, tag)
    with tempfile.TemporaryDirectory(prefix="omlx-wheel-") as directory:
        wheel = Path(directory) / name
        urllib.request.urlretrieve(url, wheel)  # noqa: S310 - URL came from GitHub release API
        _checked_run([str(python), "-m", "pip", "install", "--upgrade", str(wheel)], run)
    _verify_venv(python, version, run)


def stage_fresh_venv(version: str, target: Path, python: Path | None = None, run=_run) -> Path:
    base_python = find_framework_python(run) if python is None else python
    if python is not None:
        verify_framework_python(base_python, run)
    stage = target.with_name(f"{target.name}.new")
    shutil.rmtree(stage, ignore_errors=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    _checked_run([str(base_python), "-m", "venv", str(stage)], run)
    install_release_wheel(version, stage / "bin" / "python", run)
    return stage


def stage_venv_upgrade(version: str, source: Path, run=_run) -> Path:
    stage = source.with_name(f"{source.name}.new")
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(source, stage, symlinks=True)
    install_release_wheel(version, stage / "bin" / "python", run)
    return stage


def relocate_venv_entrypoints(stage: Path, target: Path) -> None:
    old = os.fsencode(str(stage))
    new = os.fsencode(str(target))
    for script in (stage / "bin").iterdir():
        if script.is_symlink() or not script.is_file():
            continue
        with script.open("rb") as stream:
            first = stream.readline()
            if not first.startswith(b"#!") or old not in first:
                continue
            rest = stream.read()
        script.write_bytes(first.replace(old, new, 1) + rest)


def activate_venv(stage: Path, target: Path) -> Path:
    previous = target.with_name(f"{target.name}.previous")
    if previous.exists():
        raise RuntimeError(f"refusing to replace pending rollback venv: {previous}")
    relocate_venv_entrypoints(stage, target)
    if target.exists():
        target.rename(previous)
    try:
        stage.rename(target)
    except OSError:
        if previous.exists() and not target.exists():
            previous.rename(target)
        raise
    return previous


def install(version: str, target: Path, python: Path | None = None, run=_run) -> None:
    stage = stage_fresh_venv(version, target, python, run)
    activate_venv(stage, target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="GitHub oMLX release; defaults to latest stable")
    parser.add_argument("--venv", help=f"fixed venv path (default: {DEFAULT_VENV})")
    parser.add_argument("--python", help="signed python.org framework interpreter path")
    args = parser.parse_args(argv)
    version = args.version or latest_release_version()
    try:
        install(
            version,
            venv_path(args.venv),
            Path(args.python) if args.python else None,
        )
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Installed oMLX {version} at {venv_path(args.venv)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
