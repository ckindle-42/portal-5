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

Ollama:  release tarball unpacked to ``~/.portal5/engines/ollama-<ver>/`` (live + previous kept); ``~/ollama-current``
         flipped; LaunchDaemon ``com.portal5.ollama`` kickstarted (passwordless
         launchctl per the portal5 sudoers entry). Rollback flips it back.
oMLX:    installs GitHub release wheels into a staged copy of ``~/omlx-live/venv``
         when ``com.portal5.omlx`` is loaded; the Homebrew service remains a
         fallback until cutover. ``~/.omlx/settings.json`` + ``model_settings.json``
         are backed up first. Rollback reinstalls the previous wheel and restores
         those settings.

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
from scripts.omlx_venv_install import (
    activate_venv,
    relocate_venv_entrypoints,
    stage_venv_upgrade,
    venv_path,
)

STATE = Path.home() / ".portal5" / "engine_update.json"
CONTRACT = REPO / "scripts" / "engine_contract_check.py"
HOME = Path.home()
OLLAMA_CURRENT = HOME / "ollama-current"
OLLAMA_LIVE = HOME / "ollama-live"
OLLAMA_ARCHIVE = HOME / ".portal5" / "engines"
TCC_WAIT_S = 1800
OLLAMA_URL = "http://localhost:11434"
OLLAMA_DAEMON = "system/com.portal5.ollama"
OMLX_URL = "http://localhost:8085"
OMLX_FORMULA = "jundot/omlx/omlx"
OMLX_OPT = Path("/opt/homebrew/opt/omlx")
OMLX_CELLAR = Path("/opt/homebrew/Cellar/omlx")
OMLX_VENV = venv_path()
OMLX_VENV_LABEL = "com.portal5.omlx"
OMLX_BREW_LABEL = "sh.brew.omlx"
OMLX_SETTINGS = [HOME / ".omlx" / "settings.json", HOME / ".omlx" / "model_settings.json"]
WEEK = dt.timedelta(days=7)
# wfe_campaign.sh / wfe_supervise cover the seconds between arms (only bash is alive then) and
# the gap between a chained screen and its confirm.
BUSY_PATTERNS = (
    "tests.wfe.campaign",
    "tests.wfe.runner",
    "wfe_campaign.sh",
    "wfe_supervise",
    "tests/uat",
    "bench_tps",
    "tests.uat",
)


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
    log(f"{engine}: running contract check (real generations, takes several minutes)")
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


def _ollama_archived(version: str) -> Path:
    new, legacy = OLLAMA_ARCHIVE / f"ollama-{version}", HOME / f"ollama-{version}"
    return legacy if not new.exists() and legacy.exists() else new


def ollama_prune(keep: set[str]) -> None:
    for root in (OLLAMA_ARCHIVE, HOME):
        for d in root.glob("ollama-[0-9]*"):
            if d.is_dir() and not d.is_symlink() and d.name.removeprefix("ollama-") not in keep:
                log(f"ollama: pruning archived release {d}")
                shutil.rmtree(d, ignore_errors=True)


def ollama_install(version: str) -> Path:
    target = _ollama_archived(version)
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
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), target)
    return target


def _repin_router() -> None:
    """An Ollama restart drops the router model's keep_alive:-1 pin. The pipeline
    only re-warms it on the next routed request, so until then OWUI's task model
    (`task-router`, same tag) loads cold. Load it pinned now; the routing prompt
    prefix still warms on the first routed request."""
    model = os.environ.get("LLM_ROUTER_MODEL", "")
    if not model:
        log("ollama: LLM_ROUTER_MODEL unset — router NOT re-pinned (export it, or source .env)")
        return
    body = json.dumps({"model": model, "keep_alive": -1}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=300).read()  # noqa: S310 - localhost
        log(f"ollama: router model re-pinned ({model})")
    except Exception as e:
        log(f"ollama: router re-pin failed — pipeline re-warms on the next request: {e}")


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
    archived under ~/.portal5/engines/ollama-<ver>/ for rollback."""
    staging = OLLAMA_LIVE.with_name("ollama-live.new")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(_ollama_archived(version), staging, symlinks=True)
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


def omlx_venv_active() -> bool:
    if not (OMLX_VENV / "bin" / "python").is_file():
        return False
    return (
        _run(["launchctl", "print", f"gui/{os.getuid()}/{OMLX_VENV_LABEL}"], timeout=10).returncode
        == 0
    )


def omlx_service_label() -> str:
    return OMLX_VENV_LABEL if omlx_venv_active() else OMLX_BREW_LABEL


def omlx_running() -> str:
    if omlx_venv_active():
        r = _run(
            [
                str(OMLX_VENV / "bin" / "python"),
                "-c",
                "import importlib.metadata as m; print(m.version('omlx'))",
            ],
            timeout=20,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        raise RuntimeError(f"could not read oMLX venv version: {r.stderr.strip()}")
    return os.readlink(OMLX_OPT).rstrip("/").rsplit("/", 1)[-1]


def omlx_latest() -> str:
    release = _get("https://api.github.com/repos/jundot/omlx/releases/latest")
    return str(release["tag_name"]).removeprefix("v")


def _omlx_restart() -> bool:
    if omlx_service_label() == OMLX_VENV_LABEL:
        r = _run(
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{OMLX_VENV_LABEL}"],
            timeout=120,
        )
    else:
        r = _run(["brew", "services", "restart", OMLX_FORMULA], timeout=120)
    if r.returncode != 0:
        log(f"omlx: service restart failed: {r.stderr.strip()}")
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


def omlx_upgrade(version: str, expected_models: int) -> str:
    """Install a release wheel or use brew fallback; return update outcome."""
    if omlx_venv_active():
        stage = stage_venv_upgrade(version, OMLX_VENV, _run)
        activate_venv(stage, OMLX_VENV)
        if not _omlx_restart():
            return "failed"
        visible = _await_visible("omlx", omlx_model_count, expected_models, version, _omlx_restart)
        return "ok" if visible else "tcc"
    r = _run(
        ["brew", "upgrade", OMLX_FORMULA], timeout=1800, env={"HOMEBREW_NO_INSTALL_CLEANUP": "1"}
    )
    if r.returncode != 0:
        log(f"omlx: brew upgrade failed: {r.stderr.strip()[-400:]}")
        return "failed"
    installed = omlx_running()
    if installed != version:
        log(f"omlx: Homebrew has {installed}; GitHub release {version} is not in the tap yet")
        return "unavailable"
    if not _omlx_restart():
        return "failed"
    visible = _await_visible(
        "omlx", omlx_model_count, expected_models, omlx_running(), _omlx_restart
    )
    return "ok" if visible else "tcc"


def omlx_prune(keep: set[str]) -> None:
    if omlx_venv_active():
        for suffix in ("previous", "failed", "new"):
            shutil.rmtree(OMLX_VENV.with_name(f"{OMLX_VENV.name}.{suffix}"), ignore_errors=True)
        return
    for d in OMLX_CELLAR.glob("*"):
        if d.is_dir() and not d.is_symlink() and d.name not in keep:
            log(f"omlx: pruning old keg {d}")
            shutil.rmtree(d, ignore_errors=True)


def omlx_point_at(version: str) -> bool:
    """Restore a previous service version and restart the active service."""
    if omlx_venv_active():
        if omlx_running() == version:
            return _omlx_restart()
        previous = OMLX_VENV.with_name(f"{OMLX_VENV.name}.previous")
        if not previous.is_dir():
            log(f"omlx: prior venv for {version} is gone — cannot roll back")
            return False
        stage = stage_venv_upgrade(version, previous, _run)
        relocate_venv_entrypoints(stage, OMLX_VENV)
        failed = OMLX_VENV.with_name(f"{OMLX_VENV.name}.failed")
        shutil.rmtree(failed, ignore_errors=True)
        if OMLX_VENV.exists():
            OMLX_VENV.rename(failed)
        try:
            stage.rename(OMLX_VENV)
        except OSError:
            if failed.exists() and not OMLX_VENV.exists():
                failed.rename(OMLX_VENV)
            raise
        return _omlx_restart()
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


def _update_target(engine: str, state: dict, allow_prerelease: bool) -> tuple[str, str] | None:
    running_fn, latest_fn = {
        "ollama": (ollama_running, ollama_latest),
        "omlx": (omlx_running, omlx_latest),
    }[engine]
    old, new = running_fn(), latest_fn()
    rejected = state.setdefault("rejected", {}).setdefault(engine, [])
    if _semver(new) <= _semver(old):
        log(f"{engine}: {old} is current")
        return None
    if _PRERELEASE.search(new) and not allow_prerelease:
        log(f"{engine}: {new} is a pre-release — not auto-installed (--allow-prerelease)")
        return None
    if new in rejected:
        log(f"{engine}: {new} available but previously REJECTED by the contract — skipping")
        return None
    return old, new


def _attempt_update(engine: str, old: str, new: str, tag: str) -> tuple[str, bool, bool, str, str]:
    tcc = False
    error = ""
    try:
        if engine == "ollama":
            ollama_install(new)
            outcome = ollama_switch(new, _model_count())
            switched, tcc = outcome == "ok", outcome == "tcc"
        else:
            omlx_backup(tag)
            outcome = omlx_upgrade(new, omlx_model_count())
            switched, tcc = outcome == "ok", outcome == "tcc"
            new = omlx_running() if switched else new
    except Exception as e:
        switched, outcome = False, "failed"
        error = str(e)
        log(f"{engine}: install failed: {e}")
    return outcome, switched, tcc, new, error


def _defer_failed_update(
    engine: str,
    outcome: str,
    switched: bool,
    tcc: bool,
    state: dict,
    old: str,
    new: str,
    tag: str,
    error: str,
) -> bool:
    if engine == "omlx" and outcome == "unavailable":
        state.setdefault("history", []).append(
            {"utc": tag, "from": old, "to": new, "result": "release_unavailable"}
        )
        return True
    if engine == "omlx" and not switched and not tcc and omlx_running() == old:
        omlx_restore(tag)
        detail = f"{error[:400]}\n" if error else ""
        _alert(
            f"omlx {new}: install did not switch the active version",
            f"{detail}Will retry on the next daily run.",
        )
        state.setdefault("history", []).append(
            {"utc": tag, "from": old, "to": new, "result": "install_failed"}
        )
        return True
    return False


def _record_success(engine: str, old: str, new: str, state: dict, entry: dict) -> None:
    if engine == "ollama":
        _repin_router()
    (ollama_prune if engine == "ollama" else omlx_prune)({old, new})
    state.setdefault("history", []).append(entry | {"result": "updated"})
    _alert(f"{engine} updated {old} -> {new}", "engine contract passed — values reach the model")


def _rollback_engine(engine: str, old: str, new: str, tag: str) -> int:
    try:
        back = ollama_switch(old, 1) == "ok" if engine == "ollama" else omlx_point_at(old)
    except Exception as e:
        back = False
        log(f"{engine}: rollback install failed: {e}")
    if engine == "omlx":
        omlx_restore(tag)
        try:
            back = _omlx_restart() and back
        except Exception as e:
            back = False
            log(f"{engine}: rollback restart failed: {e}")
    rc_old = contract(engine) if back else 2
    if engine == "omlx" and rc_old == 0:
        omlx_prune({old, new})
    if engine == "ollama":
        _repin_router()
    return rc_old


def _record_rollback(
    engine: str, old: str, new: str, state: dict, entry: dict, rc: int, rc_old: int, tcc: bool
) -> bool:
    if tcc:
        state.setdefault("history", []).append(entry | {"result": "awaiting_approval"})
        _alert(
            f"{engine} {new}: data01 approval not given — rolled back to {old}",
            "Will retry on the next daily run; approve the macOS popup when it appears.",
            high=True,
        )
        return True
    state.setdefault("rejected", {}).setdefault(engine, []).append(new)
    state.setdefault("history", []).append(entry | {"result": "rolled_back", "rollback_rc": rc_old})
    _alert(
        f"{engine} {new} REJECTED — rolled back to {old}",
        f"contract rc={rc} on {new}; rollback {'OK' if rc_old == 0 else f'NEEDS ATTENTION (rc={rc_old})'}. "
        f"{new} will not be retried; clear it from {STATE} to retry.",
        high=True,
    )
    return False


def update_engine(engine: str, state: dict, dry_run: bool, allow_prerelease: bool = False) -> bool:
    """Update one engine; return true when a retry is due tomorrow."""
    target = _update_target(engine, state, allow_prerelease)
    if target is None:
        return False
    old, new = target
    log(f"{engine}: updating {old} -> {new}" + (" (dry run)" if dry_run else ""))
    if dry_run:
        return False
    tag = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    outcome, switched, tcc, new, error = _attempt_update(engine, old, new, tag)
    if _defer_failed_update(engine, outcome, switched, tcc, state, old, new, tag, error):
        return True
    log(f"{engine}: switched={switched}" + (" (waited on data01 approval)" if tcc else ""))
    rc = contract(engine) if switched else 2
    entry = {"utc": tag, "from": old, "to": new, "contract_rc": rc}
    if rc == 0:
        _record_success(engine, old, new, state, entry)
        return False
    rc_old = _rollback_engine(engine, old, new, tag)
    return _record_rollback(engine, old, new, state, entry, rc, rc_old, tcc)


def main(argv: list[str]) -> int:
    now, dry_run = "--now" in argv, "--dry-run" in argv
    engines = [a for a in argv if not a.startswith("-")] or ["ollama", "omlx"]
    state = _state()
    who = busy()
    if who:
        log(f"deferring: a sweep is running ({who})")
        return 0
    # Daily: re-prove the contract whenever a version changed by any route.
    log(
        f"checking whether {', '.join(engines)} changed since last verified (may run the contract check)"
    )
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
