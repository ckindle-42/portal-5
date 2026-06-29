#!/usr/bin/env python3
"""CI guard: pyproject.toml must not have duplicate dependency strings.

Checks all dependency lists across [project.dependencies] and [project.optional-dependencies]
for repeated package names (case-insensitive, ignoring version specifiers).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

REPO = Path(__file__).resolve().parent.parent.parent


def _pkg_name(dep: str) -> str:
    return re.split(r"[><=!;[ ]", dep.strip())[0].lower().replace("-", "_")


def main() -> int:
    pyproject = REPO / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())

    all_deps: list[tuple[str, str]] = []  # (context, package_name)

    for dep in data.get("project", {}).get("dependencies", []):
        all_deps.append(("[project.dependencies]", _pkg_name(dep)))

    for extra, deps in data.get("project", {}).get("optional-dependencies", {}).items():
        for dep in deps:
            all_deps.append((f"[project.optional-dependencies.{extra}]", _pkg_name(dep)))

    # Find duplicates within the same context (same extra/core)
    from collections import defaultdict

    by_context: dict[str, list[str]] = defaultdict(list)
    for ctx, name in all_deps:
        by_context[ctx].append(name)

    failures = []
    for ctx, names in by_context.items():
        seen: set[str] = set()
        dupes: set[str] = set()
        for n in names:
            if n in seen:
                dupes.add(n)
            seen.add(n)
        if dupes:
            failures.append(f"  {ctx}: duplicate package(s): {sorted(dupes)}")

    if failures:
        print("[guard] pyproject-no-dup: FAIL — duplicate dependency pins:")
        for f in failures:
            print(f)
        return 1

    print("[guard] pyproject-no-dup: OK (no duplicate pins)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
