"""install-heartmula orchestration: pinned clone, own venv, data01 weights, idempotent re-run.

Tools are stubbed (git/uv/uname and the venv python); nothing downloads or converts.
The dependency plan itself is covered by test_engine_install_plan.py and is stubbed here.
"""

import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SERVICES = _ROOT / "scripts/lib/services.sh"
_SHA = "02dd2e22f6a1bf1a2f769a13f8af952a7a4e9cee"

_PY_STUB = r"""#!/bin/bash
echo "python $*" >> "$PORTAL5_TEST_STATE/python_calls"
args="$*"
case "$args" in
  *snapshot_download*)
    dir=$(printf '%s' "$args" | sed -n "s/.*local_dir='\([^']*\)'.*/\1/p")
    mkdir -p "$dir"
    case "$args" in
      *allow_patterns*) touch "$dir/tokenizer.json" "$dir/gen_config.json" ;;
      *) echo weights > "$dir/model.safetensors" ;;
    esac ;;
  *heartlib_mlx.utils.convert*)
    dst="" prev=""
    for a in "$@"; do
      [ "$prev" = "--dst" ] && dst="$a"
      prev="$a"
    done
    mkdir -p "$dst"
    echo mlx > "$dst/model.safetensors" ;;
  *import*) echo "verify-ok arm64" ;;
esac
exit 0
"""

_GIT_STUB = """#!/bin/bash
echo "git $*" >> "$PORTAL5_TEST_STATE/git_calls"
[ "$1" = "clone" ] && mkdir -p "$3/.git"
exit 0
"""

_UV_STUB = """#!/bin/bash
echo "uv $*" >> "$PORTAL5_TEST_STATE/uv_calls"
if [ "$1" = "sync" ]; then
  mkdir -p "$HEART_TEST_DIR/.venv/bin"
  cp "$PORTAL5_TEST_STATE/python_stub" "$HEART_TEST_DIR/.venv/bin/python"
  chmod +x "$HEART_TEST_DIR/.venv/bin/python"
fi
exit 0
"""


def _install(tmp_path: Path) -> subprocess.CompletedProcess:
    # The conftest guards Python I/O on /Volumes; the mount probe runs in bash, as in the installer.
    if subprocess.run(["bash", "-c", "test -d /Volumes/data01"], check=False).returncode != 0:
        pytest.skip("installer refuses without data01 mounted")
    stubs = tmp_path / "stubs"
    state = tmp_path / "state"
    home = tmp_path / "home"
    weights = tmp_path / "data01-weights"
    for path in (stubs, state, home):
        path.mkdir(exist_ok=True)
    (state / "python_stub").write_text(_PY_STUB)
    (state / "python_stub").chmod(0o755)
    for name, body in (
        ("git", _GIT_STUB),
        ("uv", _UV_STUB),
        ("uname", "#!/bin/sh\necho arm64\n"),
    ):
        stub = stubs / name
        stub.write_text(body)
        stub.chmod(0o755)
    heart_dir = home / ".portal5/music/heartlib-mlx"
    script = (
        f'export HOME="{home}"\n'
        f'export PORTAL5_TEST_STATE="{state}"\n'
        f'export HEART_TEST_DIR="{heart_dir}"\n'
        f'export HEARTMULA_WEIGHTS_ROOT="{weights}"\n'
        f'source "{_SERVICES}"\n'
        '_engine_dep_plan() { echo "dep-plan $*" >> "$PORTAL5_TEST_STATE/dep_plan_calls"; return 0; }\n'
        "_launch_install_heartmula\n"
        'echo "rc=$?"\n'
    )
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        env={"PATH": f"{stubs}:/usr/bin:/bin:/usr/sbin:/sbin", "PORTAL5_TEST_STATE": str(state)},
    )


def _calls(tmp_path: Path, name: str) -> list[str]:
    path = tmp_path / "state" / name
    return path.read_text().splitlines() if path.exists() else []


def test_fresh_install_pins_clones_seeds_venv_downloads_and_converts(tmp_path):
    proc = _install(tmp_path)
    assert "rc=0" in proc.stdout, proc.stderr
    assert "verify-ok arm64" in proc.stdout
    git = _calls(tmp_path, "git_calls")
    assert any(line.startswith("git clone ") for line in git)
    assert any(f"fetch --depth 1 origin {_SHA}" in line for line in git)
    assert any(f"checkout --detach {_SHA}" in line for line in git)
    assert any(line.startswith("uv sync") for line in _calls(tmp_path, "uv_calls"))
    python = _calls(tmp_path, "python_calls")
    assert sum("snapshot_download" in line for line in python) == 3
    assert sum("heartlib_mlx.utils.convert" in line for line in python) == 2
    assert any("--model-type heartmula" in line for line in python)
    assert any("--model-type heartcodec" in line for line in python)
    weights = tmp_path / "data01-weights"
    assert (weights / "ckpt/HeartMuLa-oss-3B-happy-new-year/.portal5-downloaded").exists()
    assert (weights / "ckpt/HeartCodec-oss-20260123/.portal5-downloaded").exists()
    assert (weights / "ckpt/tokenizer.json").exists()
    assert (weights / "ckpt-mlx/heartmula/model.safetensors").exists()
    assert (weights / "ckpt-mlx/heartcodec/model.safetensors").exists()
    assert any("apply" in line for line in _calls(tmp_path, "dep_plan_calls"))


def test_rerun_preserves_venv_and_skips_downloads_and_conversion(tmp_path):
    first = _install(tmp_path)
    assert "rc=0" in first.stdout, first.stderr
    state = tmp_path / "state"
    for name in ("git_calls", "uv_calls", "python_calls", "dep_plan_calls"):
        (state / name).unlink(missing_ok=True)
    second = _install(tmp_path)
    assert "rc=0" in second.stdout, second.stderr
    assert "Preserving the existing heartlib-mlx venv" in second.stdout
    assert second.stdout.count("present:") == 2
    git = _calls(tmp_path, "git_calls")
    assert not any(line.startswith("git clone ") for line in git)
    assert any(f"checkout --detach {_SHA}" in line for line in git)
    assert _calls(tmp_path, "uv_calls") == []
    python = _calls(tmp_path, "python_calls")
    assert len(python) == 1 and "import platform" in python[0]
    assert any("apply" in line for line in _calls(tmp_path, "dep_plan_calls"))
