#!/usr/bin/env python3
"""scripts/check_docstrings.py — Portal 5 docstring coverage gate.

Walks every active Python file (excludes vendored portal_mcp/mcp_server/
and the duplicated deploy/playwright-mcp/ tree) and reports:

  * modules without a docstring,
  * classes without a docstring,
  * non-dunder functions/methods without a docstring,
  * stub docstrings (< MIN_STUB_LEN characters).

Exits non-zero if any item in scope is missing. Run from repo root:

    python3 scripts/check_docstrings.py
    python3 scripts/check_docstrings.py --paths portal_pipeline
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

EXCLUDE_PREFIXES: tuple[str, ...] = (
    "portal_mcp/mcp_server/",
    "deploy/playwright-mcp/",
    "tests/_archive/",
)

SKIP_DUNDERS: frozenset[str] = frozenset({
    "__repr__", "__str__", "__eq__", "__ne__", "__hash__", "__lt__", "__le__",
    "__gt__", "__ge__", "__iter__", "__next__", "__len__", "__contains__",
    "__getitem__", "__setitem__", "__delitem__", "__enter__", "__exit__",
    "__aenter__", "__aexit__", "__bool__", "__post_init__",
})

MIN_STUB_LEN = 20


def is_excluded(rel_path: str) -> bool:
    return any(rel_path.startswith(p) for p in EXCLUDE_PREFIXES)


def find_python_files(root: Path, scope: list[str] | None) -> list[Path]:
    out: list[Path] = []
    roots = [root / s for s in scope] if scope else [root]
    for r in roots:
        if r.is_file() and r.suffix == ".py":
            out.append(r)
            continue
        for p in r.rglob("*.py"):
            rel = str(p.relative_to(root))
            if is_excluded(rel):
                continue
            out.append(p)
    return sorted(set(out))


def get_doc_len(node: ast.AST) -> int:
    ds = ast.get_docstring(node, clean=False)
    return 0 if ds is None else len(ds)


def analyse_file(path: Path, root: Path) -> list[dict]:
    rel = str(path.relative_to(root))
    issues: list[dict] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as e:
        return [{"file": rel, "line": e.lineno or 1, "kind": "parse_error", "name": "", "reason": str(e)}]

    mod_len = get_doc_len(tree)
    if mod_len == 0:
        issues.append({"file": rel, "line": 1, "kind": "module", "name": "<module>", "reason": "missing module docstring"})
    elif mod_len < MIN_STUB_LEN:
        issues.append({"file": rel, "line": 1, "kind": "module", "name": "<module>", "reason": f"stub module docstring ({mod_len}c)"})

    class V(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            n = get_doc_len(node)
            if n == 0:
                issues.append({"file": rel, "line": node.lineno, "kind": "class", "name": node.name, "reason": "missing class docstring"})
            elif n < MIN_STUB_LEN:
                issues.append({"file": rel, "line": node.lineno, "kind": "class", "name": node.name, "reason": f"stub class docstring ({n}c)"})
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def _visit_func(self, node):
            if node.name in SKIP_DUNDERS:
                return
            n = get_doc_len(node)
            kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
            if self.stack:
                kind = "async_method" if isinstance(node, ast.AsyncFunctionDef) else "method"
            if n == 0:
                issues.append({"file": rel, "line": node.lineno, "kind": kind,
                               "name": ".".join(self.stack + [node.name]),
                               "reason": "missing docstring"})
            elif n < MIN_STUB_LEN:
                issues.append({"file": rel, "line": node.lineno, "kind": kind,
                               "name": ".".join(self.stack + [node.name]),
                               "reason": f"stub docstring ({n}c)"})

        def visit_FunctionDef(self, node):
            self._visit_func(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            self._visit_func(node)
            self.generic_visit(node)

    V().visit(tree)
    return issues


def main() -> int:
    p = argparse.ArgumentParser(description="Portal 5 docstring coverage gate.")
    p.add_argument("--json", action="store_true")
    p.add_argument("--paths", nargs="*", default=None)
    p.add_argument("--root", default=".")
    args = p.parse_args()

    root = Path(args.root).resolve()
    files = find_python_files(root, args.paths)
    all_issues: list[dict] = []
    for f in files:
        all_issues.extend(analyse_file(f, root))

    if args.json:
        print(json.dumps({"files_scanned": len(files), "issues": all_issues}, indent=2))
    else:
        by_file: dict[str, list[dict]] = {}
        for i in all_issues:
            by_file.setdefault(i["file"], []).append(i)
        for f in sorted(by_file):
            print(f"\n{f}:")
            for i in by_file[f]:
                print(f"  L{i['line']:>5}  {i['kind']:14s} {i['name']:50s} {i['reason']}")
        print(f"\nFiles scanned: {len(files)}   Issues: {len(all_issues)}")

    return 1 if all_issues else 0


if __name__ == "__main__":
    sys.exit(main())
