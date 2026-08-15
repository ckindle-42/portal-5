"""Boundary / import-scan tests (MASTER SS3), grown across P1 as modules land.

Static source-text scans, not behavioral tests: they prove *what a module
is allowed to import*, independent of whether it is exercised at runtime.
Each assertion here maps to one boundary-rule bullet in MASTER SS3 /
FINAL_ARCHITECTURE SS2.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BULLY_DIR = REPO_ROOT / "portal" / "modules" / "security" / "core" / "bully"


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _bully_module(name: str) -> Path:
    return BULLY_DIR / f"{name}.py"


def test_only_store_touches_sql():
    """MASTER SS3: 'Only store.py performs SQL I/O.'"""
    for path in BULLY_DIR.glob("*.py"):
        if path.stem in ("store",):
            continue
        text = path.read_text(encoding="utf-8")
        assert "sqlite3" not in _imported_names(path), f"{path.name} imports sqlite3"
        assert "import sqlite3" not in text, f"{path.name} imports sqlite3"


def test_only_organ_touches_the_projection_import():
    """MASTER SS3: 'Only organ.py touches the hunt_memory projection.'

    lancedb is the projection client library; nothing but organ.py may
    import it.
    """
    for path in BULLY_DIR.glob("*.py"):
        if path.stem == "organ":
            continue
        assert "lancedb" not in _imported_names(path), f"{path.name} imports lancedb"


def test_pure_compute_modules_avoid_network_and_sql_imports():
    """MASTER SS3: cousin_engine/targeting/plateau/scoreboard/costing/roster/
    signatures/drift_engine are pure compute over injected data -- no network,
    no SQL. Only the modules that exist so far are checked here; later
    phases' modules (targeting.py etc.) get their own guard test when they
    land.
    """
    pure_modules = [
        m for m in ("cousin_engine", "signatures", "drift_engine") if _bully_module(m).exists()
    ]
    forbidden = {"sqlite3", "httpx", "requests", "lancedb", "urllib.request"}
    for name in pure_modules:
        imports = _imported_names(_bully_module(name))
        hit = imports & forbidden
        assert not hit, f"{name}.py is supposed to be pure compute but imports {hit}"


def _imported_symbols(path: Path) -> set[str]:
    """Every name actually bound by an `import`/`from ... import` statement
    (as opposed to `_imported_names`, which returns the *module* being
    imported from) -- used to prove a specific symbol is never imported,
    regardless of prose mentioning its name in a docstring/comment."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def test_mutation_module_imports_nothing_beyond_the_public_scenario_surface():
    """C9 guard test: MUT (`mutation.py`) never *imports* the Red-internals
    lab-execution entry points (`_prepare_scenario`/`_run_chain_test`/
    `set_scenario`) or SQL/network -- it emits data (a `ScenarioOverlay`)
    that `orchestrator.py` alone hands to those unchanged functions. (The
    module's own docstring names these functions in prose to document the
    boundary it respects -- an AST import-scan, not a text search, is what
    proves the boundary itself.)"""
    path = _bully_module("mutation")
    if not path.exists():
        pytest.skip("mutation.py not landed yet")
    imported_symbols = _imported_symbols(path)
    forbidden_names = {"_prepare_scenario", "_run_chain_test", "set_scenario"}
    hit = imported_symbols & forbidden_names
    assert not hit, f"mutation.py imports Red-internals symbol(s) {hit}"
    imports = _imported_names(path)
    forbidden_modules = {"sqlite3", "httpx", "requests", "lancedb", "urllib.request"}
    hit_modules = imports & forbidden_modules
    assert not hit_modules, f"mutation.py imports {hit_modules}"


def test_mutation_module_never_edits_red_source():
    """M1/C9: 'Red source provably unedited' -- exec_chain.py and lab.py are
    never imported for write, and this repo's git history for this build
    never touches them (checked separately via `git diff main -- ...` in
    the phase's own verification, not here -- this test covers the static
    import-boundary half)."""
    path = _bully_module("mutation")
    if not path.exists():
        pytest.skip("mutation.py not landed yet")
    imports = _imported_names(path)
    assert "exec_chain" not in {i.split(".")[-1] for i in imports}
    assert "lab" not in {i.split(".")[-1] for i in imports}


def test_bully_package_never_imports_mcp_modules():
    """MASTER SS3 / Rule 3: 'the bully package never imports MCP modules.'"""
    for path in BULLY_DIR.glob("*.py"):
        imports = _imported_names(path)
        mcp_imports = {i for i in imports if "mcp" in i.split(".")}
        assert not mcp_imports, f"{path.name} imports an MCP module: {mcp_imports}"


def test_no_mcp_module_imports_bully():
    """MASTER SS3 / Rule 3, the converse: no MCP module imports bully."""
    mcp_dirs = [
        REPO_ROOT / "portal" / "modules" / "security" / "tools",
        REPO_ROOT / "portal" / "modules" / "general" / "tools",
        REPO_ROOT / "portal" / "modules" / "media" / "tools",
        REPO_ROOT / "portal" / "modules" / "research" / "tools",
        REPO_ROOT / "portal" / "modules" / "documents" / "tools",
        REPO_ROOT / "portal" / "modules" / "coding" / "tools",
    ]
    for d in mcp_dirs:
        if not d.exists():
            continue
        for path in d.glob("*.py"):
            imports = _imported_names(path)
            hit = {i for i in imports if "bully" in i.split(".")}
            assert not hit, f"{path} imports bully: {hit}"


def test_bully_never_imports_recall_attribution():
    """MASTER SS3 / Rule BM: label-blind -- production code never imports
    recall_attribution."""
    for path in BULLY_DIR.glob("*.py"):
        imports = _imported_names(path)
        hit = {i for i in imports if i.endswith("recall_attribution") or "recall_attribution" in i}
        assert not hit, f"{path.name} imports recall_attribution: {hit}"


def test_bully_does_not_import_training_extras_at_module_scope():
    """Rule 8 precedent + MASTER SS4: training libraries never imported by a
    runtime startup path. At P1 no module has a legitimate reason to import
    mlx_lm/torch/transformers at module (top-level) scope; training.py lands
    in P6 and must do any such import lazily inside its own functions."""
    forbidden = {"mlx_lm", "torch", "transformers", "mlx_vlm"}
    for path in BULLY_DIR.glob("*.py"):
        imports = _imported_names(path)
        hit = imports & forbidden
        assert not hit, f"{path.name} imports a training extra at module scope: {hit}"


def test_only_orchestrator_sequences_the_lab_execution_functions():
    """MASTER SS3: 'Only orchestrator.py sequences a hunt iteration' --
    the unchanged exec_chain/blue lab-execution entry points are called
    from exactly one bully module."""

    def _calls(path: Path, names: set[str]) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and (node.module.endswith("exec_chain") or node.module.endswith(".blue"))
            ):
                found |= {alias.name for alias in node.names} & names
        return found

    lab_functions = {"_prepare_scenario", "_run_chain_test", "collect_and_ship_scenario_telemetry"}
    callers = {}
    for path in BULLY_DIR.glob("*.py"):
        hit = _calls(path, lab_functions)
        if hit:
            callers[path.stem] = hit
    assert set(callers.keys()) <= {"orchestrator"}, callers


def test_model_calls_only_inside_investigation_and_future_model_calling_modules():
    """MASTER SS3: model calls happen only inside investigation.py (P1) and
    later adversary.py/handoff.py/playbooks.py -- never orchestrator.py or
    the pure-compute modules directly."""
    allowed = {"investigation", "adversary", "handoff", "playbooks"}
    for path in BULLY_DIR.glob("*.py"):
        if path.stem in allowed:
            continue
        imports = _imported_names(path)
        hit = {
            i
            for i in imports
            if i.endswith("_run_three_section") or i.endswith("agentic_blue_eval")
        }
        assert not hit, f"{path.name} imports a model-calling entry point: {hit}"


def test_no_hardcoded_model_tag_string_in_bully_source():
    """MASTER SS5/SS11: no bully module hardcodes a model tag. A cheap proxy
    check: none of the current Ollama-catalog naming conventions
    (":q4", ":latest", "-gguf") appear as literal substrings in bully source,
    which would indicate a baked-in tag rather than a config-resolved alias."""
    suspicious_substrings = (":q4_k_m", ":q8_0", "-gguf", ":latest")
    for path in BULLY_DIR.glob("*.py"):
        lowered = path.read_text(encoding="utf-8").lower()
        for needle in suspicious_substrings:
            assert needle not in lowered, (
                f"{path.name} appears to hardcode a model tag ({needle!r})"
            )
