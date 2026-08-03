"""AST-derived API projection — the "free" text a unit must not merely restate.

`check_substance` in `quality.py` rejects a unit whose prose mostly overlaps this
derived text. The derivation is intentionally shallow: it is exactly what an AST
walk yields without reading the file — module and function/class signatures,
names, and docstring first lines. That is the surface a lazy summary reproduces,
and the point of the comparison is to prove the unit says something beyond it.
"""

from __future__ import annotations

import ast
from pathlib import Path


def derive_body(path: str, repo_root: Path | None = None) -> str:
    """Project a Python file's API surface into prose, from the AST only.

    Returns an empty string when the file cannot be read or parsed, so callers
    treat derivation as an optional comparison, never a gate of its own.
    """
    root = repo_root or Path(__file__).resolve().parents[4]
    target = root / path
    try:
        source = target.read_text(encoding="utf-8")
    except OSError:
        return ""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""

    lines: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name != "__init__":
            args = [a.arg for a in node.args.args]
            lines.append(f"def {node.name}({', '.join(args)})")
            doc = ast.get_docstring(node)
            if doc:
                lines.append(doc.splitlines()[0])
        elif isinstance(node, ast.ClassDef):
            bases = [ast.unparse(b) for b in node.bases]
            lines.append(f"class {node.name}({', '.join(bases)})")
            doc = ast.get_docstring(node)
            if doc:
                lines.append(doc.splitlines()[0])
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    lines.append(f"{t.id} = <constant>")
    return "\n".join(lines)
