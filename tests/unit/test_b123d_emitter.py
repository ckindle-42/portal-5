"""Kernel parity: the build123d backend vs. the IR's expected geometry (and the SCAD
mesh when OpenSCAD is installed). TASK_CAD_ARM_REDEVELOP_V1 P3."""

from __future__ import annotations

import pytest

from portal.modules.cad.tools.b123d_emitter import emit_build123d  # noqa: E402
from portal.modules.cad.tools.part_plan import EmitError  # noqa: E402
from portal.modules.cad.tools.scad_emitter import emit_scad  # noqa: E402
from tests.unit.test_cad_coverage_corpus import CORPUS  # noqa: E402


def test_script_is_self_contained_and_deterministic():
    g = CORPUS[0][1]
    script = emit_build123d(g)
    assert script.startswith("# units=mm") and "from build123d import *" in script
    assert script.rstrip().endswith("show(part, 'part')")
    assert script == emit_build123d(g)


def test_extrude_is_a_kernel_gap():
    geometry = {
        "base": {"type": "box", "dimensions": {"width": 5, "depth": 5, "height": 5}},
        "escape_hatch": {
            "csg": {
                "op": "linear_extrude",
                "amount": 3,
                "child": {"op": "box", "dimensions": {"width": 2, "depth": 2, "height": 1}},
            }
        },
    }
    with pytest.raises(EmitError) as err:
        emit_build123d(geometry)
    assert err.value.category == "kernel_gap"


def test_mixed_fillet_and_chamfer_is_a_kernel_gap():
    geometry = {
        "base": {"type": "box", "dimensions": {"width": 20, "depth": 20, "height": 10}},
        "fillets": [{"radius": 1}],
        "chamfers": [{"size": 0.5, "edges": "top"}],
    }
    with pytest.raises(EmitError) as err:
        emit_build123d(geometry)
    assert err.value.category == "kernel_gap"


def test_user_strings_cannot_inject_script_lines():
    geometry = {
        "metadata": {"part_name": "x\nimport os\r\nos.system('id') import sys"},
        "base": {"type": "box", "dimensions": {"width": 5, "depth": 5, "height": 5}},
    }
    script = emit_build123d(geometry)
    assert "\nimport os" not in script and " " not in script and "\r" not in script
    assert [ln for ln in script.splitlines() if ln.startswith("import ")] == []


def test_parameter_names_must_be_identifiers():
    geometry = {
        "parameters": {"w\nimport os": 5},
        "base": {"type": "box", "dimensions": {"width": 5, "depth": 5, "height": 5}},
    }
    with pytest.raises(EmitError):
        emit_build123d(geometry)
    with pytest.raises(EmitError):
        emit_scad(geometry)
