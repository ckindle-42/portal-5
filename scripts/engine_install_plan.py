#!/usr/bin/env python3
"""Host-engine pip plan: service deps plus sweep fixes, never a core-stack bump.

``uv pip install --upgrade`` re-resolves the named set and its dependencies, so
an advisory floor on pillow also moved torch, transformers, diffusers,
huggingface-hub, and numpy (2026-11-19 install-music). Core packages stay at
the version already installed. A sweep fix for one of them is reported and
skipped. ``--dry-run`` prints the argv and does not execute it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_NAME = re.compile(r"^\s*([A-Za-z0-9_.-]+)")
_ROW = re.compile(r"^\|(.+)\|\s*$")

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

_READ_INSTALLED = (
    "import importlib.metadata, json; "
    "print(json.dumps({d.metadata['Name']: d.version "
    "for d in importlib.metadata.distributions()}))"
)


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


def parse_sweep_fixes(text: str) -> dict[str, tuple[str, tuple[str, ...]]]:
    """PyPI rows of a security-sweep report: name -> (highest fixed, advisory ids)."""
    found: dict[str, tuple[str, tuple[str, ...]]] = {}
    for line in text.splitlines():
        match = _ROW.match(line.strip())
        if match is None:
            continue
        cells = [cell.strip() for cell in match.group(1).split("|")]
        if len(cells) < 6 or cells[0].casefold() != "pypi":
            continue
        _ecosystem, name, _version, advisory, _severity, fixed = cells[:6]
        if not fixed or fixed in {"—", "-"}:
            continue
        key = canonical_name(name)
        previous = found.get(key)
        ids = (advisory,) if advisory and advisory not in {"—", "-"} else ()
        if previous is None or version_key(fixed) > version_key(previous[0]):
            found[key] = (fixed, previous[1] + ids if previous else ids)
        elif previous is not None:
            found[key] = (previous[0], previous[1] + ids)
    return found


@dataclass(frozen=True)
class InstallPlan:
    service: str
    service_deps: tuple[str, ...]
    upgrades: tuple[str, ...]
    upgrade_packages: tuple[str, ...]
    refused: tuple[str, ...]
    holds: tuple[str, ...]

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
    if service not in SERVICE_DEPS:
        raise ValueError(f"unknown engine service {service!r}")
    deps = SERVICE_DEPS[service]
    dep_names = {requirement_name(spec) for spec in deps}
    upgrades: list[str] = []
    upgrade_packages: list[str] = []
    refused: list[str] = []
    for name, (fixed, ids) in sorted(parse_sweep_fixes(sweep_text).items()):
        label = f"{name}=={fixed}" + (f" ({', '.join(ids)})" if ids else "")
        if is_core_stack(name):
            current = installed.get(name, "not installed")
            refused.append(f"{label}; installed {current}; engine bump required")
            continue
        if name in dep_names:
            continue
        upgrades.append(f"{name}=={fixed}")
        upgrade_packages.append(name)
    holds = tuple(
        f"{name}=={version}"
        for name, version in sorted(installed.items())
        if is_core_stack(name) and name not in dep_names
    )
    return InstallPlan(
        service, deps, tuple(upgrades), tuple(upgrade_packages), tuple(refused), holds
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
    if not python or not Path(python).is_file():
        return {}
    result = subprocess.run(
        [python, "-c", _READ_INSTALLED],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"cannot read packages from {python}: {result.stderr.strip()}")
    payload = json.loads(result.stdout or "{}")
    return {canonical_name(name): version for name, version in payload.items()}


def _apply(plan: InstallPlan, python: str) -> int:
    print(render_plan(plan, python))
    if not plan.requirements():
        return 0
    descriptor, path = tempfile.mkstemp(prefix=f"portal5-{plan.service}-hold-", suffix=".txt")
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write("\n".join(plan.holds) + ("\n" if plan.holds else ""))
        command = plan.argv(python, path)
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            print(f"dependency install failed ({result.returncode})", file=sys.stderr)
        return result.returncode
    finally:
        os.unlink(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, choices=sorted(SERVICE_DEPS))
    parser.add_argument("--python", required=True)
    parser.add_argument("--sweep-report", default="")
    parser.add_argument("--mode", choices=("apply", "dry-run"), default="apply")
    args = parser.parse_args(argv)
    sweep = Path(args.sweep_report).read_text(encoding="utf-8") if args.sweep_report else ""
    if args.mode == "dry-run":
        installed = read_installed(args.python) if Path(args.python).is_file() else {}
    else:
        if not Path(args.python).is_file():
            raise SystemExit(f"interpreter missing: {args.python}")
        installed = read_installed(args.python)
    plan = build_plan(args.service, installed, sweep)
    if args.mode == "dry-run":
        print(render_plan(plan, args.python))
        return 0
    return _apply(plan, args.python)


if __name__ == "__main__":
    raise SystemExit(main())
