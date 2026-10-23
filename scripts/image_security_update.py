#!/usr/bin/env python3
"""Keep compose images current — Open WebUI on an explicit release pin.

Open WebUI runs the locally built ``portal5-open-webui:<release>-hardened`` image
(``deploy/portal-5/Dockerfile.openwebui``: the pinned upstream release plus patched
wheels) and is pinned by the ``OPENWEBUI_VERSION`` build arg in
``deploy/portal-5/docker-compose.yml``. This module is the ONLY route that moves
it: compose sets ``pull_policy: never`` and ``launch.sh up`` / ``weekly_rebuild.py``
leave it out of their pulls and call :func:`owui_update` instead. The daily run
only *proposes* a newer upstream release; adopting one is explicit
(``--bump [TAG]``) and applied as:

  1. rebuild the image from the new upstream base; stop Open WebUI, tag the
     running image ``:rollback`` (survives ``image prune``) and tar ``webui.db`` +
     ``vector_db`` to ``~/.portal5/backups`` — its DB migrations are one-way, so
     the data must be restorable too;
  2. recreate on the new build and wait for the healthcheck;
  3. on failure restore the data and the previous compose pin, re-tag the previous
     build, record the upstream base's revision as rejected and alert.

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
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.check_updates import _pushover, check_images  # noqa: E402
from scripts.engine_autoupdate import busy, log  # noqa: E402

COMPOSE = REPO / "deploy" / "portal-5" / "docker-compose.yml"
DOCKER = shutil.which("docker") or "/usr/local/bin/docker"
SERVICES = {"searxng/searxng": "searxng"}  # re-pulled when an advisory is newer than the build
OWUI_IMAGE_PREFIX = "portal5-open-webui"  # locally built from Dockerfile.openwebui
OWUI_RELEASE = "v0.12.3"  # also the default OPENWEBUI_VERSION build arg
OWUI_IMAGE = f"{OWUI_IMAGE_PREFIX}:{OWUI_RELEASE}-hardened"
OWUI_ROLLBACK = f"{OWUI_IMAGE_PREFIX}:rollback"
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
def _compose_text() -> str:
    try:
        return COMPOSE.read_text()
    except OSError:
        return ""


def _service_block(text: str) -> re.Match[str] | None:
    return re.search(r"^  open-webui:\n(.*?)(?=^  \S)", text, re.MULTILINE | re.DOTALL)


def _service_field(text: str, pattern: str, default: str) -> str:
    block = _service_block(text)
    hit = re.search(pattern, block.group(1), re.MULTILINE) if block else None
    return hit.group(1) if hit else default


def _pinned_release(text: str | None = None) -> str:
    """Upstream release pinned by the OPENWEBUI_VERSION build arg."""
    return _service_field(
        _compose_text() if text is None else text,
        r"^\s+OPENWEBUI_VERSION:\s*(\S+)",
        OWUI_RELEASE,
    )


def _pinned_image(text: str | None = None) -> str:
    """Hardened image ref pinned in compose (OWUI_IMAGE when unreadable)."""
    return _service_field(
        _compose_text() if text is None else text, r"^\s+image:\s*(\S+)", OWUI_IMAGE
    )


def _image_ref(release: str) -> str:
    return f"{OWUI_IMAGE_PREFIX}:{release}-hardened"


def _set_pinned(release: str) -> bool:
    """Rewrite the image tag and the OPENWEBUI_VERSION arg; False when either is absent."""
    text = _compose_text()
    block = _service_block(text)
    if block is None:
        return False
    body, img = re.subn(
        r"^(\s+image:\s*)\S+",
        lambda m: m.group(1) + _image_ref(release),
        block.group(1),
        count=1,
        flags=re.MULTILINE,
    )
    body, arg = re.subn(
        r"^(\s+OPENWEBUI_VERSION:\s*)\S+",
        lambda m: m.group(1) + release,
        body,
        count=1,
        flags=re.MULTILINE,
    )
    if not (img and arg):
        return False
    COMPOSE.write_text(text[: block.start(1)] + body + text[block.end(1) :])
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


def _revert(previous: str, old_id: str, image: str) -> bool:
    """Put the previous compose pin back and re-tag the previous hardened image."""
    COMPOSE.write_text(previous)
    return _docker("tag", old_id, image, timeout=60).returncode == 0


def _rollback(
    old_id: str,
    old_rev: str,
    bad: str,
    name: str,
    state: dict[str, Any],
    previous: str,
    image: str,
) -> tuple[bool, str]:
    """Restore the data + previous image after a build failed its health gate."""
    tail = _docker("logs", "--tail", "15", OWUI_CONTAINER, timeout=60)
    log(f"open-webui: {bad} did not come up healthy — rolling back\n{tail.stderr[-1200:]}")
    _compose("stop", OWUI_SVC)
    restored = (
        _restore(name)
        and _revert(previous, old_id, image)
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


def _swap(
    old_id: str, previous: str, rev: str, state: dict[str, Any], pinned: str
) -> tuple[bool, str]:
    """Back up the data, recreate on the new build, roll back if it stays unhealthy."""
    prev_image, prev_release = _pinned_image(previous), _pinned_release(previous)
    old_rev = _revision(old_id) or prev_release
    log(f"open-webui: moving {old_rev} -> {rev} ({pinned})")
    _docker("tag", old_id, OWUI_ROLLBACK, timeout=60)
    name = f"owui-{old_rev}-{dt.datetime.now():%Y%m%dT%H%M%S}.tar"
    _compose("stop", OWUI_SVC)
    if not _backup(name):
        restored = (
            _revert(previous, old_id, prev_image)
            and _compose("up", "-d", "--no-deps", OWUI_SVC).returncode == 0
            and _wait_healthy(OWUI_SVC, 900)
        )
        return restored, "open-webui: data backup failed — stayed on the current build"

    if _compose("up", "-d", "--no-deps", OWUI_SVC).returncode == 0 and _wait_healthy(OWUI_SVC, 900):
        return True, f"open-webui: updated to {rev} (data backup {name})"

    return _rollback(old_id, old_rev, rev, name, state, previous, prev_image)


def _apply_pinned(previous: str, dry_run: bool, proposal: str = "") -> tuple[bool, str]:
    pinned, release = _pinned_image(), _pinned_release()
    running = _docker("inspect", OWUI_CONTAINER, "--format", "{{.Image}}", timeout=60)
    old_id = running.stdout.strip() if running.returncode == 0 else _image_id(pinned)
    if not old_id:
        return False, "open-webui: no running container or local image to update from"
    if dry_run:
        return True, f"[dry-run] would build {release} and apply it behind the health gate"
    if _compose("build", OWUI_SVC, timeout=3600).returncode != 0:
        COMPOSE.write_text(previous)  # a failed --bump must not leave the new pin behind
        return True, f"open-webui: build of {release} failed — staying on the current build"
    new_id = _image_id(pinned)
    # Inherited from the upstream base; a derived build without it is tracked by release.
    rev = _revision(pinned) or release
    if new_id == old_id:
        note = f"; {proposal}" if proposal else ""
        return True, f"open-webui: current ({rev}){note}"

    state = _load()
    if rev in state.get("rejected", {}).get("open-webui", []):
        return True, f"open-webui: build {rev} was rejected earlier — staying on the current one"

    return _swap(old_id, previous, rev, state, pinned)


def owui_update(dry_run: bool = False, bump: str | None = None) -> tuple[bool, str]:
    """Apply the pinned release; ``bump`` rewrites the hardened pin first ("" = newest)."""
    previous = _compose_text()
    if not previous:
        return False, f"open-webui: cannot read {COMPOSE}"
    release = _pinned_release(previous)
    proposal = ""
    if bump is None:
        latest = _latest_release()
        if latest and _tag_key(latest) > _tag_key(release):
            proposal = f"newer release {latest} available (`--bump {latest}`)"
    else:
        target = _release_tag(bump) if bump else _release_tag(_latest_release())
        if not target:
            return False, f"open-webui: could not resolve a release tag ({bump or 'upstream'})"
        if dry_run:
            return True, f"[dry-run] would bump the pin to {target} behind the health gate"
        if not _set_pinned(target):
            return False, f"open-webui: no OPENWEBUI_VERSION/image pin for open-webui in {COMPOSE}"
        log(f"open-webui: pin bumped to {target} in {COMPOSE}")
    return _apply_pinned(previous, dry_run, proposal)


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
