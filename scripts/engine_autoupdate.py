#!/usr/bin/env python3
"""Keep Ollama and oMLX current — each update gated by the engine contract.

Runs daily from launchd (``deploy/launchd/com.portal5.engine-update.plist``):

  * every day:   ``engine_contract_check --if-changed`` — re-proves that the
                 values Portal sends reach the model whenever an engine version
                 changed by ANY route (including a manual upgrade), and at
                 least weekly regardless.
  * weekly:      install the newest upstream release of each engine, restart
                 it, and run the contract check against it. A failure (or a
                 check that cannot run) rolls the engine back to the previous
                 version, re-verifies that version, records the rejected
                 release so it is not retried, and alerts (Pushover, high).
  * sooner:      when ``check_updates`` flags a security fix or advisory for an
                 engine that is behind, or when run with ``--now``.

Never updates while a WFE campaign, UAT or bench run is in flight (one request
at a time is a house rule; an engine restart mid-sweep invalidates the sweep) —
it defers to the next day.

Ollama:  release tarball unpacked to ``~/ollama-<ver>/``; ``~/ollama-current``
         flipped; LaunchDaemon ``com.portal5.ollama`` kickstarted (passwordless
         launchctl per the portal5 sudoers entry). Rollback flips it back.
oMLX:    ``brew upgrade`` with cleanup disabled so the previous keg survives;
         ``~/.omlx/settings.json`` + ``model_settings.json`` backed up first.
         Rollback re-points ``/opt/homebrew/opt/omlx`` (what the brew service
         runs) at the previous keg and restores the settings.

Usage:
  uv run python scripts/engine_autoupdate.py            # the daily job
  uv run python scripts/engine_autoupdate.py --now      # update now if behind
  uv run python scripts/engine_autoupdate.py --dry-run  # say what it would do
  --allow-prerelease   also install rc/beta releases (oMLX's tap ships
                       0.7.0rc1 as "stable"; the default skips it)
State: ~/.portal5/engine_update.json. Log: stdout (launchd log file).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.check_updates import (  # noqa: E402
    _get,
    _pushover,
    _semver,
    check_ollama,
    check_omlx,
)

STATE = Path.home() / ".portal5" / "engine_update.json"
CONTRACT = REPO / "scripts" / "engine_contract_check.py"
HOME = Path.home()
OLLAMA_CURRENT = HOME / "ollama-current"
OLLAMA_LIVE = HOME / "ollama-live"
TCC_WAIT_S = 1800
OLLAMA_URL = "http://localhost:11434"
OLLAMA_DAEMON = "system/com.portal5.ollama"
OMLX_URL = "http://localhost:8085"
OMLX_FORMULA = "jundot/omlx/omlx"
OMLX_OPT = Path("/opt/homebrew/opt/omlx")
OMLX_CELLAR = Path("/opt/homebrew/Cellar/omlx")
OMLX_SETTINGS = [HOME / ".omlx" / "settings.json", HOME / ".omlx" / "model_settings.json"]
WEEK = dt.timedelta(days=7)
BUSY_PATTERNS = ("tests.wfe.campaign", "tests.wfe.runner", "tests/uat", "bench_tps", "tests.uat")


def log(msg: str) -> None:
    print(f"{dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}", flush=True)


def _run(
    cmd: list[str], timeout: int = 900, env: dict | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env={**os.environ, **(env or {})}
    )


def _http_ok(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:  # noqa: S310 - localhost engine
            return json.loads(r.read().decode() or "{}")
    except Exception:
        return None


def busy() -> str | None:
    """A sweep in flight must not have its engine restarted under it."""
    out = _run(["ps", "-axo", "command"], timeout=20).stdout
    for line in out.splitlines():
        if "engine_autoupdate" in line:
            continue
        for pat in BUSY_PATTERNS:
            if pat in line:
                return line.strip()[:160]
    return None


def contract(engine: str) -> int:
    """Run the contract check for one engine. 0 = OK, 1 = failed, 2 = cannot run."""
    r = _run([sys.executable, str(CONTRACT), engine], timeout=3600)
    print(r.stdout + r.stderr, flush=True)
    return r.returncode


def _wait(pred, timeout_s: int = 180) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(3)
    return False


# ── Ollama ──────────────────────────────────────────────────────────────────


def ollama_running() -> str:
    marker = OLLAMA_CURRENT.resolve() / "VERSION"
    if marker.exists():
        return marker.read_text().strip()
    return os.readlink(OLLAMA_CURRENT).rsplit("ollama-", 1)[-1]


def _model_count() -> int:
    return len((_http_ok(f"{OLLAMA_URL}/api/tags") or {}).get("models") or [])


def ollama_latest() -> str:
    return str(
        _get("https://api.github.com/repos/ollama/ollama/releases/latest")["tag_name"]
    ).lstrip("v")


def _ollama_restart(version: str) -> bool:
    r = _run(["sudo", "-n", "launchctl", "kickstart", "-k", OLLAMA_DAEMON], timeout=60)
    if r.returncode != 0:
        log(f"ollama: kickstart failed: {r.stderr.strip()}")
        return False
    return _wait(lambda: (_http_ok(f"{OLLAMA_URL}/api/version") or {}).get("version") == version)


def ollama_install(version: str) -> Path:
    target = HOME / f"ollama-{version}"
    if (target / "ollama").exists():
        return target
    url = f"https://github.com/ollama/ollama/releases/download/v{version}/ollama-darwin.tgz"
    with tempfile.TemporaryDirectory() as td:
        tgz = Path(td) / "ollama-darwin.tgz"
        urllib.request.urlretrieve(url, tgz)  # noqa: S310 - fixed github.com release host
        staging = Path(td) / "x"
        staging.mkdir()
        with tarfile.open(tgz) as tf:
            tf.extractall(staging, filter="data")
        if not (staging / "ollama").exists():
            raise RuntimeError(f"release {version} tarball has no top-level ollama binary")
        r = _run([str(staging / "ollama"), "--version"], timeout=30)
        if version not in (r.stdout + r.stderr):
            raise RuntimeError(f"unpacked binary does not report {version}: {r.stdout}{r.stderr}")
        shutil.move(str(staging), target)
    return target


def _await_visible(engine: str, count, expected: int, version: str, restart) -> bool:
    """macOS asks the user before a NEW binary may read the external data01
    volume (the popup seen on every Ollama upgrade, and on oMLX upgrades that
    bring a new Homebrew Python): until someone clicks Allow, the engine answers
    with no models. Detect that, ask for the click, and wait."""
    if count() >= expected:
        return True
    _alert(
        f"{engine} {version}: approve data01 access on the Mac",
        f"{engine} sees {count()}/{expected} models — a macOS permission popup is "
        "waiting for 'Allow'. The update waits 30 min, then rolls back and retries tomorrow.",
        high=True,
    )
    kicked = False
    deadline = time.monotonic() + TCC_WAIT_S
    while time.monotonic() < deadline:
        if count() >= expected:
            log(f"{engine}: data01 access approved ({count()} models)")
            return True
        if not kicked and time.monotonic() > deadline - TCC_WAIT_S / 2:
            restart()  # some grants only take effect for a freshly started process
            kicked = True
        time.sleep(10)
    return False


def ollama_switch(version: str, expected_models: int) -> str:
    """Make `version` live and restart. Returns "ok", "restart_failed" or "tcc".

    The binary always runs from ONE real path, ~/ollama-live/ollama, whatever
    the version: macOS keys a bare executable's volume-access grant to its path
    plus its Developer ID requirement (identical across Ollama releases), so a
    stable path lets one approval cover every future upgrade. Versions stay
    archived as ~/ollama-<ver>/ for rollback."""
    staging = OLLAMA_LIVE.with_name("ollama-live.new")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(HOME / f"ollama-{version}", staging, symlinks=True)
    (staging / "VERSION").write_text(version + "\n")
    prev = OLLAMA_LIVE.with_name("ollama-live.prev")
    shutil.rmtree(prev, ignore_errors=True)
    if OLLAMA_LIVE.exists():
        OLLAMA_LIVE.rename(prev)
    staging.rename(OLLAMA_LIVE)
    shutil.rmtree(prev, ignore_errors=True)
    if not (OLLAMA_CURRENT.is_symlink() and OLLAMA_CURRENT.resolve() == OLLAMA_LIVE):
        tmp = HOME / ".ollama-current.tmp"
        if tmp.is_symlink() or tmp.exists():
            tmp.unlink()
        tmp.symlink_to(OLLAMA_LIVE)
        tmp.replace(OLLAMA_CURRENT)  # atomic
    if not _ollama_restart(version):
        return "restart_failed"
    visible = _await_visible(
        "ollama", _model_count, expected_models, version, lambda: _ollama_restart(version)
    )
    return "ok" if visible else "tcc"


# ── oMLX ────────────────────────────────────────────────────────────────────


def omlx_running() -> str:
    return os.readlink(OMLX_OPT).rstrip("/").rsplit("/", 1)[-1]


def omlx_latest() -> str:
    _run(["brew", "update", "--quiet"], timeout=600)
    info = json.loads(_run(["brew", "info", "--json=v2", OMLX_FORMULA], timeout=120).stdout)
    return str(info["formulae"][0]["versions"]["stable"])


def _omlx_restart() -> bool:
    r = _run(["brew", "services", "restart", OMLX_FORMULA], timeout=120)
    if r.returncode != 0:
        log(f"omlx: brew services restart failed: {r.stderr.strip()}")
        return False
    return _wait(lambda: _http_ok(f"{OMLX_URL}/health") is not None)


def omlx_backup(tag: str) -> None:
    for f in OMLX_SETTINGS:
        if f.exists():
            shutil.copy2(f, f.with_name(f"{f.name}.autoupdate-{tag}"))


def omlx_restore(tag: str) -> None:
    for f in OMLX_SETTINGS:
        b = f.with_name(f"{f.name}.autoupdate-{tag}")
        if b.exists():
            shutil.copy2(b, f)


def omlx_model_count() -> int:
    pool = (_http_ok(f"{OMLX_URL}/health") or {}).get("engine_pool") or {}
    return int(pool.get("model_count") or 0)


def omlx_upgrade(expected_models: int) -> str:
    """brew upgrade + restart. Returns "ok", "failed" or "tcc" (data01 popup)."""
    r = _run(
        ["brew", "upgrade", OMLX_FORMULA], timeout=1800, env={"HOMEBREW_NO_INSTALL_CLEANUP": "1"}
    )
    if r.returncode != 0:
        log(f"omlx: brew upgrade failed: {r.stderr.strip()[-400:]}")
        return "failed"
    if not _omlx_restart():
        return "failed"
    visible = _await_visible(
        "omlx", omlx_model_count, expected_models, omlx_running(), _omlx_restart
    )
    return "ok" if visible else "tcc"


def omlx_point_at(version: str) -> bool:
    """Re-point the service's opt symlink at a kept keg (rollback)."""
    if not (OMLX_CELLAR / version).is_dir():
        log(f"omlx: keg {version} is gone — cannot roll back")
        return False
    tmp = OMLX_OPT.with_name("omlx.autoupdate.tmp")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(Path("../Cellar/omlx") / version)
    tmp.replace(OMLX_OPT)
    return _omlx_restart()


# ── orchestration ───────────────────────────────────────────────────────────


def _state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1))


def _alert(title: str, msg: str, high: bool = False) -> None:
    log(f"{title}: {msg}")
    _pushover(title, msg, high=high)


_PRERELEASE = re.compile(r"(rc|alpha|beta|dev|pre)\d*", re.IGNORECASE)


def update_engine(engine: str, state: dict, dry_run: bool, allow_prerelease: bool = False) -> bool:
    """Update one engine if behind. Returns True when it must be retried on the
    NEXT daily run rather than a week later (the data01 approval was not given)."""
    running_fn, latest_fn = {
        "ollama": (ollama_running, ollama_latest),
        "omlx": (omlx_running, omlx_latest),
    }[engine]
    old, new = running_fn(), latest_fn()
    rejected = state.setdefault("rejected", {}).setdefault(engine, [])
    if _semver(new) <= _semver(old):
        log(f"{engine}: {old} is current")
        return False
    if _PRERELEASE.search(new) and not allow_prerelease:
        log(f"{engine}: {new} is a pre-release — not auto-installed (--allow-prerelease)")
        return False
    if new in rejected:
        log(f"{engine}: {new} available but previously REJECTED by the contract — skipping")
        return False
    log(f"{engine}: updating {old} -> {new}" + (" (dry run)" if dry_run else ""))
    if dry_run:
        return False
    tag = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    tcc = False
    try:
        if engine == "ollama":
            ollama_install(new)
            outcome = ollama_switch(new, _model_count())
            switched, tcc = outcome == "ok", outcome == "tcc"
        else:
            omlx_backup(tag)
            outcome = omlx_upgrade(omlx_model_count())
            switched, tcc = outcome == "ok", outcome == "tcc"
            new = omlx_running() if switched else new
    except Exception as e:
        switched = False
        log(f"{engine}: install failed: {e}")
    rc = contract(engine) if switched else 2
    entry = {"utc": tag, "from": old, "to": new, "contract_rc": rc}
    if rc == 0:
        state.setdefault("history", []).append(entry | {"result": "updated"})
        _alert(
            f"{engine} updated {old} -> {new}", "engine contract passed — values reach the model"
        )
        return False
    # Roll back, and prove the old version still satisfies the contract.
    back = ollama_switch(old, 1) == "ok" if engine == "ollama" else omlx_point_at(old)
    if engine == "omlx":
        omlx_restore(tag)
        back = _omlx_restart() and back
    rc_old = contract(engine) if back else 2
    if tcc:
        # Nobody clicked Allow — not a verdict on the release. Retry tomorrow.
        state.setdefault("history", []).append(entry | {"result": "awaiting_approval"})
        _alert(
            f"{engine} {new}: data01 approval not given — rolled back to {old}",
            "Will retry on the next daily run; approve the macOS popup when it appears.",
            high=True,
        )
        return True
    rejected.append(new)
    state.setdefault("history", []).append(entry | {"result": "rolled_back", "rollback_rc": rc_old})
    _alert(
        f"{engine} {new} REJECTED — rolled back to {old}",
        f"contract rc={rc} on {new}; rollback {'OK' if rc_old == 0 else f'NEEDS ATTENTION (rc={rc_old})'}. "
        f"{new} will not be retried; clear it from {STATE} to retry.",
        high=True,
    )
    return False


def main(argv: list[str]) -> int:
    now, dry_run = "--now" in argv, "--dry-run" in argv
    engines = [a for a in argv if not a.startswith("-")] or ["ollama", "omlx"]
    state = _state()
    who = busy()
    if who:
        log(f"deferring: a sweep is running ({who})")
        return 0
    # Daily: re-prove the contract whenever a version changed by any route.
    r = _run([sys.executable, str(CONTRACT), "--if-changed", *engines], timeout=7200)
    print(r.stdout + r.stderr, flush=True)
    last = state.get("last_update_run")
    due = now or not last or dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(last) >= WEEK
    security = {
        rep.name for rep in (check_ollama(), check_omlx()) if rep.actionable and rep.security_in_gap
    }
    retry_soon = False
    for engine in engines:
        if due or engine in security:
            if engine in security and not due:
                log(f"{engine}: security-flagged update — not waiting for the weekly window")
            retry_soon |= update_engine(engine, state, dry_run, "--allow-prerelease" in argv)
    if due and not dry_run and not retry_soon:
        state["last_update_run"] = dt.datetime.now(dt.UTC).isoformat()
    _save(state)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
