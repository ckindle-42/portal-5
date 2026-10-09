#!/usr/bin/env python3
"""Prune ledger for the Bully package -- keep/delete decided by reachability, not by taste.

    # 1. record which modules REAL runs import (any python command; children are traced too)
    uv run python scripts/bully_review_prune_ledger.py trace --out reports/bully_review/trace -- \\
        uv run pytest tests/security/review -q
    uv run python scripts/bully_review_prune_ledger.py trace --out reports/bully_review/trace -- \\
        uv run python scripts/review_eval_run.py --arm D0

    # 2. build the ledger
    uv run python scripts/bully_review_prune_ledger.py ledger \\
        --keep portal.modules.security.core.review --keep portal.modules.security.core.review_eval \\
        --trace-dir reports/bully_review/trace --out reports/bully_review

A known-lazy edge (e.g. the package ``__init__`` importing the hunt orchestrator inside a
function) can be cut explicitly with ``--ignore-edge SRC=>DST``; every cut is recorded in the
ledger, so the decision is auditable rather than implicit.

Rules (mechanical): a module of the package is KEEP if a keep root reaches it through ANY import
(module-level or function-level -- conservative); KEEP_DYNAMIC if no static path exists but a
trace shows it imported; otherwise DELETE. A test or script is DELETE only if every package
module it imports is DELETE (a file that imports a KEEP module, or no package module at all,
is kept). Nothing is executed: the ledger writes ``prune_batches.sh`` for the agent to review,
run in batches, and verify after each batch.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DEFAULT_PACKAGE = "portal/modules/security/core/bully"
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}

SITECUSTOMIZE = """\
import atexit, json, os, sys

def _dump():
    out = os.environ.get("REVIEW_TRACE_OUT")
    if not out:
        return
    mods = sorted(m for m in sys.modules if m.startswith("portal."))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "trace_%d.json" % os.getpid()), "w") as handle:
        json.dump(mods, handle)

atexit.register(_dump)
"""


def _python_files(repo: Path) -> list[Path]:
    return [
        p
        for p in repo.rglob("*.py")
        if not any(part in SKIP_DIRS for part in p.relative_to(repo).parts)
    ]


def _module(repo: Path, path: Path) -> str:
    parts = list(path.relative_to(repo).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(repo: Path, path: Path) -> set[str]:
    """Every import in the file (module- and function-level; TYPE_CHECKING included)."""
    mod = _module(repo, path)
    pkg = mod if path.name == "__init__.py" else mod.rsplit(".", 1)[0]
    found: set[str] = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return found
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = pkg.split(".")
                base = ".".join(parts[: len(parts) - (node.level - 1)])
                target = f"{base}.{node.module}" if node.module else base
            else:
                target = node.module or ""
            found.add(target)
            found.update(f"{target}.{a.name}" for a in node.names)
    return found


def _resolve(name: str, known: set[str]) -> str | None:
    parts = name.split(".")
    while parts:
        cand = ".".join(parts)
        if cand in known:
            return cand
        parts.pop()
    return None


def load_trace(trace_dir: Path | None) -> set[str]:
    seen: set[str] = set()
    if trace_dir is not None and trace_dir.is_dir():
        for f in trace_dir.glob("trace_*.json"):
            seen.update(json.loads(f.read_text(encoding="utf-8")))
    return seen


def build_ledger(
    repo: Path,
    *,
    package_dir: str = DEFAULT_PACKAGE,
    keep_prefixes: list[str],
    protect: set[str] | None = None,
    dynamic: set[str] | None = None,
    ignore_edges: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    package = (repo / package_dir).resolve()
    files = _python_files(repo)
    mod_of = {p: _module(repo, p) for p in files}
    known = set(mod_of.values())
    cut = ignore_edges or set()
    graph: dict[str, set[str]] = {}
    for path in files:
        src = mod_of[path]
        graph[src] = {
            r
            for n in _imports(repo, path)
            if (r := _resolve(n, known)) and r != src and (src, r) not in cut
        }

    roots = {m for m in known if any(m == k or m.startswith(k + ".") for k in keep_prefixes)}
    roots |= protect or set()
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        item = stack.pop()
        if item in seen:
            continue
        seen.add(item)
        stack.extend(graph.get(item, set()) - seen)

    pkg_files = {p: m for p, m in mod_of.items() if p.resolve().is_relative_to(package)}
    pkg_mods = set(pkg_files.values())
    dyn = dynamic or set()

    def lines(path: Path) -> int:
        return sum(1 for _ in path.open(encoding="utf-8", errors="ignore"))

    modules: list[dict[str, Any]] = []
    decision_of: dict[str, str] = {}
    for path, mod in sorted(pkg_files.items(), key=lambda kv: kv[1]):
        if mod in seen:
            decision, reason = "KEEP", "reachable from a keep root"
        elif mod in dyn:
            decision, reason = "KEEP_DYNAMIC", "imported in a traced run; no static path"
        else:
            decision, reason = "DELETE", "unreachable statically and never imported in a traced run"
        decision_of[mod] = decision
        importers = sorted(m for m, deps in graph.items() if mod in deps and m != mod)
        modules.append(
            {
                "module": mod,
                "path": str(path.relative_to(repo)),
                "lines": lines(path),
                "decision": decision,
                "reason": reason,
                "importers": importers,
            }
        )

    def classify(path: Path) -> tuple[str, list[str]]:
        hit = {r for n in _imports(repo, path) if (r := _resolve(n, known)) and r in pkg_mods}
        # `from pkg import mod` also names `pkg`; only the most specific module counts.
        used = sorted(m for m in hit if not any(o != m and o.startswith(m + ".") for o in hit))
        if not used:
            return "KEEP", []
        keepers = [m for m in used if decision_of[m] != "DELETE"]
        return ("KEEP" if keepers else "DELETE"), used

    def side(prefix: str) -> list[dict[str, Any]]:
        out = []
        for path in files:
            rel = path.relative_to(repo)
            if path.resolve().is_relative_to(package) or rel.parts[0] != prefix:
                continue
            decision, used = classify(path)
            if used:
                out.append(
                    {"path": str(rel), "decision": decision, "imports": used, "lines": lines(path)}
                )
        return sorted(out, key=lambda r: r["path"])

    tests, scripts = side("tests"), side("scripts")
    docs = sorted(
        str(p.relative_to(repo))
        for pattern in ("docs/BULLY_*", "docs/DESIGN_BULLY_*", "docs/HANDOFF_BULLY_*")
        for p in repo.glob(pattern)
        if p.is_file()
    )
    tally = {
        d: sum(1 for m in modules if m["decision"] == d) for d in ("KEEP", "KEEP_DYNAMIC", "DELETE")
    }
    return {
        "schema": "bully-review-prune-ledger-v1",
        "created_at": time.time(),
        "keep_roots": sorted(keep_prefixes),
        "cut_edges": sorted(f"{a} => {b}" for a, b in cut),
        "tally": tally,
        "delete_lines": sum(m["lines"] for m in modules if m["decision"] == "DELETE"),
        "modules": modules,
        "tests": tests,
        "scripts": scripts,
        "docs_to_review": docs,
    }


def render_markdown(ledger: dict[str, Any]) -> str:
    lines = [
        "# Bully prune ledger",
        "",
        f"keep roots: {', '.join(ledger['keep_roots'])}",
        f"tally: {ledger['tally']} -- deletable lines: {ledger['delete_lines']}",
        "",
        "| module | lines | decision | importers (any) |",
        "|---|---|---|---|",
    ]
    for m in ledger["modules"]:
        short = m["module"].rsplit(".", 1)[-1]
        who = ", ".join(i.rsplit(".", 1)[-1] for i in m["importers"][:4]) or "-"
        lines.append(f"| {short} | {m['lines']} | {m['decision']} | {who} |")
    for title, key in (("Tests", "tests"), ("Scripts", "scripts")):
        gone = [r for r in ledger[key] if r["decision"] == "DELETE"]
        lines += ["", f"## {title} that only exercise deletable modules ({len(gone)})", ""]
        lines += [f"- {r['path']}" for r in gone]
    lines += ["", "## Docs to reconcile or archive", ""]
    lines += [f"- {d}" for d in ledger["docs_to_review"]]
    return "\n".join(lines) + "\n"


def render_batches(ledger: dict[str, Any]) -> str:
    def rm(paths: list[str]) -> str:
        return "git rm -q " + " ".join(paths) if paths else "# (none)"

    gone_mods = [m["path"] for m in ledger["modules"] if m["decision"] == "DELETE"]
    gone_tests = [r["path"] for r in ledger["tests"] if r["decision"] == "DELETE"]
    gone_scripts = [r["path"] for r in ledger["scripts"] if r["decision"] == "DELETE"]
    verify = "uv run pytest tests -q -x && uv run python scripts/validate_system.py"
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "# GENERATED by bully_review_prune_ledger.py -- review, run one batch at a time,",
            "# verify, commit. Nothing here has been executed.",
            "set -euo pipefail",
            "",
            "# batch 1: scripts that only exercise deletable modules",
            rm(gone_scripts),
            f"{verify} && git commit -m 'chore(bully): remove run scripts for retired modules'",
            "",
            "# batch 2: tests that only exercise deletable modules",
            rm(gone_tests),
            f"{verify} && git commit -m 'test(bully): remove tests for retired modules'",
            "",
            "# batch 3: the modules themselves",
            rm(gone_mods),
            f"{verify} && git commit -m 'refactor(bully): remove modules unreachable from the reviewer'",
            "",
        ]
    )


def cmd_trace(args: argparse.Namespace) -> int:
    command = [c for c in args.command if c != "--"]
    if not command:
        print("trace: give a command after --", file=sys.stderr)
        return 2
    out = Path(args.out).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [tmp, env.get("PYTHONPATH", "")]))
        env["REVIEW_TRACE_OUT"] = str(out)
        return subprocess.run(command, env=env, check=False).returncode


def cmd_ledger(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    ledger = build_ledger(
        repo,
        package_dir=args.package,
        keep_prefixes=args.keep,
        protect=set(args.protect),
        dynamic=load_trace(Path(args.trace_dir)) if args.trace_dir else None,
        ignore_edges={(a, b) for a, _, b in (e.partition("=>") for e in args.ignore_edge)},
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "prune_ledger.json").write_text(
        json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8"
    )
    (out / "prune_ledger.md").write_text(render_markdown(ledger), encoding="utf-8")
    (out / "prune_batches.sh").write_text(render_batches(ledger), encoding="utf-8")
    print(json.dumps({"tally": ledger["tally"], "delete_lines": ledger["delete_lines"]}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    trace = sub.add_parser("trace", help="run a command and record the portal modules it imports")
    trace.add_argument("--out", required=True)
    trace.add_argument("command", nargs=argparse.REMAINDER)
    ledger = sub.add_parser("ledger", help="build the keep/delete ledger")
    ledger.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    ledger.add_argument("--package", default=DEFAULT_PACKAGE)
    ledger.add_argument(
        "--keep", action="append", required=True, help="dotted prefix of a keep root"
    )
    ledger.add_argument(
        "--protect", action="append", default=[], help="dotted module to keep regardless"
    )
    ledger.add_argument(
        "--ignore-edge",
        action="append",
        default=[],
        help="SRC=>DST dotted modules: cut one known-lazy edge (recorded in the ledger)",
    )
    ledger.add_argument("--trace-dir", default="")
    ledger.add_argument("--out", required=True)
    args = parser.parse_args()
    return cmd_trace(args) if args.cmd == "trace" else cmd_ledger(args)


if __name__ == "__main__":
    raise SystemExit(main())
