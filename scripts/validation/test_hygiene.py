"""Test-hygiene check: a test may name only paths a fresh checkout supplies.

A `coding_task/` or absolute checkout path passes in the author's worktree and
fails everywhere else; an ignored path is absent by definition. A statement may
opt out with a `# local-only: <reason>` marker, and the check reports how many it
exempted. Docstrings and f-strings are prose, not paths the code resolves.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

from ._shared import REPO_ROOT
from .registry import register

# A repo path token: >=1 directory segment, then a final segment. A token whose
# first segment is not a tracked top-level name is a URL or an opaque word.
_TOKEN = re.compile(r"(?<![\w/.\-])((?:[A-Za-z0-9_][\w.\-]*/)+[A-Za-z0-9_][\w.\-]*)")
# An absolute home path with a real user segment after it (`/Users/` alone is a
# redaction guard in test_powermetrics_daemon, not a location).
_HOME = re.compile(r"/(?:Users|home)/[^/\s\"']+/")
_MARKER = re.compile(r"#\s*local-only:\s*\S")
_SHOW = 5


def _prose_ids(tree: ast.AST) -> set[int]:
    """`id()` of constants that are docstrings or f-string fragments."""
    prose: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                prose.add(id(body[0].value))
        elif isinstance(node, ast.JoinedStr):
            prose.update(id(part) for part in node.values)
    return prose


def _statements(tree: ast.AST) -> dict[int, ast.stmt | None]:
    """`id()` of every string constant -> the statement that contains it."""
    spans: dict[int, ast.stmt | None] = {}

    def walk(node: ast.AST, stmt: ast.stmt | None) -> None:
        if isinstance(node, ast.stmt):
            stmt = node
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            spans[id(node)] = stmt
        for child in ast.iter_child_nodes(node):
            walk(child, stmt)

    walk(tree, None)
    return spans


def _string_nodes(tree: ast.AST, prose: set[int]) -> list[ast.Constant]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in prose
    ]


def _git(root: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _top_level(root: Path) -> set[str]:
    """Top-level names git knows: the index, so it works without a commit."""
    out = _git(root, "ls-files")
    return {line.split("/", 1)[0] for line in out.stdout.splitlines() if "/" in line}


def _ignored(root: Path, candidates: list[str]) -> set[str]:
    """Of `candidates`, the subset `.gitignore` excludes (see wiki.drift's rationale)."""
    if not candidates:
        return set()
    queries = [query for cand in candidates for query in (cand, f"{cand}/")]
    hit = set(_git(root, "check-ignore", "--stdin", stdin="\n".join(queries)).stdout.splitlines())
    return {cand for cand in candidates if cand in hit or f"{cand}/" in hit}


def _scan_tests(base: Path) -> tuple[list[str], list[str], list[tuple[str, str, bool]]]:
    """(coding_task refs, absolute-home refs, [(where, repo path token, exempt)])."""
    top = _top_level(base)
    coding: list[str] = []
    absolute: list[str] = []
    refs: list[tuple[str, str, bool]] = []
    for py in sorted((base / "tests").rglob("*.py")):
        rel = py.relative_to(base).as_posix()
        try:
            source = py.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py))
        except (OSError, SyntaxError):
            continue
        lines = source.splitlines()
        spans = _statements(tree)
        for node in _string_nodes(tree, _prose_ids(tree)):
            where = f"{rel}:{node.lineno}"
            if "coding_task/" in node.value:
                coding.append(where)
            absolute.extend(f"{where} ({match.group(0)})" for match in _HOME.finditer(node.value))
            stmt = spans.get(id(node))
            exempt = stmt is not None and any(
                _MARKER.search(line) for line in lines[stmt.lineno - 1 : stmt.end_lineno]
            )
            for match in _TOKEN.finditer(node.value):
                token = match.group(1)
                if token.split("/", 1)[0] in top:
                    refs.append((where, token, exempt))
    return coding, absolute, refs


def _unit_source_refs(base: Path) -> list[str]:
    """Canonical unit sources that point outside the repo or into scratch/another worktree."""
    from portal.platform.wiki.schema import KnowledgeUnit

    bad: list[str] = []
    for md in sorted((base / "portal_wiki" / "canonical").glob("*.md")):
        try:
            unit = KnowledgeUnit.from_markdown(md.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a malformed unit fails AJ, not this gate
            continue
        for source in unit.sources:
            path = source.path
            segments = path.split("/")
            if (
                path.startswith("coding_task/")
                or path.startswith("/")
                or ".." in segments
                or segments[0].startswith("portal-5-")
            ):
                bad.append(f"{unit.id} -> {path}")
    return bad


@register("test_paths_tracked", "HX. tests cite only tracked paths", order=213)
def check_test_paths_tracked(root: Path | None = None) -> tuple[str, str, list[dict]]:
    """HX. No test names a gitignored `coding_task/` path, an absolute home path, or an ignored path."""
    base = root or REPO_ROOT
    coding, absolute, refs = _scan_tests(base)
    ignored = _ignored(base, sorted({token for _where, token, _exempt in refs}))
    offenders = [
        f"{where} -> {token}" for where, token, exempt in refs if token in ignored and not exempt
    ]
    exemptions = sorted({token for _where, token, exempt in refs if token in ignored and exempt})
    units = _unit_source_refs(base)

    def _detail(items: list[str], ok: str) -> str:
        return ok if not items else f"{len(items)}: " + "; ".join(items[:_SHOW])

    subs = [
        {
            "name": "no test references coding_task/",
            "status": "PASS" if not coding else "FAIL",
            "detail": _detail(coding, "none"),
        },
        {
            "name": "no test names an absolute home path",
            "status": "PASS" if not absolute else "FAIL",
            "detail": _detail(absolute, "none"),
        },
        {
            "name": "every repo path a test names is tracked",
            "status": "PASS" if not offenders else "FAIL",
            "detail": _detail(
                offenders,
                f"none ({len(exemptions)} local-only exempt)" if exemptions else "none",
            ),
        },
        {
            "name": "canonical unit sources stay repo-relative",
            "status": "PASS" if not units else "FAIL",
            "detail": _detail(units, "none"),
        },
    ]
    failures = len(coding) + len(absolute) + len(offenders) + len(units)
    if failures:
        return (
            "FAIL",
            f"{len(coding)} coding_task, {len(absolute)} absolute, "
            f"{len(offenders)} gitignored, {len(units)} unit source(s)",
            subs,
        )
    return ("PASS", f"tests cite only tracked paths ({len(exemptions)} local-only exempt)", subs)
