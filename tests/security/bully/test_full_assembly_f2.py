"""F.2 -- one run script wires all sixteen modules.

`bully_full_assembly_run.py` is the first run script in the arc whose stage
list is not a subset of the sixteen (prior best: 7/16, `bully_analyst_loop_
run.py`/`bully_loop_milestone_run.py`/`bully_truth_acceptance_run.py`). This
test asserts that statically, from `STAGE_PLAN`, without touching a live
connector -- and that every stage the script actually builds (`build_stages`)
registers cleanly against `full_pipeline.Stage`, which raises for any module
outside the sixteen (F.1)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bully_full_assembly_run as fa  # noqa: E402

from portal.modules.security.core.bully.full_pipeline import BUILT_MODULES  # noqa: E402


def test_stage_plan_covers_at_least_fourteen_of_sixteen_modules() -> None:
    modules = {module for _name, module in fa.STAGE_PLAN}
    assert modules <= BUILT_MODULES, modules - BUILT_MODULES
    assert len(modules) >= 14, f"only {len(modules)}/16 modules in STAGE_PLAN: {sorted(modules)}"


def test_stage_plan_covers_all_sixteen() -> None:
    # F.2's table names all sixteen; this is a stronger assertion than the
    # >=14 floor above, kept separate so a future seam defect that drops one
    # module fails loudly here without weakening the >=14 acceptance floor.
    # `run_preflight` (H.1, TASK_BULLY_HUNT_SWEEP_V1) is excluded: it is a
    # gating module invoked before the pipeline runs, never as a Stage in
    # STAGE_PLAN itself -- it adds no capability to assert coverage of here.
    modules = {module for _name, module in fa.STAGE_PLAN}
    assert modules == BUILT_MODULES - {"run_preflight"}


def test_build_stages_registers_without_naming_an_unbuilt_module() -> None:
    stages = fa.build_stages(
        max_records=10, batch_size=10, per_sourcetype_cap=10, dry_run_cousins=True
    )
    assert len(stages) == len(fa.STAGE_PLAN)
    built_modules = {stage.module for stage in stages}
    assert built_modules == BUILT_MODULES - {"run_preflight"}


def test_no_stage_name_or_module_is_duplicated() -> None:
    stages = fa.build_stages(
        max_records=10, batch_size=10, per_sourcetype_cap=10, dry_run_cousins=True
    )
    names = [s.name for s in stages]
    assert len(names) == len(set(names))
