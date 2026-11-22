"""`./launch.sh rebuild` must rebuild dind (11-22: a stale Alpine 3.21 / Docker 27 image).

`_compose_built_services` derives the rebuild set from docker-compose.yml. Every test stubs
`docker`, so nothing here can reach a real daemon.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_LIB = _ROOT / "scripts" / "lib" / "services.sh"

_SERVICES = {
    "services": {
        "portal-pipeline": {"build": {"context": "../.."}},
        "open-webui": {"build": {"context": "../.."}},
        "dind": {"build": {"context": "../.."}, "container_name": "portal5-dind"},
        "mcp-documents": {
            "build": {"context": "../.."},
            "container_name": "portal5-mcp-documents",
        },
        "portal-telegram": {
            "build": {"context": "../.."},
            "container_name": "portal-telegram",
            "profiles": ["telegram"],
        },
    }
}


def _built_services(tmp_path: Path, mode: str) -> list[str]:
    bindir = tmp_path / "stub-bin"
    bindir.mkdir(exist_ok=True)
    docker = bindir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = compose ]; then\n'
        f"cat <<'JSON'\n{json.dumps(_SERVICES)}\nJSON\n"
        "else\n"
        "  exit 0\n"
        "fi\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}")
    result = subprocess.run(
        ["/bin/bash", "-c", f'source "{_LIB}"; _compose_built_services {mode}'],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return result.stdout.split()


def test_full_rebuild_includes_dind(tmp_path: Path) -> None:
    services = _built_services(tmp_path, "all")
    assert "dind" in services
    assert "open-webui" not in services
    assert {"portal-pipeline", "mcp-documents"} <= set(services)


def test_mcp_subset_leaves_dind_alone(tmp_path: Path) -> None:
    services = _built_services(tmp_path, "--mcp")
    assert "dind" not in services
    assert "portal-pipeline" not in services
    assert "mcp-documents" in services


def test_rebuild_passes_the_build_stamp_to_every_service() -> None:
    launch = (_ROOT / "launch.sh").read_text(encoding="utf-8")
    body = launch.split("  rebuild)", 1)[1].split("\n    ;;", 1)[0]
    build = next(line for line in body.splitlines() if "docker compose build" in line)
    assert "--build-arg PORTAL_BUILD_SHA=" in build
    assert "$BUILD_SERVICES" in build
