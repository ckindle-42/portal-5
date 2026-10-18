#!/usr/bin/env python3
"""Weekly full rebuild: fresh base images, every Portal image rebuilt, stack down/up.

The daily image job only re-pulls Open WebUI / SearXNG when an advisory names
them, and ``./launch.sh rebuild`` reuses cached layers (and skips ``dind``), so
OS-package fixes in the python/debian base images never land on their own. This
closes that gap once a week, after the Sunday security-update job has committed
any pinned-image/dependency bumps:

1. ``compose build --pull --no-cache`` — every buildable service, fresh bases.
2. ``compose pull --ignore-buildable`` — refresh pulled images (pinned tags are
   a no-op; floating tags move) — except Open WebUI, see 4.
3. ``./launch.sh down`` + ``./launch.sh up`` — only if 1 and 2 succeeded, so a
   failed build never takes the running stack down.
4. Open WebUI's new ``:main`` build, if any, via ``image_security_update.owui_update``
   (data backup + health gate + rollback) — never by the bulk pull/up.
5. Rebuild the DinD sandbox images (pwsh, data) and load them, as ``rebuild`` does.
6. Health-gate the pipeline, prune dangling images (only on success, so a
   broken upgrade can be rolled back), push a summary.

Runs from launchd (``deploy/launchd/com.portal5.weekly-rebuild.plist``).
``--dry-run`` prints the plan. Defers while a WFE/UAT/bench run is in flight.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.check_updates import _pushover  # noqa: E402
from scripts.engine_autoupdate import busy, log  # noqa: E402
from scripts.image_security_update import owui_update  # noqa: E402

COMPOSE = REPO / "deploy" / "portal-5" / "docker-compose.yml"
DOCKER = shutil.which("docker") or "/usr/local/bin/docker"
PIPELINE_HEALTH = "http://localhost:9099/health"


def _run(cmd: list[str], timeout: int, input_: str | None = None) -> subprocess.CompletedProcess:
    log("$ " + " ".join(cmd))
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=REPO,
        input=input_ if input_ is not None else "",  # EOF for launch.sh prompts
    )
    if r.returncode != 0:
        log(f"  rc={r.returncode}\n{(r.stdout + r.stderr)[-1500:]}")
    return r


def _compose(*args: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return _run([DOCKER, "compose", "-f", str(COMPOSE), *args], timeout)


def _build_args() -> list[str]:
    """The provenance args ``./launch.sh rebuild`` passes. Without them every image reports
    build_sha "unknown" and the WFE harness refuses to trust the deployed build (2026-10-18:
    this job ran mid-program and blanked every service's /health build_sha)."""
    sha = _run(["git", "-C", str(REPO), "rev-parse", "HEAD"], 30).stdout.strip() or "unknown"
    dirty = _run(["git", "-C", str(REPO), "status", "--porcelain", "--", "portal"], 30).stdout
    n = len([ln for ln in dirty.splitlines() if ln.strip()])
    return ["--build-arg", f"PORTAL_BUILD_SHA={sha}", "--build-arg", f"PORTAL_BUILD_DIRTY={n}"]


def _pull_services() -> list[str]:
    """Every active-profile service except Open WebUI (updated by ``owui_update``)."""
    r = _compose("config", "--services", timeout=120)
    # An empty list would make `compose pull` take every service, Open WebUI included.
    return [s for s in r.stdout.split() if s != "open-webui"] if r.returncode == 0 else []


def _pipeline_healthy(timeout_s: int = 600) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(PIPELINE_HEALTH, timeout=5) as r:  # noqa: S310 - localhost
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001 - still starting
            pass
        time.sleep(10)
    return False


def _sandbox_images() -> bool:
    """Same images ``./launch.sh rebuild`` builds and loads into DinD."""
    ok = (
        _run(
            [
                DOCKER,
                "build",
                "--pull",
                "-t",
                "portal5-pwsh:latest",
                "-f",
                str(REPO / "Dockerfile.pwsh"),
                str(REPO),
            ],
            3600,
        ).returncode
        == 0
    )
    data = "FROM python:3.11-slim\nRUN pip install --no-cache-dir pandas openpyxl\n"
    ok &= (
        _run(
            [DOCKER, "build", "--pull", "-t", "portal5-sandbox-data:latest", "-"], 1800, data
        ).returncode
        == 0
    )
    for img in ("portal5-pwsh:latest", "portal5-sandbox-data:latest"):
        save = subprocess.Popen([DOCKER, "save", img], stdout=subprocess.PIPE)
        load = subprocess.run(
            [DOCKER, "exec", "-i", "portal5-dind", "docker", "load"],
            stdin=save.stdout,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        save.wait()
        if load.returncode != 0 or save.returncode != 0:
            log(f"  dind load {img} failed: {load.stderr[-400:]}")
            ok = False
    return ok


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    if (who := busy()) is not None:
        log(f"deferring: a sweep is running ({who})")
        _pushover("Weekly rebuild", f"deferred — {who} in flight", high=False)
        return 0
    if dry_run:
        log(
            "[dry-run] compose build --pull --no-cache; compose pull --ignore-buildable (minus open-webui); "
            "launch.sh down; launch.sh up; guarded open-webui update; DinD sandbox images; "
            "health gate; image prune"
        )
        return 0

    t0 = time.monotonic()
    if _compose("build", "--pull", "--no-cache", *_build_args(), timeout=7200).returncode != 0:
        _pushover(
            "Weekly rebuild FAILED", "image build failed — stack left running untouched", high=True
        )
        return 1
    services = _pull_services()
    if not services or _compose("pull", "--ignore-buildable", *services, timeout=3600).returncode:
        _pushover(
            "Weekly rebuild FAILED", "image pull failed — stack left running untouched", high=True
        )
        return 1

    _run(["bash", "./launch.sh", "down"], 900)
    up = _run(["bash", "./launch.sh", "up"], 3600)
    healthy = _pipeline_healthy()
    owui_ok, owui_msg = owui_update() if healthy else (False, "open-webui: skipped")
    log(owui_msg)
    sandbox = _sandbox_images() if healthy else False
    ok = up.returncode == 0 and healthy and sandbox and owui_ok
    if ok:  # a failed up keeps the previous (now dangling) images for rollback
        _run([DOCKER, "image", "prune", "-f"], 600)

    mins = (time.monotonic() - t0) / 60
    msg = (
        f"{'OK' if ok else 'PROBLEM'} in {mins:.0f} min — up rc={up.returncode}, "
        f"pipeline {'healthy' if healthy else 'NOT healthy'}, sandbox images {'ok' if sandbox else 'FAILED'}; "
        + owui_msg
    )
    log(msg)
    _pushover("Weekly rebuild" + ("" if ok else " NEEDS ATTENTION"), msg, high=not ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
