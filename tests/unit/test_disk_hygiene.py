"""Disk hygiene: _disk_hygiene prunes what the started stack no longer uses.

Stubbed docker/df/du (test_installer_launchd_reload.py stub pattern) drive the
util.sh function: superseded Portal images (retired MCP image) are removed,
compose-declared and container-referenced images are kept, dind keeps the
images its compose-declared sandbox services need, the report prints
before/after main-drive free space and Docker.raw allocated size, and the
fstrim runs through the VM namespaces. No live docker here.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_UTIL = _ROOT / "scripts" / "lib" / "util.sh"

_DOCKER_STUB = r"""#!/bin/bash
state="${PORTAL5_TEST_STATE:?}"
case "$1" in
  compose) cat "$state/declared_images" ;;
  ps) cat "$state/in_use_images" ;;
  image)
    case "$2" in
      ls)
        if [[ "$4" == *Size* ]]; then cat "$state/host_images"; else cat "$state/dind_images"; fi ;;
      prune) echo "Total reclaimed space: 1.2GB" ;;
      *) exit 1 ;;
    esac ;;
  builder) echo "Total reclaimed space: 3.4GB" ;;
  rmi) echo "$2" >> "$state/removed.log"; exit 0 ;;
  inspect) cat "$state/dind_state" ;;
  exec)
    case "$4" in
      rmi) echo "$5" >> "$state/dind_removed.log"; exit 0 ;;
      image)
        case "$5" in
          ls) cat "$state/dind_images" ;;
          prune) echo "Total reclaimed space: 0B" ;;
          *) exit 1 ;;
        esac ;;
      builder) echo "Total reclaimed space: 0B" ;;
      *) exit 1 ;;
    esac ;;
  run)
    printf '%s\n' "$*" >> "$state/cmd.log"
    echo "/var/lib/docker: 1.0 GiB trimmed" ;;
  *) exit 1 ;;
esac
"""

_DF_STUB = r"""#!/bin/sh
state="${PORTAL5_TEST_STATE:?}"
n="$(cat "$state/df_calls" 2>/dev/null || echo 0)"
echo $((n + 1)) > "$state/df_calls"
if [ "$n" -eq 0 ]; then avail=10485760; else avail=15728640; fi
echo "Filesystem 1K-blocks Used Available Use%"
echo "/dev/disk3s1s1 971350180 13436672 $avail 4%"
"""

_DU_STUB = r"""#!/bin/sh
state="${PORTAL5_TEST_STATE:?}"
n="$(cat "$state/du_calls" 2>/dev/null || echo 0)"
echo $((n + 1)) > "$state/du_calls"
if [ "$n" -eq 0 ]; then echo 20971520; else echo 19922944; fi
"""


def _hygiene_run(tmp_path: Path, monkeypatch, *, dind_running: bool = True) -> str:
    home = tmp_path / "home"
    state = tmp_path / "state"
    stubs = tmp_path / "stubs"
    compose = tmp_path / "deploy" / "portal-5"
    raw = home / "Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"")
    compose.mkdir(parents=True)
    state.mkdir()
    stubs.mkdir()
    (compose / "docker-compose.yml").write_text(
        "services:\n"
        "  mcp-sandbox:\n"
        "    environment:\n"
        "      - SANDBOX_DOCKER_IMAGE=${SANDBOX_DOCKER_IMAGE:-portal5-sandbox-data:latest}\n"
        "  binresearch:\n"
        "    environment:\n"
        "      - BINRESEARCH_IMAGE=${BINRESEARCH_IMAGE:-portal5-binresearch:latest}\n"
    )
    (stubs / "docker").write_text(_DOCKER_STUB)
    (stubs / "df").write_text(_DF_STUB)
    (stubs / "du").write_text(_DU_STUB)
    for stub in stubs.iterdir():
        stub.chmod(0o755)
    (state / "declared_images").write_text("portal-5-mcp-documents\npython:3.11-slim\n")
    (state / "in_use_images").write_text("portal-5-mcp-documents:latest\n")
    (state / "host_images").write_text(
        "portal-5-mcp-reranker:latest\t23.6GB\n"
        "portal-5-mcp-documents:latest\t7.56GB\n"
        "python:3.11-slim\t215MB\n"
        "<none>:<none>\t0B\n"
    )
    (state / "dind_images").write_text(
        "python:3.11-slim\nportal5-sandbox-data:latest\nportal5-pwsh:latest\n<none>:<none>\n"
    )
    (state / "dind_state").write_text("true" if dind_running else "false\n")

    env = {
        "PATH": f"{stubs}:{os.environ['PATH']}",
        "HOME": str(home),
        "PORTAL5_TEST_STATE": str(state),
        "PORTAL_ROOT": str(tmp_path),
        "COMPOSE_DIR": str(compose),
    }
    result = subprocess.run(
        ["bash", "-c", f"source {_UTIL}; _disk_hygiene"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_superseded_portal_image_removed_declared_and_used_kept(tmp_path, monkeypatch):
    out = _hygiene_run(tmp_path, monkeypatch)
    removed = (tmp_path / "state" / "removed.log").read_text().splitlines()

    assert removed == ["portal-5-mcp-reranker:latest"]
    assert "superseded image: portal-5-mcp-reranker:latest (23.6GB)" in out
    assert "superseded Portal images removed: 1" in out


def test_report_prints_before_after_free_space_and_docker_raw(tmp_path, monkeypatch):
    out = _hygiene_run(tmp_path, monkeypatch)

    assert "main drive free: 10.0 → 15.0 GB (Δ+5.0 GB)" in out
    assert "Docker.raw allocated: 20.0 → 19.0 GB (Δ-1.0 GB)" in out
    assert "host dangling images: 1.2GB" in out
    assert "host build cache: 3.4GB" in out


def test_dind_prune_keeps_sandbox_images_removes_unused_upstream(tmp_path, monkeypatch):
    out = _hygiene_run(tmp_path, monkeypatch)
    removed = (tmp_path / "state" / "dind_removed.log").read_text().splitlines()

    assert removed == ["python:3.11-slim"]
    assert "dind dangling images: 0B" in out
    assert "dind build cache: 0B" in out


def test_fstrim_runs_in_vm_namespaces_when_docker_raw_present(tmp_path, monkeypatch):
    out = _hygiene_run(tmp_path, monkeypatch)
    cmd = (tmp_path / "state" / "cmd.log").read_text()

    assert "--pid=host" in cmd
    assert "--privileged" in cmd
    assert cmd.rstrip().endswith("fstrim -av")
    assert "fstrim: /var/lib/docker: 1.0 GiB trimmed" in out


def test_dind_down_skips_dind_prune_and_trim(tmp_path, monkeypatch):
    out = _hygiene_run(tmp_path, monkeypatch, dind_running=False)
    state = tmp_path / "state"

    assert not (state / "dind_removed.log").exists()
    assert not (state / "cmd.log").exists()
    assert "main drive free: 10.0 → 15.0 GB" in out
    assert "fstrim" not in out
