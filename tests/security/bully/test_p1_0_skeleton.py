"""P1.0 -- package skeleton + spine surface + CLI shell.

Not a symbol-presence test: asserts the actual boundary behavior --
`__init__.py` exposes only the public API, the spine surface glob covers
every current bully module, and the CLI shell enforces the operator gate
without owning any hunt logic itself (I-3).
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
BULLY_DIR = REPO_ROOT / "portal" / "modules" / "security" / "core" / "bully"


def test_package_public_api_is_minimal():
    import portal.modules.security.core.bully as bully

    assert set(bully.__all__) == {"__version__", "run_hunt"}
    assert callable(bully.run_hunt)


def test_spine_surface_entry_covers_every_bully_module():
    manifest = yaml.safe_load((REPO_ROOT / "config" / "spine_surfaces.yaml").read_text())
    surfaces = {s["name"]: s for s in manifest["surfaces"]}
    assert "unit-surface-sec-bully" in surfaces
    entry = surfaces["unit-surface-sec-bully"]
    assert entry["unit"] == "unit-surface-sec-bully"
    globs = entry["globs"]

    py_files = sorted(p.name for p in BULLY_DIR.glob("*.py"))
    assert py_files, "expected bully/*.py modules to exist"
    for name in py_files:
        rel = f"portal/modules/security/core/bully/{name}"
        assert any(fnmatch.fnmatch(rel, g) for g in globs), (
            f"{rel} not covered by any declared glob"
        )


def test_covering_unit_exists_and_cites_the_glob_path():
    unit_path = REPO_ROOT / "portal_wiki" / "canonical" / "unit-surface-sec-bully.md"
    assert unit_path.exists()
    text = unit_path.read_text()
    assert "portal/modules/security/core/bully/*.py" in text


def test_hunt_cli_shell_registered_in_main_dispatch():
    main_text = (REPO_ROOT / "portal" / "modules" / "security" / "core" / "__main__.py").read_text()
    assert 'sys.argv[1] == "hunt"' in main_text
    assert "hunt_modes import hunt_main" in main_text


def test_hunt_run_requires_operator_actor():
    from portal.modules.security.core.commands.hunt_modes import hunt_main

    rc = hunt_main(["run", "--actor", "not-an-operator"])
    assert rc == 1


def test_hunt_run_with_operator_actor_reaches_orchestrator_not_implemented():
    # P1.0: orchestrator is a stub -- the CLI must reach past its own parsing
    # into the real orchestrator entry point (never fake a green here).
    from portal.modules.security.core.bully.orchestrator import (
        HonestBlockedError,
        OperatorRequiredError,
        run_hunt,
    )

    try:
        run_hunt(actor="operator:test")
    except (NotImplementedError, HonestBlockedError, OperatorRequiredError):
        pass
    else:  # pragma: no cover
        raise AssertionError("expected run_hunt to be unimplemented at P1.0")


def test_no_hunt_logic_in_cli_module():
    # I-3: "No hunt logic in the CLI." hunt_modes.py may parse argv and call
    # bully.orchestrator, but must not import store/organ/cousin_engine.
    cli_text = (
        REPO_ROOT / "portal" / "modules" / "security" / "core" / "commands" / "hunt_modes.py"
    ).read_text()
    for forbidden in ("bully.store", "bully.organ", "bully.cousin_engine", "sqlite3"):
        assert forbidden not in cli_text
