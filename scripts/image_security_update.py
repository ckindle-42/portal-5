#!/usr/bin/env python3
"""Re-pull floating-tag compose images that have a security advisory newer than the build.

``docker compose up`` only refreshes images at start, so a long-running stack
keeps an old Open WebUI / SearXNG for weeks. This closes that gap: when
``check_updates.check_images`` finds an advisory published after the local image
was built, pull that one service and recreate it (``--no-deps``), then wait for
it to be running. Pinned images (Grafana, Prometheus, Wazuh) and Python deps are
report-only — bumping them can change behaviour and is a deliberate commit.

Runs daily from launchd (``deploy/launchd/com.portal5.image-update.plist``).
``--dry-run`` reports without touching containers. Defers while a
WFE/UAT/bench run is in flight.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.check_updates import _pushover, check_images  # noqa: E402
from scripts.engine_autoupdate import busy, log  # noqa: E402

COMPOSE = REPO / "deploy" / "portal-5" / "docker-compose.yml"
SERVICES = {"open-webui/open-webui": "open-webui", "searxng/searxng": "searxng"}


def _compose(*args: str, timeout: int = 900) -> subprocess.CompletedProcess:
    docker = shutil.which("docker") or "/usr/local/bin/docker"
    return subprocess.run(
        [docker, "compose", "-f", str(COMPOSE), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=COMPOSE.parent,
    )


def _running(service: str) -> bool:
    r = _compose("ps", "--status", "running", "-q", service, timeout=60)
    return bool(r.stdout.strip())


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    rep = check_images()
    stale = [SERVICES[r] for r in rep.stale_images if r in SERVICES]
    if not stale:
        log("no floating image has a newer advisory — nothing to do")
        return 0
    if (who := busy()) is not None:
        log(f"deferring: a sweep is running ({who})")
        return 0
    for svc in stale:
        if dry_run:
            log(f"[dry-run] would pull + recreate {svc}")
            continue
        log(f"{svc}: advisory newer than local build — pulling and recreating")
        pull = _compose("pull", svc)
        up = _compose("up", "-d", "--no-deps", svc) if pull.returncode == 0 else pull
        ok = up.returncode == 0
        if ok:
            deadline = time.monotonic() + 180
            while not (ok := _running(svc)) and time.monotonic() < deadline:
                time.sleep(5)
        msg = f"{svc} updated for security advisory" if ok else f"{svc} update FAILED"
        log(msg + ("" if ok else f"\n{pull.stderr[-400:]}{up.stderr[-400:]}"))
        _pushover("Image security update", msg, high=not ok)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
