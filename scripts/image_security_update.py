#!/usr/bin/env python3
"""Keep compose images current — Open WebUI on an explicit release pin.

Open WebUI is pinned to a tested release in ``deploy/portal-5/docker-compose.yml``.
This module is the ONLY route that moves it: compose sets ``pull_policy: missing``
and ``launch.sh up`` / ``weekly_rebuild.py`` leave it out of their pulls and call
:func:`owui_update` instead. The daily run only *proposes* a newer release;
adopting one is explicit (``--bump [TAG]``) and applied as:

  1. stop Open WebUI, tag the running image ``:rollback`` (survives ``image
     prune``) and tar ``webui.db`` + ``vector_db`` to ``~/.portal5/backups`` —
     its DB migrations are one-way, so the data must be restorable too;
  2. recreate on the pinned image and wait for the healthcheck;
  3. on failure restore the data, re-point the pin at the rollback image,
     record the build's revision as rejected and alert.

2026-10-11: an unguarded pull of v0.12.0 crash-looped on a migration against a
legacy column default in our DB; nothing could roll it back.

SearXNG (floating ``:latest``) is re-pulled when ``check_updates.check_images``
finds an advisory newer than the local build. Pinned infra images (Grafana,
Prometheus, Wazuh) are ``security_autoupdate``'s.

Runs daily from launchd; ``--dry-run`` reports without touching containers and
WFE/UAT/bench runs defer. State: ~/.portal5/image_update.json.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.check_updates import _pushover, check_images  # noqa: E402
from scripts.engine_autoupdate import busy, log  # noqa: E402

COMPOSE = REPO / "deploy" / "portal-5" / "docker-compose.yml"
DOCKER = shutil.which("docker") or "/usr/local/bin/docker"
SERVICES = {"searxng/searxng": "searxng"}  # re-pulled when an advisory is newer than the build
OWUI_REPO = "ghcr.io/open-webui/open-webui"
OWUI_IMAGE = f"{OWUI_REPO}:v0.12.3"
OWUI_ROLLBACK = f"{OWUI_REPO}:rollback"
OWUI_RELEASES = "https://api.github.com/repos/open-webui/open-webui/releases/latest"
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


# ── Open WebUI: pinned release behind backup + health gate + rollback ────────
def _pinned_image() -> str:
    """Open WebUI image ref pinned in compose (OWUI_IMAGE when unreadable)."""
    try:
        text = COMPOSE.read_text()
    except OSError:
        return OWUI_IMAGE
    svc = re.search(r"^  open-webui:\n(.*?)(?=^  \S)", text, re.MULTILINE | re.DOTALL)
    img = re.search(r"^\s+image:\s*(\S+)", svc.group(1), re.MULTILINE) if svc else None
    return img.group(1) if img else OWUI_IMAGE


def _set_pinned_image(image: str) -> bool:
    """Rewrite the open-webui image line; False when the service is absent."""
    text = COMPOSE.read_text()
    svc = re.compile(r"(^  open-webui:\n.*?)(^\s+image:\s*)(\S+)", re.MULTILINE | re.DOTALL)
    new_text, n = svc.subn(lambda m: m.group(1) + m.group(2) + image, text, count=1)
    if not n:
        return False
    COMPOSE.write_text(new_text)
    return True


def _tag_key(tag: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", tag)[:3])


def _latest_release(timeout: int = 10) -> str:
    try:
        req = urllib.request.Request(
            OWUI_RELEASES,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "portal5-image-update"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return str(json.loads(resp.read()).get("tag_name") or "")
    except (OSError, ValueError):
        return ""


def _bump_arg(argv: list[str]) -> str | None:
    """Tag from ``--bump [TAG]``; "" means newest, None means absent."""
    if "--bump" not in argv:
        return None
    nxt = argv[argv.index("--bump") + 1 :] or [""]
    return "" if nxt[0].startswith("-") else nxt[0]


def _release_tag(tag: str) -> str:
    target = tag if tag.startswith("v") else f"v{tag}"
    return target if re.fullmatch(r"v\d+\.\d+\.\d+", target) else ""


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


def _rollback(
    old_id: str, old_rev: str, bad: str, name: str, state: dict, image: str
) -> tuple[bool, str]:
    """Restore the data + previous image after a build failed its health gate."""
    tail = _docker("logs", "--tail", "15", OWUI_CONTAINER, timeout=60)
    log(f"open-webui: {bad} did not come up healthy — rolling back\n{tail.stderr[-1200:]}")
    _compose("stop", OWUI_SVC)
    restored = (
        _restore(name)
        and _docker("tag", old_id, image, timeout=60).returncode == 0
        and _compose("up", "-d", "--no-deps", OWUI_SVC).returncode == 0
        and _wait_healthy(OWUI_SVC, 900)
    )
    state.setdefault("rejected", {}).setdefault("open-webui", []).append(bad)
    _save(state)
    outcome = "(healthy)" if restored else f"BUT ROLLBACK IS NOT HEALTHY (backup {BACKUPS / name})"
    return False, (
        f"open-webui: build {bad} unhealthy — rolled back to {old_rev} {outcome}; "
        f"skipped until the pin changes (or clear it from {STATE})"
    )


def _apply_pinned(pinned: str, dry_run: bool, proposal: str = "") -> tuple[bool, str]:
    running = _docker("inspect", OWUI_CONTAINER, "--format", "{{.Image}}", timeout=60)
    old_id = running.stdout.strip() if running.returncode == 0 else _image_id(pinned)
    if not old_id:
        return False, "open-webui: no running container or local image to update from"
    if dry_run:
        return True, f"[dry-run] would pull {pinned} and apply it behind the health gate"
    if _docker("pull", pinned, timeout=3600).returncode != 0:
        return True, f"open-webui: pull of {pinned} failed — staying on the current build"
    new_id, rev = _image_id(pinned), _revision(pinned)
    if new_id == old_id:
        note = f"; {proposal}" if proposal else ""
        return True, f"open-webui: current ({rev or new_id[:19]}){note}"

    state = _load()
    if rev and rev in state.get("rejected", {}).get("open-webui", []):
        return True, f"open-webui: build {rev} was rejected earlier — staying on the current one"

    old_rev = _revision(old_id)
    log(f"open-webui: moving {old_rev or old_id[:19]} -> {rev or new_id[:19]} ({pinned})")
    _docker("tag", old_id, OWUI_ROLLBACK, timeout=60)
    name = f"owui-{old_rev or 'prev'}-{dt.datetime.now():%Y%m%dT%H%M%S}.tar"
    _compose("stop", OWUI_SVC)
    if not _backup(name):
        _docker("tag", old_id, pinned, timeout=60)
        _compose("up", "-d", "--no-deps", OWUI_SVC)
        ok = _wait_healthy(OWUI_SVC, 900)
        return ok, "open-webui: data backup failed — stayed on the current build"

    if _compose("up", "-d", "--no-deps", OWUI_SVC).returncode == 0 and _wait_healthy(OWUI_SVC, 900):
        return True, f"open-webui: updated to {rev or new_id[:19]} (data backup {name})"

    return _rollback(old_id, old_rev, rev or new_id, name, state, pinned)


def owui_update(dry_run: bool = False, bump: str | None = None) -> tuple[bool, str]:
    """Apply the pinned release; ``bump`` rewrites the compose pin first ("" = newest)."""
    pinned = _pinned_image()
    proposal = ""
    if bump is None:
        latest = _latest_release()
        if latest and _tag_key(latest) > _tag_key(pinned.rsplit(":", 1)[-1]):
            proposal = f"newer release {latest} available (`--bump {latest}`)"
    else:
        target = _release_tag(bump) if bump else _release_tag(_latest_release())
        if not target:
            return False, f"open-webui: could not resolve a release tag ({bump or 'upstream'})"
        if dry_run:
            return True, f"[dry-run] would bump the pin to {target} behind the health gate"
        if not _set_pinned_image(f"{OWUI_REPO}:{target}"):
            return False, f"open-webui: no open-webui image line in {COMPOSE}"
        pinned = f"{OWUI_REPO}:{target}"
        log(f"open-webui: pin bumped to {target} in {COMPOSE}")
    return _apply_pinned(pinned, dry_run, proposal)


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    bump = _bump_arg(argv)
    if (who := busy()) is not None:
        log(f"deferring: a sweep is running ({who})")
        return 0
    floating(dry_run)
    ok, msg = owui_update(dry_run, bump)
    log(msg)
    state = _load()
    release = re.search(r"newer release (\S+)", msg)
    first = bool(release and state.get("proposed") != release.group(1))
    if first and release is not None and not dry_run:
        state["proposed"] = release.group(1)
        _save(state)
    if not dry_run and (not ok or "updated" in msg or bump is not None or first):
        _pushover("Open WebUI update" + ("" if ok else " FAILED"), msg, high=not ok)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
