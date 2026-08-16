#!/usr/bin/env python3
"""Complexity census — the measurement that gates TASK_COMPLEXITY_REDUCTION_V1.

Reports four independently-actionable pathologies, each with a hard number:

  DATA    module-level literal assignments inside .py files (data masquerading as code)
  GOD     functions over the size/branch budget
  PROSE   comment + docstring lines, and files where prose outweighs code
  INERT   unwired scripts, byte-identical file pairs, committed result blobs

Exit code is 0 in ``--report`` mode always; in ``--gate`` mode it is 1 when any
budget in ``config/complexity_budget.yaml`` is exceeded. Report first, gate later:
the budget file starts as a recorded baseline and ratchets down, mirroring the
BR spine-coverage gate's ratchet→absolute path.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import subprocess
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Budgets. A function over EITHER line or branch budget is a GOD finding.
FUNC_LINE_BUDGET = 80
FUNC_BRANCH_BUDGET = 15
# A module-level literal assignment this long is data, not code.
DATA_LINE_BUDGET = 30
# Prose share above this in a file over 200 lines is a PROSE finding.
PROSE_SHARE_BUDGET = 0.35


@dataclass
class FileStats:
    path: str
    lines: int = 0
    code: int = 0
    comment: int = 0
    docstring: int = 0
    blank: int = 0
    data_lines: int = 0

    @property
    def prose(self) -> int:
        return self.comment + self.docstring

    @property
    def prose_share(self) -> float:
        return self.prose / self.lines if self.lines else 0.0


@dataclass
class Census:
    files: list[FileStats] = field(default_factory=list)
    god_funcs: list[tuple[str, str, int, int]] = field(default_factory=list)
    data_blobs: list[tuple[str, str, int]] = field(default_factory=list)
    identical: list[tuple[str, str]] = field(default_factory=list)
    unwired: list[str] = field(default_factory=list)
    blobs: list[tuple[str, int]] = field(default_factory=list)

    @property
    def totals(self) -> dict[str, int]:
        return {
            "files": len(self.files),
            "lines": sum(f.lines for f in self.files),
            "code": sum(f.code for f in self.files),
            "prose": sum(f.prose for f in self.files),
            "data_lines": sum(f.data_lines for f in self.files),
            "god_funcs": len(self.god_funcs),
            "god_lines": sum(n for _, _, n, _ in self.god_funcs),
            "data_blobs": len(self.data_blobs),
            "identical_pairs": len(self.identical),
            "unwired_scripts": len(self.unwired),
            "committed_blob_bytes": sum(b for _, b in self.blobs),
        }


def _tracked(pattern: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", pattern],
            cwd=REPO,
            capture_output=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    return [p for p in out.stdout.decode("utf-8", errors="replace").split("\n") if p]


def _branches(node: ast.AST) -> int:
    return sum(
        1
        for n in ast.walk(node)
        if isinstance(n, ast.If | ast.For | ast.While | ast.Try | ast.BoolOp | ast.ExceptHandler)
    )


def _span(node: ast.AST) -> int:
    return getattr(node, "end_lineno", node.lineno) - node.lineno + 1


def measure_file(rel: str) -> tuple[FileStats, list, list]:
    st = FileStats(path=rel)
    src = (REPO / rel).read_text(errors="replace")
    lines = src.splitlines()
    st.lines = len(lines)
    st.blank = sum(1 for line in lines if not line.strip())
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                st.comment += 1
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass

    gods: list[tuple[str, str, int, int]] = []
    blobs: list[tuple[str, str, int]] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        st.code = st.lines - st.blank - st.comment
        return st, gods, blobs

    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            if ast.get_docstring(node, clean=False) is not None:
                st.docstring += _span(node.body[0])
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            n_lines, n_br = _span(node), _branches(node)
            if n_lines > FUNC_LINE_BUDGET or n_br > FUNC_BRANCH_BUDGET:
                gods.append((rel, node.name, n_lines, n_br))

    for node in tree.body:
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        target = node.targets[0] if isinstance(node, ast.Assign) else node.target
        name = getattr(target, "id", "?")
        n_lines = _span(node)
        if n_lines > DATA_LINE_BUDGET:
            blobs.append((rel, name, n_lines))
            st.data_lines += n_lines

    st.code = max(st.lines - st.blank - st.comment - st.docstring, 0)
    return st, gods, blobs


def find_identical() -> list[tuple[str, str]]:
    """Byte-identical tracked .py pairs anywhere in the tree, not just deploy/."""
    from collections import defaultdict
    from hashlib import sha256

    by_hash: dict[str, list[str]] = defaultdict(list)
    for rel in _tracked("*.py"):
        p = REPO / rel
        if not p.is_file() or p.stat().st_size == 0:
            continue
        by_hash[sha256(p.read_bytes()).hexdigest()].append(rel)
    pairs = []
    for group in by_hash.values():
        if len(group) > 1:
            first = group[0]
            pairs.extend((first, other) for other in sorted(group[1:]))
    return sorted(pairs)


def find_unwired() -> list[str]:
    """Tracked scripts whose module name appears nowhere but their own file and wiki unit."""
    haystack_files = [
        p for p in _tracked("*") if p.endswith((".py", ".sh", ".yaml", ".yml", ".toml", ".mk"))
    ]
    # scripts/OPERATOR_TOOLS.md is the deliberate registration manifest for the
    # operator-invoked surface: naming a script there is what makes it referenced.
    if (REPO / "scripts" / "OPERATOR_TOOLS.md").exists():
        haystack_files.append("scripts/OPERATOR_TOOLS.md")
    corpus: dict[str, str] = {}
    for rel in haystack_files:
        try:
            corpus[rel] = (REPO / rel).read_text(errors="replace")
        except OSError:
            continue
    unwired = []
    for rel in sorted(set(_tracked("scripts/*.py")) | set(_tracked("scripts/**/*.py"))):
        stem = Path(rel).stem
        if stem.startswith("_"):
            continue
        hits = [
            other
            for other, text in corpus.items()
            if other != rel and (stem in text or rel in text)
        ]
        if not hits:
            unwired.append(rel)
    return sorted(unwired)


def find_blobs() -> list[tuple[str, int]]:
    """Result/data artifacts committed inside the importable package tree."""
    out = []
    for rel in _tracked("portal/*"):
        if rel.endswith((".json", ".jsonl", ".csv", ".log")):
            try:
                out.append((rel, (REPO / rel).stat().st_size))
            except OSError:
                continue
    return sorted(out, key=lambda r: -r[1])


def run_census() -> Census:
    c = Census()
    for rel in _tracked("*.py"):
        if not (REPO / rel).is_file():
            continue
        st, gods, blobs = measure_file(rel)
        c.files.append(st)
        c.god_funcs.extend(gods)
        c.data_blobs.extend(blobs)
    c.identical = find_identical()
    c.unwired = find_unwired()
    c.blobs = find_blobs()
    return c


def render(c: Census, top: int = 15) -> str:
    t = c.totals
    out: list[str] = []
    out.append("=" * 78)
    out.append("COMPLEXITY CENSUS")
    out.append("=" * 78)
    out.append(
        f"  {t['files']} tracked .py files   {t['lines']:,} lines   "
        f"{t['code']:,} code   {t['prose']:,} prose ({100 * t['prose'] / max(t['lines'], 1):.1f}%)"
    )
    out.append("")
    out.append(
        f"DATA   {t['data_blobs']} module-level literals > {DATA_LINE_BUDGET} lines, "
        f"{t['data_lines']:,} lines total"
    )
    for rel, name, n in sorted(c.data_blobs, key=lambda r: -r[2])[:top]:
        out.append(f"       {n:>6,}  {name:<32} {rel}")
    out.append("")
    out.append(
        f"GOD    {t['god_funcs']} functions over budget "
        f"(>{FUNC_LINE_BUDGET} lines or >{FUNC_BRANCH_BUDGET} branches), "
        f"{t['god_lines']:,} lines total"
    )
    for rel, name, n, br in sorted(c.god_funcs, key=lambda r: -r[2])[:top]:
        out.append(f"       {n:>6,}L  br={br:<4} {name:<34} {rel}")
    out.append("")
    out.append(f"PROSE  files > 200 lines where prose share exceeds {PROSE_SHARE_BUDGET:.0%}")
    worst = [f for f in c.files if f.lines > 200 and f.prose_share > PROSE_SHARE_BUDGET]
    for f in sorted(worst, key=lambda f: -f.prose)[:top]:
        out.append(f"       {f.prose:>6,}p  {f.prose_share:>5.0%}  {f.code:>6,}c  {f.path}")
    out.append(f"       ({len(worst)} files over prose budget)")
    out.append("")
    out.append(
        f"INERT  {t['unwired_scripts']} unwired scripts | "
        f"{t['identical_pairs']} byte-identical .py pairs | "
        f"{t['committed_blob_bytes'] / 1e6:.1f} MB result blobs inside portal/"
    )
    for rel in c.unwired[:top]:
        out.append(f"       unwired      {rel}")
    for a, b in c.identical[:top]:
        out.append(f"       identical    {a}  ==  {b}")
    for rel, size in c.blobs[:5]:
        out.append(f"       blob {size / 1e6:>5.1f}MB  {rel}")
    out.append("=" * 78)
    return "\n".join(out)


BUDGET_PATH = REPO / "config" / "complexity_budget.yaml"

GATED_KEYS = (
    "data_lines",
    "god_funcs",
    "god_lines",
    "prose",
    "unwired_scripts",
    "identical_pairs",
    "committed_blob_bytes",
)


def gate(c: Census) -> int:
    """Fail when any gated total exceeds the recorded budget. Never raises."""
    import yaml

    if not BUDGET_PATH.exists():
        print(f"[complexity] no budget at {BUDGET_PATH.relative_to(REPO)} — run --write-budget")
        return 0
    budget = yaml.safe_load(BUDGET_PATH.read_text()) or {}
    totals = c.totals
    failures = []
    for key in GATED_KEYS:
        allowed = budget.get(key)
        if allowed is None:
            continue
        actual = totals[key]
        if actual > allowed:
            failures.append(f"  {key}: {actual:,} > budget {allowed:,}")
    if failures:
        print("[complexity] GATE FAIL — complexity increased above the recorded budget:")
        print("\n".join(failures))
        print("  Reduce the complexity, or lower the budget only alongside a real reduction.")
        return 1
    print("[complexity] GATE OK — all totals at or below budget:")
    for key in GATED_KEYS:
        if budget.get(key) is not None:
            print(f"  {key}: {totals[key]:,} <= {budget[key]:,}")
    return 0


def write_budget(c: Census) -> int:
    import yaml

    totals = c.totals
    payload = {k: totals[k] for k in GATED_KEYS}
    BUDGET_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_PATH.write_text(
        "# Recorded complexity budget — written by scripts/complexity_report.py --write-budget.\n"
        "# Values are ceilings. Re-baseline after intentional code growth; lower them when complexity falls.\n"
        + yaml.safe_dump(payload, sort_keys=True)
    )
    print(f"[complexity] wrote budget to {BUDGET_PATH.relative_to(REPO)}")
    print(yaml.safe_dump(payload, sort_keys=True))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Portal complexity census")
    ap.add_argument("--json", action="store_true", help="emit machine-readable totals")
    ap.add_argument("--gate", action="store_true", help="exit 1 if over recorded budget")
    ap.add_argument("--write-budget", action="store_true", help="record current totals as budget")
    ap.add_argument("--top", type=int, default=15, help="rows per section")
    args = ap.parse_args()

    c = run_census()
    if args.write_budget:
        return write_budget(c)
    if args.gate:
        return gate(c)
    if args.json:
        print(json.dumps(c.totals, indent=2, sort_keys=True))
        return 0
    print(render(c, top=args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
