#!/usr/bin/env python3
"""Test-reduction v2 LOC measurement (same scope as v1: tests/unit, tests/wfe, portal/**/tests).

Reports nonblank and nonblank-nocomment LOC per group, plus the test:product ratio.
Run: uv run python coding_task/measure_test_loc.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def files() -> list[Path]:
    out: list[Path] = []
    for base in ("tests/unit", "tests/wfe"):
        out += sorted((ROOT / base).rglob("*.py"))
    out += sorted(p for p in (ROOT / "portal").rglob("*.py") if "/tests/" in str(p))
    return out


def count(path: Path) -> tuple[int, int]:
    nb = nbc = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s:
            continue
        nb += 1
        if not s.startswith("#"):
            nbc += 1
    return nb, nbc


def main() -> None:
    groups: dict[str, list[int]] = {
        "tests/unit": [0, 0, 0],
        "tests/wfe": [0, 0, 0],
        "portal/**/tests": [0, 0, 0],
    }
    for f in files():
        rel = str(f.relative_to(ROOT))
        key = "portal/**/tests" if rel.startswith("portal/") else "/".join(rel.split("/")[:2])
        nb, nbc = count(f)
        g = groups[key]
        g[0] += 1
        g[1] += nb
        g[2] += nbc
    tot = [0, 0, 0]
    for k, (n, nb, nbc) in groups.items():
        print(f"{k}: files={n} nonblank={nb} nonblank_nocomment={nbc}")
        tot[0] += n
        tot[1] += nb
        tot[2] += nbc
    print(f"TOTAL: files={tot[0]} nonblank={tot[1]} nonblank_nocomment={tot[2]}")
    prod = 0
    for p in (ROOT / "portal").rglob("*.py"):
        if "/tests/" in str(p):
            continue
        nb, _ = count(p)
        prod += nb
    print(f"product_nonblank={prod} ratio_nonblank={tot[1] / prod:.4f}")


if __name__ == "__main__":
    main()
