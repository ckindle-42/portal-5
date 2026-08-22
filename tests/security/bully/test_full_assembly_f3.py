"""F.3 -- BOTS answer keys loaded at scale, scorer-plane only.

The arc used 1-4 answer-key entries for the whole life of this project; this
asserts the expanded set actually clears F.3's floor (>=25 entries across the
three BOTS datasets, each with a technique and >=2 stage entities for
`reach_report`'s multi-entity chain requirement, A3) and that the module
stays scorer-plane-only (never imported by the grading path)."""

from __future__ import annotations

import ast
from pathlib import Path

from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_at_least_25_entries_load() -> None:
    assert len(BOTS_ANSWER_KEY) >= 25


def test_all_three_datasets_are_represented() -> None:
    datasets = {e.dataset for e in BOTS_ANSWER_KEY}
    assert {"botsv1", "botsv2", "botsv3"} <= datasets


def test_every_entry_has_a_technique_and_at_least_two_stage_entities() -> None:
    for entry in BOTS_ANSWER_KEY:
        assert entry.technique, entry
        assert len(entry.entities) >= 2, (entry.dataset, entry.technique, entry.entities)


def test_every_entry_declares_a_nonempty_behavioural_spine() -> None:
    for entry in BOTS_ANSWER_KEY:
        assert entry.behavioural_spine, (entry.dataset, entry.technique)


def test_bots_answer_key_module_is_not_imported_by_any_grading_module() -> None:
    # C4: `answer_key_visibility: scorer_only` -- the grader never sees this
    # module. Static AST check across the package so a future import can't
    # silently reintroduce it.
    bully_dir = REPO_ROOT / "portal" / "modules" / "security" / "core" / "bully"
    grading_modules = {"discovery.py", "unit_outcome.py", "loop_grader.py", "baseline.py"}
    for path in bully_dir.glob("*.py"):
        if path.name not in grading_modules:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "bots_answer_key" not in node.module, path
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "bots_answer_key" not in alias.name, path
