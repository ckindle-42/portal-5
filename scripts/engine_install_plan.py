#!/usr/bin/env python3
"""Host-engine pip plan: service deps plus sweep fixes, never a core-stack bump.

``uv pip install --upgrade`` re-resolves the named set and its dependencies, so
an advisory floor on pillow also moved torch, transformers, diffusers,
huggingface-hub, and numpy (2026-11-19 install-music). The plan is anchored in
the installed venv: holds are the core pins from ``uv pip freeze``, sweep fixes
apply only at the flagged version (core hits refuse as an engine bump unless the
installed version already satisfies the fix). A resolve conflict against a held
pin drops the offending service dep or sweep fix and prints the pair.
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

_NAME = re.compile(r"^\s*([A-Za-z0-9_.-]+)")
_ROW = re.compile(r"^\|(.+)\|\s*$")
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


def version_key(value: str) -> tuple[int, ...]:
    nums = [int(part) for part in re.findall(r"\d+", value)][:6]
    return tuple(nums + [0] * (6 - len(nums)))


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
        if len(cells) < 6 or cells[0].casefold() != "pypi":
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


def highest_core_fix(
    rows: dict[str, tuple[str, tuple[str, ...]]],
) -> tuple[str, tuple[str, ...]]:
    """Highest fix for a package across flagged versions, with every advisory id."""
    fix, ids = "", ()
    for _version, (candidate, row_ids) in rows.items():
        if version_key(candidate) > version_key(fix):
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
    satisfied: tuple[str, ...] = ()

    def requirements(self) -> list[str]:
        return [*self.service_deps, *self.upgrades]

    def argv(self, python: str, constraint: str) -> list[str]:
        command = ["uv", "pip", "install", "--python", python, "--constraint", constraint]
        for name in self.upgrade_packages:
            command.extend(["--upgrade-package", name])
        command.extend(self.requirements())
        return command


def build_plan(
    service: str,
    installed: dict[str, str],
    sweep_text: str,
) -> InstallPlan:
    """Anchor the plan in the installed venv.

    Sweep fixes apply only when the flagged version is the one installed here;
    core hits refuse as an engine bump unless the installed version already
    satisfies the highest fix in the report.
    """
    if service not in SERVICE_DEPS:
        raise ValueError(f"unknown engine service {service!r}")
    deps = SERVICE_DEPS[service]
    dep_names = {requirement_name(spec) for spec in deps}
    fixes = parse_sweep_fixes(sweep_text)
    upgrades: list[str] = []
    upgrade_packages: list[str] = []
    refused: list[str] = []
    satisfied: list[str] = []
    for name in sorted(fixes):
        rows = fixes[name]
        current = installed.get(name)
        if current is None:
            continue
        if is_core_stack(name):
            fix, ids = highest_core_fix(rows)
            if version_key(current) >= version_key(fix):
                satisfied.append(f"{name}=={current} (fix {fix})")
                continue
            label = f"{name}=={fix}" + (f" ({', '.join(ids)})" if ids else "")
            refused.append(f"{label}; installed {current}; engine bump required")
            continue
        row = rows.get(current)
        if row is None or name in dep_names:
            continue
        upgrades.append(f"{name}=={row[0]}")
        upgrade_packages.append(name)
    holds = tuple(
        f"{name}=={version}"
        for name, version in sorted(installed.items())
        if is_core_stack(name) and name not in dep_names
    )
    return InstallPlan(
        service,
        deps,
        tuple(upgrades),
        tuple(upgrade_packages),
        tuple(refused),
        holds,
        tuple(satisfied),
    )


def render_plan(plan: InstallPlan, python: str) -> str:
    lines = [f"service: {plan.service}", "service deps:"]
    lines.extend(f"  {spec}" for spec in plan.service_deps)
    lines.append("sweep upgrades:")
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
        refined = replace(plan, upgrades=upgrades, upgrade_packages=packages)
        note = f"{dropped} conflicts with {other}; dropped from this install"
        return refined, note
    deps = tuple(spec for spec in plan.service_deps if requirement_name(spec) != name)
    refused = plan.refused + (f"{dropped}; conflicts with held {other}; engine bump required",)
    refined = replace(plan, service_deps=deps, refused=refused)
    note = f"{dropped} needs newer core than held {other}; engine bump required"
    return refined, note


def _apply(plan: InstallPlan, python: str, dry_run: bool) -> int:
    print(render_plan(plan, python))
    if not plan.requirements():
        return 0
    descriptor, path = tempfile.mkstemp(prefix=f"portal5-{plan.service}-hold-", suffix=".txt")
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write("\n".join(plan.holds) + ("\n" if plan.holds else ""))
        current = plan
        for _ in range(_MAX_REFINES):
            command = current.argv(python, path)
            if dry_run:
                command.append("--dry-run")
            result = subprocess.run(command, check=False, stderr=subprocess.PIPE, text=True)
            if result.stderr:
                print(result.stderr, end="")
            if result.returncode == 0:
                return 0
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
    os.chdir(Path(__file__).resolve().parent.parent)
    if args.mode == "dry-run":
        if not Path(python).is_file():
            installed: dict[str, str] = {}
            print(render_plan(build_plan(args.service, installed, sweep), python))
            return 0
        plan = build_plan(args.service, read_installed(python), sweep)
        return _apply(plan, python, dry_run=True)
    if not Path(python).is_file():
        raise SystemExit(f"interpreter missing: {python}")
    plan = build_plan(args.service, read_installed(python), sweep)
    return _apply(plan, python, dry_run=False)


if __name__ == "__main__":
    raise SystemExit(main())
