"""review.wall -- the truth wall, by construction.

Two mechanical guards, both tested:

1. ``assert_label_free`` -- a record handed to the observation plane may not carry a scorer
   or scenario label (``family``, ``technique``, ``_labels`` ...). The evaluation harness
   calls it on every probe record; a violation is an error, never a warning.
2. ``scan_source`` -- a static scan of observation-plane module source. Those modules may not
   mention a label identifier (as a name, attribute, argument, field, or dict-key / literal
   string). The lab's own history is why: a signature that carried ``family`` or the ATT&CK
   ids let the engine read the answer through its retrieval axes (precision 0.72 leaky versus
   ~4-6 % blind). The only durable fix is that the observation plane cannot even spell them.

Docstrings are exempt (documentation may name what is forbidden); code is not.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from typing import Any

#: Identifiers that denote a scorer/scenario label. Compared case-insensitively.
LABEL_IDENTIFIERS: frozenset[str] = frozenset(
    {
        "family",
        "scenario",
        "scenario_family",
        "technique",
        "techniques",
        "technique_id",
        "technique_ids",
        "attack_id",
        "attack_ids",
        "attack_mappings",
        "attack_primary",
        "answer_key",
        "ground_truth",
        "sealed_truth",
        "truth",
        "_labels",
        "injected",
        "malicious",
        "chain_id",
        "implant_class",
        "parent_family",
        "parent_technique",
        "expected_technique",
    }
)

#: Observation-plane modules (file stems under ``review/``). ``tests/security/review`` scans
#: each of these with ``scan_source``.
OBSERVATION_PLANE: tuple[str, ...] = ("content", "intake", "calibration", "funnel")


class WallViolation(ValueError):  # noqa: N818 -- the name is the contract
    """A label crossed into the observation plane."""


def find_label_keys(obj: Any, *, path: str = "") -> list[str]:
    """Every dict key (at any depth) that names a label, as a dotted path."""
    hits: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else str(key)
            if str(key).strip().lower() in LABEL_IDENTIFIERS:
                hits.append(here)
            hits.extend(find_label_keys(value, path=here))
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            hits.extend(find_label_keys(value, path=f"{path}[{index}]"))
    return hits


def assert_label_free(record: Mapping[str, Any], *, where: str) -> None:
    hits = find_label_keys(record)
    if hits:
        raise WallViolation(f"{where}: label key(s) {hits[:5]} in an observation record")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    exempt: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                exempt.add(id(body[0].value))
    return exempt


def scan_source(source: str, *, filename: str = "<source>") -> list[str]:
    """Label identifiers that the code (not the docstrings) of ``source`` mentions."""
    tree = ast.parse(source, filename=filename)
    exempt = _docstring_nodes(tree)
    hits: list[str] = []

    def hit(name: str, node: ast.AST) -> None:
        if name.strip().lower() in LABEL_IDENTIFIERS:
            hits.append(f"{filename}:{getattr(node, 'lineno', 0)}: {name}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            hit(node.id, node)
        elif isinstance(node, ast.Attribute):
            hit(node.attr, node)
        elif isinstance(node, ast.arg | ast.keyword) and node.arg:
            hit(node.arg, node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            hit(node.name, node)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in exempt
        ):
            hit(node.value, node)
    return hits


def scan_modules(sources: Iterable[tuple[str, str]]) -> list[str]:
    """``scan_source`` over ``(filename, source)`` pairs."""
    out: list[str] = []
    for filename, source in sources:
        out.extend(scan_source(source, filename=filename))
    return out
