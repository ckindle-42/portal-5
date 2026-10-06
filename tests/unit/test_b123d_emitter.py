"""Kernel parity: the build123d backend vs. the IR's expected geometry (and the SCAD
mesh when OpenSCAD is installed). TASK_CAD_ARM_REDEVELOP_V1 P3."""

from __future__ import annotations

import shutil
import subprocess

import pytest

pytest.importorskip("build123d")
trimesh = pytest.importorskip("trimesh")

from build123d import export_stl  # noqa: E402

from portal.modules.cad.tools.b123d_emitter import emit_build123d  # noqa: E402
from portal.modules.cad.tools.part_plan import EmitError  # noqa: E402
from portal.modules.cad.tools.scad_emitter import emit_scad  # noqa: E402
from tests.unit.test_cad_coverage_corpus import CORPUS  # noqa: E402

# Through-hole counts (genus) for each corpus part — derived from the IR by hand.
GENUS = {
    "plain_plate": 0,
    "grommet_plate": 3,
    "drilled_standoff": 0,  # the pilot bore stops at the base face
    "open_enclosure": 0,
    "mounting_bracket": 0,
    "vented_panel": 5,
    "cylindrical_adapter": 1,
    "chamfered_block": 0,
    "filleted_block": 0,
    "gearish_disc": 8,
}
TREATED = {"grommet_plate", "chamfered_block", "filleted_block"}  # SCAD side is faceted


def _build(script: str):
    ns: dict = {}
    captured: dict = {}
    exec("from build123d import *", ns)  # noqa: S102 — our own emitted script
    ns["show"] = lambda obj, name=None: captured.setdefault("part", obj)
    exec(script, ns)  # noqa: S102
    return captured["part"]


def _mesh(part, tmp_path, name):
    path = tmp_path / f"{name}.stl"
    export_stl(part, str(path), tolerance=0.01, angular_tolerance=0.1)
    mesh = trimesh.load(str(path), force="mesh")
    mesh.merge_vertices()
    # OCC's tessellation of spherical corner blends leaves a few zero-area sliver
    # triangles; they are mesh artifacts (the BREP solid is valid), not geometry.
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    return mesh


def _genus(mesh) -> int:
    return (2 - int(mesh.euler_number)) // 2


@pytest.mark.parametrize(("name", "geometry", "expected"), CORPUS, ids=[c[0] for c in CORPUS])
def test_corpus_parity(tmp_path, name, geometry, expected):
    part = _build(emit_build123d(geometry))
    assert len(part.solids()) == 1 and part.is_valid
    mesh = _mesh(part, tmp_path, name)
    assert mesh.is_watertight
    assert sorted(mesh.extents) == pytest.approx(sorted(expected), abs=0.05)
    assert _genus(mesh) == GENUS[name]

    openscad = shutil.which("openscad-nightly") or shutil.which("openscad")
    if openscad is None:
        return
    scad, stl = tmp_path / f"{name}.scad", tmp_path / f"{name}_scad.stl"
    scad.write_text(emit_scad(geometry))
    subprocess.run(  # noqa: S603
        [openscad, "--render", "-o", str(stl), str(scad)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    ref = trimesh.load(str(stl), force="mesh")
    ref.merge_vertices()
    assert _genus(ref) == _genus(mesh)
    tol = 0.05 if name in TREATED else 0.02
    assert mesh.volume == pytest.approx(ref.volume, rel=tol)


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
