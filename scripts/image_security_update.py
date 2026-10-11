#!/usr/bin/env python3
"""Keep floating-tag compose images current — Open WebUI behind a health gate.

Open WebUI tracks ``ghcr.io/open-webui/open-webui:main`` (upstream's release
branch; no version pin). This module is the ONLY route that moves it: compose
sets ``pull_policy: missing`` and ``launch.sh up`` / ``weekly_rebuild.py`` leave
it out of their pulls and call :func:`owui_update` instead. A new ``:main``
build is applied as:

  1. pull; if the running container is already on that image, done;
  2. tag the running image ``:rollback`` (survives ``image prune``), stop Open
     WebUI and tar ``webui.db`` + ``vector_db`` to ``~/.portal5/backups`` —
     its DB migrations are one-way, so the data must be restorable too;
  3. recreate on the new image and wait for the healthcheck;
  4. on failure restore the data, re-point ``:main`` at the rollback image,
     bring it back up, record the build's revision as rejected (skipped until
     upstream ships a different build) and alert.

2026-10-11: an unguarded pull of v0.12.0 crash-looped on a migration against a
legacy column default in our DB; nothing could roll it back.

SearXNG (floating ``:latest``) is re-pulled when ``check_updates.check_images``
finds an advisory newer than the local build. Pinned infra images (Grafana,
Prometheus, Wazuh) are ``security_autoupdate``'s.

Runs daily from launchd (``deploy/launchd/com.portal5.image-update.plist``).
``--dry-run`` reports without touching containers. Defers while a
WFE/UAT/bench run is in flight. State: ~/.portal5/image_update.json.
"""

from __future__ import annotations

import datetime as dt
import json
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
DOCKER = shutil.which("docker") or "/usr/local/bin/docker"
SERVICES = {"searxng/searxng": "searxng"}  # re-pulled when an advisory is newer than the build
OWUI_IMAGE = "ghcr.io/open-webui/open-webui:main"
OWUI_ROLLBACK = "ghcr.io/open-webui/open-webui:rollback"
OWUI_SVC = "open-webui"
OWUI_CONTAINER = "portal5-open-webui"
OWUI_DATA = "/app/backend/data"
BACKUPS = Path.home() / ".portal5" / "backups"
STATE = Path.home() / ".portal5" / "image_update.json"
KEEP_BACKUPS = 3


def _docker(*args: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run([DOCKER, *args], capture_output=True, text=True, timeout=timeout)


def _compose(*args: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(
        [DOCKER, "compose", "-f", str(COMPOSE), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=COMPOSE.parent,
    )


def _healthy(service: str) -> bool:
    """Running and, where the service has a healthcheck, healthy — a crash-looping
    container (e.g. a failed DB migration) is briefly "running" between restarts."""
    r = _compose("ps", "--format", "json", service, timeout=60)
    try:
        st = json.loads(r.stdout.strip().splitlines()[0])
    except (IndexError, ValueError):
        return False
    return st.get("State") == "running" and st.get("Health") in ("healthy", "")


def _wait_healthy(service: str, timeout_s: int) -> bool:
    deadline = time.monotonic() + timeout_s
    while not (ok := _healthy(service)) and time.monotonic() < deadline:
        time.sleep(5)
    return ok


def _load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1))


# ── SearXNG: advisory-driven re-pull ─────────────────────────────────────────
def floating(dry_run: bool) -> None:
    rep = check_images()
    stale = [SERVICES[r] for r in rep.stale_images if r in SERVICES]
    if not stale:
        log("searxng: no advisory newer than the local build")
    for svc in stale:
        if dry_run:
            log(f"[dry-run] would pull + recreate {svc}")
            continue
        log(f"{svc}: advisory newer than local build — pulling and recreating")
        pull = _compose("pull", svc)
        up = _compose("up", "-d", "--no-deps", svc) if pull.returncode == 0 else pull
        ok = up.returncode == 0 and _wait_healthy(svc, 300)
        msg = f"{svc} updated for security advisory" if ok else f"{svc} update FAILED"
        log(msg + ("" if ok else f"\n{pull.stderr[-400:]}{up.stderr[-400:]}"))
        _pushover("Image security update", msg, high=not ok)


# ── Open WebUI: :main behind backup + health gate + rollback ─────────────────
def _image_id(ref: str) -> str:
    r = _docker("image", "inspect", ref, "--format", "{{.Id}}", timeout=60)
    return r.stdout.strip() if r.returncode == 0 else ""


def _revision(ref: str) -> str:
    r = _docker(
        "image",
        "inspect",
        ref,
        "--format",
        '{{index .Config.Labels "org.opencontainers.image.revision"}}',
        timeout=60,
    )
    return r.stdout.strip()[:12] if r.returncode == 0 else ""


def _data_shell(script: str) -> bool:
    """Run `script` in a throwaway container sharing Open WebUI's volumes (works
    while it is stopped), with the backup dir at /b."""
    BACKUPS.mkdir(parents=True, exist_ok=True)
    r = _docker(
        "run",
        "--rm",
        "--volumes-from",
        OWUI_CONTAINER,
        "-v",
        f"{BACKUPS}:/b",
        "alpine",
        "sh",
        "-c",
        script,
        timeout=1800,
    )
    if r.returncode:
        log(f"  data step failed: {r.stderr[-400:]}")
    return r.returncode == 0


def _backup(name: str) -> bool:
    ok = _data_shell(f"cd {OWUI_DATA} && tar cf /b/{name} webui.db* vector_db")
    for old in sorted(BACKUPS.glob("owui-*.tar"), key=lambda f: f.stat().st_mtime)[:-KEEP_BACKUPS]:
        old.unlink()
    return ok


def _restore(name: str) -> bool:
    return _data_shell(
        f"cd {OWUI_DATA} && rm -rf vector_db webui.db webui.db-wal webui.db-shm && tar xf /b/{name}"
    )


def _rollback(old_id: str, old_rev: str, bad: str, name: str, state: dict) -> tuple[bool, str]:
    """Restore the data + previous image after a build failed its health gate."""
    tail = _docker("logs", "--tail", "15", OWUI_CONTAINER, timeout=60)
    log(f"open-webui: {bad} did not come up healthy — rolling back\n{tail.stderr[-1200:]}")
    _compose("stop", OWUI_SVC)
    restored = (
        _restore(name)
        and _docker("tag", old_id, OWUI_IMAGE, timeout=60).returncode == 0
        and _compose("up", "-d", "--no-deps", OWUI_SVC).returncode == 0
        and _wait_healthy(OWUI_SVC, 900)
    )
    state.setdefault("rejected", {}).setdefault("open-webui", []).append(bad)
    _save(state)
    outcome = "(healthy)" if restored else f"BUT ROLLBACK IS NOT HEALTHY (backup {BACKUPS / name})"
    return False, (
        f"open-webui: build {bad} unhealthy — rolled back to {old_rev} {outcome}; "
        f"skipped until upstream ships a new build (or clear it from {STATE})"
    )


def owui_update(dry_run: bool = False) -> tuple[bool, str]:
    """Apply a new ``:main`` build if there is one. Returns (ok, summary); ok is
    False only when Open WebUI is left unhealthy or the update was rolled back."""
    running = _docker("inspect", OWUI_CONTAINER, "--format", "{{.Image}}", timeout=60)
    old_id = running.stdout.strip() if running.returncode == 0 else _image_id(OWUI_IMAGE)
    if not old_id:
        return False, "open-webui: no running container or local image to update from"
    if dry_run:
        return True, "[dry-run] would pull open-webui:main and apply it behind the health gate"
    if _docker("pull", OWUI_IMAGE, timeout=3600).returncode != 0:
        return True, "open-webui: pull failed — staying on the current build"
    new_id, rev = _image_id(OWUI_IMAGE), _revision(OWUI_IMAGE)
    if new_id == old_id:
        return True, f"open-webui: current ({rev or new_id[:19]})"

    state = _load()
    if rev and rev in state.get("rejected", {}).get("open-webui", []):
        _docker("tag", old_id, OWUI_IMAGE, timeout=60)
        return True, f"open-webui: build {rev} was rejected earlier — staying on the current one"

    old_rev = _revision(old_id)
    log(f"open-webui: new :main build {old_rev or old_id[:19]} -> {rev or new_id[:19]}")
    _docker("tag", old_id, OWUI_ROLLBACK, timeout=60)
    name = f"owui-{old_rev or 'prev'}-{dt.datetime.now():%Y%m%dT%H%M%S}.tar"
    _compose("stop", OWUI_SVC)
    if not _backup(name):
        _docker("tag", old_id, OWUI_IMAGE, timeout=60)
        _compose("up", "-d", "--no-deps", OWUI_SVC)
        ok = _wait_healthy(OWUI_SVC, 900)
        return ok, "open-webui: data backup failed — stayed on the current build"

    if _compose("up", "-d", "--no-deps", OWUI_SVC).returncode == 0 and _wait_healthy(OWUI_SVC, 900):
        return True, f"open-webui: updated to {rev or new_id[:19]} (data backup {name})"

    return _rollback(old_id, old_rev, rev or new_id, name, state)


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    if (who := busy()) is not None:
        log(f"deferring: a sweep is running ({who})")
        return 0
    floating(dry_run)
    ok, msg = owui_update(dry_run)
    log(msg)
    if "updated" in msg or not ok:
        _pushover("Open WebUI update" + ("" if ok else " FAILED"), msg, high=not ok)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
