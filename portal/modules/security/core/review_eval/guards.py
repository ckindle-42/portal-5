"""review_eval.guards -- AST guards that make whole defect classes loud.

Pure functions over source text (the tests apply them to the product package):

* ``disallowed_imports``  -- a module may import only from allowed ``portal.*`` prefixes. The
  evaluation runner may import only the public service API: arms are CONFIGURATION of the one
  product path, never copies of engine internals (a harness that re-implements the engine
  drifts from it -- the lab's B1 "v1 base arm" silently became v2).
* ``numeric_constants``   -- every module-level ALL_CAPS number, numeric dataclass default and
  numeric function default, by qualified name. The product registers each one with a KIND
  (``review.constants``); a number nobody classified is a candidate for "a constant that
  decides".
* ``literal_tables``      -- module-level literal containers with many elements: data
  masquerading as code. A curated table is always the cheapest fix and nothing ever ratcheted
  it, so definition matchers crept back every phase.
"""

from __future__ import annotations

import ast
from collections.abc import Collection

TRIVIAL_NUMBERS = frozenset({0, 1, -1})


def disallowed_imports(source: str, *, allowed_prefixes: Collection[str]) -> list[str]:
    """``portal.*`` modules imported outside ``allowed_prefixes`` (any nesting, lazy included)."""
    bad: list[str] = []
    for node in ast.walk(ast.parse(source)):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        for name in names:
            if name.startswith("portal.") and not any(
                name == p or name.startswith(p + ".") for p in allowed_prefixes
            ):
                bad.append(name)
    return sorted(set(bad))


def _number(node: ast.expr) -> float | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _number(node.operand)
        return None if inner is None else -inner
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return None if isinstance(node.value, bool) else float(node.value)
    return None


def _nontrivial(node: ast.expr | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return any(_nontrivial(e) for e in node.elts)
    value = _number(node)
    return value is not None and value not in TRIVIAL_NUMBERS


def numeric_constants(source: str, *, module: str) -> list[str]:
    found: list[str] = []

    def visit(body: list[ast.stmt], scope: tuple[str, ...]) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, (*scope, node.name))
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                args = node.args
                positional = [*args.posonlyargs, *args.args]
                for arg, default in zip(
                    positional[len(positional) - len(args.defaults) :], args.defaults, strict=True
                ):
                    if _nontrivial(default):
                        found.append(".".join([module, *scope, node.name, arg.arg]))
                for arg, kw_default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
                    if _nontrivial(kw_default):
                        found.append(".".join([module, *scope, node.name, arg.arg]))
                visit(node.body, (*scope, node.name))
            elif isinstance(node, ast.Assign) and not scope:
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id.isupper()
                        and _nontrivial(node.value)
                    ):
                        found.append(f"{module}.{target.id}")
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
                if _nontrivial(node.value) and (scope or name.isupper()):
                    found.append(".".join([module, *scope, name]))

    visit(ast.parse(source).body, ())
    return sorted(set(found))


def literal_tables(source: str, *, min_elements: int = 10) -> list[tuple[str, int]]:
    """Module-level literal containers (or ``frozenset``/``set``/``tuple`` of one) with at least
    ``min_elements`` elements, as ``(name, element_count)``."""
    out: list[tuple[str, int]] = []
    for node in ast.parse(source).body:
        targets: list[str] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets, value = [node.target.id], node.value
        if value is None or not targets:
            continue
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.args
            and value.func.id in {"frozenset", "set", "tuple", "list", "dict"}
        ):
            value = value.args[0]
        if isinstance(value, ast.Dict):
            count = len(value.keys)
        elif isinstance(value, ast.Set | ast.List | ast.Tuple):
            count = len(value.elts)
        else:
            continue
        if count >= min_elements:
            out.extend((name, count) for name in targets)
    return out
