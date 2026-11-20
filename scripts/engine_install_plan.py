#!/usr/bin/env python3
"""Host-engine pip plan: latest compatible deps, without downgrades or core bumps.

``uv pip install --upgrade`` re-resolves the named set and its dependencies, so
an advisory floor on pillow also moved torch, transformers, diffusers,
huggingface-hub, and numpy (2026-11-19 install-music). The plan is anchored in
the installed venv: core pins from ``uv pip freeze`` stay held, and installed
packages are upgraded to the latest compatible stable releases without crossing
their installed version floors. The service helper refreshes the sweep before
apply. A resolve conflict against a held pin drops the offending requirement.
``--dry-run`` prints the argv and resolves without installing.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from packaging.version import Version

_NAME = re.compile(r"^\s*([A-Za-z0-9_.-]+)")
_ROW = re.compile(r"^\|(.+)\|\s*$")
_UPSTREAM_EXACT = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.\-]+\])?)"
    r"\s*==(?!=)\s*([^;\s]+)(?:\s*;\s*(.+))?$"
)
_REQ_TOKEN = re.compile(
    r"([A-Za-z0-9_.\-]+(?:\[[A-Za-z0-9_,.\-]+\])?"
    r"\s*(?:==|>=|<=|!=|~=|<|>)\s*[0-9][0-9A-Za-z._+*]*)"
)
_MAX_REFINES = 8

# torch/transformers/diffusers/hf-hub/numpy/mlx* — an engine bump, not a sweep.
_CORE_EXACT = frozenset(
    {
        "torch",
        "torchvision",
        "torchaudio",
        "transformers",
        "diffusers",
        "huggingface-hub",
        "numpy",
    }
)

SERVICE_DEPS: dict[str, tuple[str, ...]] = {
    "music": (
        "mlx-audio==0.6.6",
        "mcp>=2.0.0,<3.0.0",
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "httpx>=0.26.0",
        "pyyaml>=6.0.1",
    ),
    "mflux": (
        "mflux>=0.24.0",
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "httpx>=0.26.0",
        "pyyaml>=6.0.1",
        "starlette>=1.3.1",
        "mcp>=2.0.0,<3.0.0",
        "pillow>=13.0.0",
    ),
    "video": (
        "mcp>=2.0.0,<3.0.0",
        "starlette>=1.3.1",
        "httpx>=0.26.0",
        "pyyaml>=6.0.1",
    ),
}


def canonical_name(name: str) -> str:
    return name.lower().replace("_", "-")


def is_core_stack(name: str) -> bool:
    normalized = canonical_name(name)
    if normalized in _CORE_EXACT:
        return True
    return normalized == "mlx" or normalized.startswith("mlx-")


def requirement_name(spec: str) -> str:
    head = spec.split("[", 1)[0]
    match = _NAME.match(head)
    if match is None:
        raise ValueError(f"not a requirement: {spec}")
    return canonical_name(match.group(1))


def version_key(value: str) -> Version:
    return Version(value)


def parse_sweep_fixes(
    text: str,
) -> dict[str, dict[str, tuple[str, tuple[str, ...]]]]:
    """PyPI rows of a security-sweep report: name -> {flagged version: (fix, ids)}."""
    found: dict[str, dict[str, tuple[str, tuple[str, ...]]]] = {}
    for line in text.splitlines():
        match = _ROW.match(line.strip())
        if match is None:
            continue
        cells = [cell.strip() for cell in match.group(1).split("|")]
        if len(cells) < 7 or cells[0].casefold() != "pypi":
            continue
        _ecosystem, name, version, advisory, _severity, fixed = cells[:6]
        if not fixed or fixed in {"—", "-"}:
            continue
        rows = found.setdefault(canonical_name(name), {})
        ids = (advisory,) if advisory and advisory not in {"—", "-"} else ()
        previous = rows.get(version)
        if previous is None:
            rows[version] = (fixed, ids)
        else:
            best = max(previous[0], fixed, key=version_key)
            rows[version] = (best, tuple(dict.fromkeys(previous[1] + ids)))
    return found


def parse_upstream_floors(text: str) -> tuple[str, ...]:
    """Convert exact upstream lock exports into non-pinning version floors."""
    floors = []
    for line in text.splitlines():
        requirement = _UPSTREAM_EXACT.fullmatch(line.split(" #", 1)[0].strip())
        if requirement is None:
            continue
        name, version, marker = requirement.groups()
        floor = f"{name}>={Version(version).public}"
        if marker:
            floor += f" ; {marker}"
        floors.append(floor)
    return tuple(dict.fromkeys(floors))


def highest_fix(
    rows: dict[str, tuple[str, tuple[str, ...]]],
) -> tuple[str, tuple[str, ...]]:
    """Highest fix for a package across flagged versions, with every advisory id."""
    fix, ids = "", ()
    for _version, (candidate, row_ids) in rows.items():
        if not fix or version_key(candidate) > version_key(fix):
            fix = candidate
        ids = tuple(dict.fromkeys(ids + row_ids))
    return fix, ids


@dataclass(frozen=True)
class InstallPlan:
    service: str
    service_deps: tuple[str, ...]
    upgrades: tuple[str, ...]
    upgrade_packages: tuple[str, ...]
    refused: tuple[str, ...]
    holds: tuple[str, ...]
    floors: tuple[str, ...]
    installed: tuple[tuple[str, str], ...]
    upstream_floors: tuple[str, ...]
    satisfied: tuple[str, ...] = ()

    def requirements(self) -> list[str]:
        requirements = [*self.service_deps, *self.upgrades, *self.upstream_floors]
        names = {requirement_name(spec) for spec in requirements}
        requirements.extend(name for name, _version in self.installed if name not in names)
        return requirements

    def argv(self, python: str, constraint: str) -> list[str]:
        command = [
            "uv",
            "pip",
            "install",
            "--upgrade",
            "--resolution",
            "highest",
            "--prerelease",
            "disallow",
            "--python",
            python,
            "--constraint",
            constraint,
        ]
        command.extend(self.requirements())
        return command


def build_plan(
    service: str,
    installed: dict[str, str],
    sweep_text: str,
    upstream_text: str = "",
) -> InstallPlan:
    """Upgrade all installed packages while keeping the core and version floors."""
    if service not in SERVICE_DEPS:
        raise ValueError(f"unknown engine service {service!r}")
    deps = SERVICE_DEPS[service]
    fixes = parse_sweep_fixes(sweep_text)
    upstream_floors = parse_upstream_floors(upstream_text)
    upgrades: list[str] = []
    upgrade_packages: list[str] = []
    refused: list[str] = []
    satisfied: list[str] = []
    package_floors = {
        name: version for name, version in installed.items() if not is_core_stack(name)
    }
    for name in sorted(fixes):
        rows = fixes[name]
        current = installed.get(name)
        if current is None:
            continue
        fix, ids = highest_fix(rows)
        if is_core_stack(name):
            if version_key(current) >= version_key(fix):
                satisfied.append(f"{name}=={current} (fix {fix})")
                continue
            label = f"{name}=={fix}" + (f" ({', '.join(ids)})" if ids else "")
            refused.append(f"{label}; installed {current}; engine bump required")
            continue
        if version_key(current) >= version_key(fix):
            continue
        upgrades.append(f"{name}>={fix}")
        upgrade_packages.append(name)
        package_floors[name] = fix
    holds = tuple(
        f"{name}=={version}" for name, version in sorted(installed.items()) if is_core_stack(name)
    )
    floors = tuple(f"{name}>={version}" for name, version in sorted(package_floors.items()))
    floors += tuple(_constraint_floor(spec) for spec in upstream_floors)
    return InstallPlan(
        service,
        deps,
        tuple(upgrades),
        tuple(upgrade_packages),
        tuple(refused),
        holds,
        floors,
        tuple(sorted(installed.items())),
        upstream_floors,
        tuple(satisfied),
    )


def _constraint_floor(spec: str) -> str:
    requirement, separator, marker = spec.partition(";")
    name, _operator, version = requirement.partition(">=")
    floor = f"{requirement_name(name)}>={version.strip()}"
    return floor + (f" ; {marker.strip()}" if separator else "")


def render_plan(plan: InstallPlan, python: str) -> str:
    lines = [f"service: {plan.service}", "service deps:"]
    lines.extend(f"  {spec}" for spec in plan.service_deps)
    lines.append("upstream lock floors:")
    lines.extend(f"  {spec}" for spec in plan.upstream_floors)
    if not plan.upstream_floors:
        lines.append("  (none)")
    lines.append("security floors:")
    lines.extend(f"  {spec}" for spec in plan.upgrades)
    if not plan.upgrades:
        lines.append("  (none)")
    lines.append("refused core stack:")
    lines.extend(f"  {line}" for line in plan.refused)
    if not plan.refused:
        lines.append("  (none)")
    lines.append("already satisfied:")
    lines.extend(f"  {line}" for line in plan.satisfied)
    if not plan.satisfied:
        lines.append("  (none)")
    lines.append("held core stack:")
    lines.extend(f"  {line}" for line in plan.holds)
    if not plan.holds:
        lines.append("  (none)")
    if plan.requirements():
        shown = plan.argv(python, "<constraints>")
        lines.append("command: " + " ".join(shlex.quote(part) for part in shown))
    else:
        lines.append("command: (no pip changes)")
    return "\n".join(lines)


def read_installed(python: str) -> dict[str, str]:
    """Installed packages from the venv uv will install into (`uv pip freeze`)."""
    result = subprocess.run(
        ["uv", "pip", "freeze", "--python", python],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"cannot read packages from {python}: {result.stderr.strip()}")
    installed: dict[str, str] = {}
    for line in (result.stdout or "").splitlines():
        name, mark, version = line.partition("==")
        if not mark or _NAME.match(name) is None:
            continue
        installed[canonical_name(name)] = version.strip()
    return installed


def requirement_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _REQ_TOKEN.finditer(text):
        token = match.group(1)
        if token not in tokens:
            tokens.append(token)
    return tokens


def _token_name(token: str) -> str | None:
    match = _NAME.match(token)
    return canonical_name(match.group(1)) if match else None


def conflict_pair(tokens: list[str], plan: InstallPlan) -> tuple[str, str, str] | None:
    """Find the conflicting pair uv named: (dropped token, other token, kind)."""
    by_name: dict[str, list[str]] = {}
    for token in tokens:
        name = _token_name(token)
        if name is not None:
            by_name.setdefault(name, []).append(token)

    def pick(specs: tuple[str, ...]) -> list[str]:
        names = {requirement_name(spec) for spec in specs}
        found = [token for name in names for token in by_name.get(name, [])]
        heads = {spec.split(",", 1)[0] for spec in specs}
        return [token for token in found if token in heads] + [
            token for token in found if token not in heads
        ]

    held = pick(plan.holds)
    if held:
        other = [token for token in held if "==" in token] or held
        upgrades = pick(plan.upgrades)
        if upgrades:
            return upgrades[0], other[0], "upgrade"
        deps = pick(plan.service_deps)
        if deps:
            return deps[0], other[0], "service dep"
    upgrades = pick(plan.upgrades)
    deps = pick(plan.service_deps)
    if upgrades and deps:
        return upgrades[0], deps[0], "upgrade"
    return None


def refine_plan(plan: InstallPlan, stderr: str) -> tuple[InstallPlan, str] | None:
    """Drop the conflicting service dep or sweep fix; the held core pin stays."""
    conflict = conflict_pair(requirement_tokens(stderr), plan)
    if conflict is None:
        return None
    dropped, other, kind = conflict
    name = requirement_name(dropped)
    if kind == "upgrade":
        upgrades = tuple(spec for spec in plan.upgrades if requirement_name(spec) != name)
        packages = tuple(part for part in plan.upgrade_packages if canonical_name(part) != name)
        floors = tuple(spec for spec in plan.floors if requirement_name(spec) != name)
        installed = dict(plan.installed)
        if name in installed and not is_core_stack(name):
            floors = (*floors, f"{name}>={installed[name]}")
        refined = replace(plan, upgrades=upgrades, upgrade_packages=packages, floors=floors)
        note = f"{dropped} conflicts with {other}; dropped from this install"
        return refined, note
    deps = tuple(spec for spec in plan.service_deps if requirement_name(spec) != name)
    refused = plan.refused + (f"{dropped}; conflicts with held {other}; engine bump required",)
    refined = replace(plan, service_deps=deps, refused=refused)
    note = f"{dropped} needs newer core than held {other}; engine bump required"
    return refined, note


def parse_package_changes(
    output: str, installed: dict[str, str]
) -> tuple[tuple[str, str | None, str | None], ...]:
    removed: dict[str, str] = {}
    added: dict[str, str] = {}
    for line in output.splitlines():
        match = re.match(r"^\s*([+-])\s+([A-Za-z0-9_.-]+)==([^\s]+)\s*$", line)
        if match is None:
            continue
        action, raw_name, version = match.groups()
        target = removed if action == "-" else added
        target[canonical_name(raw_name)] = version
    changes = []
    for name in sorted(set(removed) | set(added)):
        old = removed.get(name, installed.get(name))
        new = added.get(name)
        if old != new:
            changes.append((name, old, new))
    return tuple(changes)


def _show_and_validate_changes(output: str, plan: InstallPlan) -> bool:
    changes = parse_package_changes(output, dict(plan.installed))
    planned = re.search(r"^Would install (\d+) packages?$", output, re.MULTILINE)
    if planned is not None and int(planned.group(1)) > 0 and not changes:
        print("cannot inspect resolved package changes; refusing to install")
        return False
    print("planned package changes:")
    for name, old, new in changes:
        print(f"  {name}: {old or '(new)'} -> {new or '(removed)'}")
    if not changes:
        print("  (none)")
    removals = [(name, old) for name, old, new in changes if old and new is None]
    downgrades = [
        (name, old, new)
        for name, old, new in changes
        if old is not None and new is not None and version_key(new) < version_key(old)
    ]
    for name, old in removals:
        print(
            f"  ❌ refusing package removal before install: {name} {old}; "
            "installed package would not move forward"
        )
    for name, old, new in downgrades:
        print(
            f"  ❌ refusing downgrade before install: {name} {old} -> {new}; "
            "installed version floor would be crossed"
        )
    return not removals and not downgrades


def _write_constraints(path: str, plan: InstallPlan) -> None:
    constraints = (*plan.holds, *plan.floors)
    Path(path).write_text("\n".join(constraints) + ("\n" if constraints else ""))


def _apply(plan: InstallPlan, python: str, dry_run: bool) -> int:
    print(render_plan(plan, python))
    if not plan.requirements():
        return 0
    descriptor, path = tempfile.mkstemp(prefix=f"portal5-{plan.service}-hold-", suffix=".txt")
    try:
        os.close(descriptor)
        current = plan
        for _ in range(_MAX_REFINES):
            _write_constraints(path, current)
            command = current.argv(python, path)
            check_command = [*command, "--dry-run"]
            result = subprocess.run(check_command, capture_output=True, text=True, check=False)
            output = (result.stdout or "") + (result.stderr or "")
            if output:
                print(output, end="")
            if result.returncode == 0:
                if not _show_and_validate_changes(output, current):
                    return 1
                if dry_run:
                    return 0
                applied = subprocess.run(command, capture_output=True, text=True, check=False)
                applied_output = (applied.stdout or "") + (applied.stderr or "")
                if applied_output:
                    print(applied_output, end="")
                if applied.returncode == 0:
                    return 0
                result = applied
            refined = refine_plan(current, result.stderr)
            if refined is None:
                tokens = requirement_tokens(result.stderr)
                names = ", ".join(tokens[:8]) or "(no requirement tokens in output)"
                print(f"conflicting requirements: {names}", file=sys.stderr)
                print(f"dependency install failed ({result.returncode})", file=sys.stderr)
                return result.returncode
            current, note = refined
            print(f"  ⚠️  {note}")
            print(render_plan(current, python))
        print(
            "resolve still unsatisfiable after dropping conflicting requirements", file=sys.stderr
        )
        return 1
    finally:
        os.unlink(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, choices=sorted(SERVICE_DEPS))
    parser.add_argument("--python", required=True)
    parser.add_argument("--sweep-report", default="")
    parser.add_argument("--upstream-requirements", default="")
    parser.add_argument("--mode", choices=("apply", "dry-run"), default="apply")
    args = parser.parse_args(argv)
    # Make paths absolute without following symlinks: a venv's bin/python is a
    # symlink to the base interpreter and uv needs the venv path itself. The
    # chdir then runs the resolve from the repo root so the repo's [tool.uv]
    # security floors (pillow>=13 on Python 3.11+) apply the same way regardless
    # of the caller's working directory.
    python = os.path.abspath(args.python)
    sweep_path = os.path.abspath(args.sweep_report) if args.sweep_report else ""
    sweep = Path(sweep_path).read_text(encoding="utf-8") if sweep_path else ""
    upstream_path = (
        os.path.abspath(args.upstream_requirements) if args.upstream_requirements else ""
    )
    upstream = Path(upstream_path).read_text(encoding="utf-8") if upstream_path else ""
    os.chdir(Path(__file__).resolve().parent.parent)
    if args.mode == "dry-run":
        if not Path(python).is_file():
            installed: dict[str, str] = {}
            print(render_plan(build_plan(args.service, installed, sweep, upstream), python))
            return 0
        plan = build_plan(args.service, read_installed(python), sweep, upstream)
        return _apply(plan, python, dry_run=True)
    if not Path(python).is_file():
        raise SystemExit(f"interpreter missing: {python}")
    plan = build_plan(args.service, read_installed(python), sweep, upstream)
    return _apply(plan, python, dry_run=False)


if __name__ == "__main__":
    raise SystemExit(main())
