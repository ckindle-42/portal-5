#!/usr/bin/env python3
"""Apply security-motivated upgrades that the engine/image jobs deliberately leave alone.

  deps  Raise vulnerable ``uv.lock`` packages to the lowest version OSV.dev lists as
        fixed. Resolved and tested in a throwaway copy of HEAD (own venv, full unit
        suite); only a lock that resolves, removes vulns, and passes is committed
        (``uv.lock`` only, never pushed). The live ``.venv`` is NOT touched — a
        venv that diverges from its lock has destroyed runtimes before — so the
        weekly ``python-deps`` check reports "behind" until you review + ``uv sync``.
  pins  Bump pinned compose images (Grafana, Prometheus, Wazuh) to the newest PATCH
        of their current major.minor that exists on Docker Hub for arm64, recreate
        the running service, roll the pin back if it does not come up, and commit
        the compose file. Never crosses a minor/major line.

``--dry-run`` reports the plan only. Defers while a sweep/UAT/bench is running or
when the files it would commit already have uncommitted changes. Weekly from
launchd (``deploy/launchd/com.portal5.security-update.plist``).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.check_updates import (  # noqa: E402
    _FLOATING_TAGS,
    COMPOSE_FILES,
    _locked_packages,
    _pushover,
    _semver,
    osv_query,
    vuln_fixes,
)
from scripts.engine_autoupdate import busy, log  # noqa: E402

LOCKSTEP = ("wazuh/wazuh-manager", "wazuh/wazuh-indexer", "wazuh/wazuh-dashboard")
PINNED = ("grafana/grafana", "prom/prometheus", *LOCKSTEP)
ATTRIBUTION = (
    "\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
    "\nClaude-Session: https://claude.ai/code/session_01DCQmSP3YR5WPrepAP5CSYr"
)


def _sh(cmd: list[str], cwd: Path = REPO, timeout: int = 900, env: dict | None = None):
    import os

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
        env={**os.environ, **(env or {})},
    )


def _tool(name: str, *fallbacks: str) -> str:
    return shutil.which(name) or next((f for f in fallbacks if Path(f).exists()), name)


UV = _tool("uv", str(Path.home() / ".local/bin/uv"))
DOCKER = _tool("docker", "/usr/local/bin/docker")


def _dirty(*paths: Path) -> bool:
    return bool(_sh(["git", "status", "--porcelain", "--", *map(str, paths)]).stdout.strip())


def _commit(msg: str, *paths: Path) -> bool:
    _sh(["git", "add", "--", *map(str, paths)])
    r = _sh(["git", "commit", "-m", msg + ATTRIBUTION, "--", *map(str, paths)], timeout=1800)
    if r.returncode:
        log(f"commit failed:\n{(r.stdout + r.stderr)[-600:]}")
    return r.returncode == 0


# ── deps ─────────────────────────────────────────────────────────────────────
def _lock_with(work: Path, floors: dict[str, str], op: str) -> bool:
    cmd = [UV, "lock"]
    for name, fixed in floors.items():
        cmd += ["--upgrade-package", f"{name}{op}{fixed}"]
    return _sh(cmd, cwd=work, timeout=600).returncode == 0


def _resolve(work: Path, floors: dict[str, str]) -> dict[str, str]:
    """Apply as many floors as resolve together; returns the ones applied."""
    pristine = (work / "uv.lock").read_text()
    for op in ("==", ">="):
        if _lock_with(work, floors, op):
            return floors
        (work / "uv.lock").write_text(pristine)
    applied: dict[str, str] = {}
    for name, fixed in floors.items():
        if _lock_with(work, {**applied, name: fixed}, ">="):
            applied[name] = fixed
        else:
            (work / "uv.lock").write_text(pristine)
            if applied:
                _lock_with(work, applied, ">=")
    return applied


def _fixable_count(lock_dir: Path | None) -> int:
    import scripts.check_updates as cu

    saved = cu.REPO_ROOT
    cu.REPO_ROOT = lock_dir or REPO
    try:
        fixes = vuln_fixes(osv_query(_locked_packages()))
    finally:
        cu.REPO_ROOT = saved
    return sum(bool(f) for _, f, _ in fixes.values())


def deps(dry_run: bool) -> int:
    hits = osv_query(_locked_packages())
    floors: dict[str, str] = {}
    for (name, _), (_, fixed, _) in vuln_fixes(hits).items():
        if fixed and (name not in floors or _semver(fixed) > _semver(floors[name])):
            floors[name] = fixed
    if not floors:
        log("deps: no vulnerable package has a published fix")
        return 0
    log(
        f"deps: {len(floors)} package(s) with a fix: "
        + ", ".join(f"{n}>={v}" for n, v in floors.items())
    )
    if dry_run:
        return 0
    if _dirty(REPO / "uv.lock", REPO / "pyproject.toml"):
        log("deps: uv.lock/pyproject.toml have uncommitted changes — deferring")
        return 0
    before = _fixable_count(None)
    with tempfile.TemporaryDirectory(prefix="portal-secdeps-") as tmp:
        # A real clone, not `git archive`: repo-introspecting tests need .git.
        work = Path(tmp) / "src"
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(REPO), str(work)], check=True)
        applied = _resolve(work, floors)
        skipped = sorted(set(floors) - set(applied))
        if not applied or (work / "uv.lock").read_text() == (REPO / "uv.lock").read_text():
            _pushover(
                "Security deps", f"no resolvable upgrade (skipped: {', '.join(skipped)})", True
            )
            log(f"deps: nothing resolvable; skipped {skipped}")
            return 0
        after = _fixable_count(work)
        if after >= before:
            log(f"deps: new lock leaves {after} fixable vulns (was {before}) — rejecting")
            _pushover("Security deps", f"upgrade rejected: fixable vulns {before}->{after}", True)
            return 0
        env = {"UV_PROJECT_ENVIRONMENT": str(Path(tmp) / "venv")}
        sync = _sh([UV, "sync", "--all-extras", "--frozen"], cwd=work, timeout=3600, env=env)
        test = (
            _sh(
                [UV, "run", "--frozen", "pytest", "tests/unit/", "-q", "-x", "--tb=short"],
                cwd=work,
                timeout=3600,
                env=env,
            )
            if sync.returncode == 0
            else sync
        )
        if test.returncode:
            log("deps: validation FAILED — lock not applied\n" + (test.stdout + test.stderr)[-800:])
            _pushover(
                "Security deps", "upgrade failed validation in a scratch venv; lock unchanged", True
            )
            return 0
        shutil.copy(work / "uv.lock", REPO / "uv.lock")
    msg = f"fix(deps): raise {len(applied)} vulnerable locked package(s) to patched versions"
    body = "\n".join(f"- {n} >= {v}" for n, v in applied.items())
    if skipped:
        body += "\n\nNot resolvable alongside the rest: " + ", ".join(skipped)
    ok = _commit(f"{msg}\n\n{body}", REPO / "uv.lock")
    note = (
        f"uv.lock committed ({len(applied)} pkgs, fixable vulns {before}->{after}); "
        "review then `uv sync --all-extras` to apply to the live venv"
        if ok
        else "uv.lock updated and validated but the commit failed — left in the working tree"
    )
    log("deps: " + note)
    _pushover("Security deps", note, not ok)
    return 0


# ── pins ─────────────────────────────────────────────────────────────────────
def _hub_patches(repo: str, tag: str) -> list[str]:
    """Same-major.minor patch tags above `tag` that have an arm64 image on Docker Hub."""
    prefix = "v" if tag.startswith("v") else ""
    major, minor = _semver(tag)[:2]
    url = f"https://hub.docker.com/v2/repositories/{repo}/tags?" + urllib.parse.urlencode(
        {"name": f"{prefix}{major}.{minor}.", "page_size": 100}
    )
    with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310 - fixed hub.docker.com host
        results = json.loads(r.read().decode())["results"]
    found = []
    for t in results:
        n = t["name"]
        if re.fullmatch(rf"{prefix}{major}\.{minor}\.\d+", n) and any(
            i.get("architecture") == "arm64" for i in t.get("images", [])
        ):
            found.append(n)
    return sorted((n for n in found if _semver(n) > _semver(tag)), key=_semver)


def _compose_services(file: Path) -> dict[str, str]:
    r = _sh(
        [DOCKER, "compose", "-f", str(file), "--profile", "*", "config", "--format", "json"],
        cwd=file.parent,
        timeout=120,
    )
    try:
        return {s["image"]: n for n, s in json.loads(r.stdout)["services"].items() if "image" in s}
    except (ValueError, KeyError):
        return {}


def _service_up(file: Path, svc: str, want: bool = True, wait: int = 180) -> bool:
    deadline = time.monotonic() + wait
    while True:
        r = _sh(
            [DOCKER, "compose", "-f", str(file), "ps", "--status", "running", "-q", svc],
            cwd=file.parent,
            timeout=60,
        )
        if bool(r.stdout.strip()) == want or time.monotonic() > deadline:
            return bool(r.stdout.strip()) == want
        time.sleep(5)


def _recreate(file: Path, svc: str) -> bool:
    c = ["docker", "compose", "-f", str(file)]
    c[0] = DOCKER
    return (
        _sh([*c, "pull", svc], cwd=file.parent).returncode == 0
        and _sh([*c, "up", "-d", "--no-deps", svc], cwd=file.parent).returncode == 0
        and _service_up(file, svc)
    )


def _pin_plan(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """(current {repo: tag}, wanted {repo: newer patch tag}) for the pinned images in a compose file."""
    refs = {
        m.group(1): m.group(2)
        for m in re.finditer(r"^\s*image:\s*(\S+?):(\S+)\s*$", text, re.MULTILINE)
        if m.group(1) in PINNED and m.group(2) not in _FLOATING_TAGS
    }
    plan: dict[str, str] = {}
    for repo, tag in refs.items():
        try:
            newer = _hub_patches(repo, tag)
        except (OSError, ValueError, KeyError) as e:
            log(f"pins: {repo}: Docker Hub lookup failed: {e}")
            continue
        if newer:
            plan[repo] = newer[-1]
    # All-or-nothing: the Wazuh stack members must agree on a version.
    members = [r for r in LOCKSTEP if r in refs]
    if members and not all(plan.get(r) == plan.get(members[0]) for r in members):
        for r in members:
            plan.pop(r, None)
    return refs, plan


def _apply_pins(file: Path, text: str, refs: dict[str, str], plan: dict[str, str]) -> None:
    services = _compose_services(file)
    new_text = text
    for repo, tag in plan.items():
        old, new = f"image: {repo}:{refs[repo]}", f"image: {repo}:{tag}"
        if new_text.count(old) != 1:
            log(f"pins: {old!r} not unique in {file.name} — skipping {repo}")
            plan.pop(repo)
            continue
        new_text = new_text.replace(old, new)
    file.write_text(new_text)
    running = [
        services[f"{r}:{refs[r]}"]
        for r in plan
        if f"{r}:{refs[r]}" in services and _service_up(file, services[f"{r}:{refs[r]}"], wait=1)
    ]
    failed = [svc for svc in running if not _recreate(file, svc)]
    if failed:
        file.write_text(text)
        for svc in failed:
            _recreate(file, svc)
        msg = f"pin bump rolled back — {', '.join(failed)} did not come up"
        log("pins: " + msg)
        _pushover("Security pins", msg, True)
        return
    ok = _commit(
        "fix(deploy): bump pinned image patch versions\n\n"
        + "\n".join(f"- {r}: {refs[r]} -> {t}" for r, t in plan.items()),
        file,
    )
    note = ", ".join(f"{r} {refs[r]}->{t}" for r, t in plan.items())
    _pushover(
        "Security pins", note + ("" if ok else " (commit failed; left in working tree)"), not ok
    )


def pins(dry_run: bool) -> int:
    for file in COMPOSE_FILES:
        text = file.read_text()
        refs, plan = _pin_plan(text)
        if not plan:
            log(f"pins: {file.name}: already on the newest patch")
            continue
        log(f"pins: {file.name}: " + ", ".join(f"{r}:{refs[r]} -> {t}" for r, t in plan.items()))
        if dry_run:
            continue
        if _dirty(file):
            log(f"pins: {file.name} has uncommitted changes — deferring")
            continue
        _apply_pins(file, text, refs, plan)
    return 0


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    which = [a for a in argv if not a.startswith("-")] or ["deps", "pins"]
    if (who := busy()) is not None:
        log(f"deferring: a sweep is running ({who})")
        return 0
    for w in which:
        {"deps": deps, "pins": pins}[w](dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
