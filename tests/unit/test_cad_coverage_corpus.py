from __future__ import annotations

import shutil
import subprocess

import pytest
import trimesh

from portal.modules.cad.tools.scad_emitter import emit_scad


def _base(width=40, depth=30, height=5):
    return {"type": "box", "dimensions": {"width": width, "depth": depth, "height": height}}


def _corpus_boxes():
    return [
        ("plain_plate", {"metadata": {"part_name": "plain_plate"}, "base": _base()}, (40, 30, 5)),
        (
            "grommet_plate",
            {
                "base": _base(80, 30, 4),
                "holes": [
                    {
                        "diameter": 10,
                        "chamfer": 1,
                        "face": "top",
                        "offset_from": "edge",
                        "offset_x": 15,
                        "offset_y": 15,
                    }
                ],
                "pattern": {
                    "type": "linear",
                    "feature_kind": "holes",
                    "feature_index": 0,
                    "count": 3,
                    "spacing": 25,
                },
            },
            (80, 30, 4),
        ),
        (
            "drilled_standoff",
            {
                "base": _base(50, 40, 4),
                "standoffs": [
                    {
                        "outer_diameter": 8,
                        "inner_diameter": 3,
                        "height": 8,
                        "face": "top",
                        "offset_from": "corner",
                        "offset_x": 8,
                        "offset_y": 8,
                    }
                ],
            },
            (50, 40, 12),
        ),
        (
            "open_enclosure",
            {"base": _base(60, 40, 25), "shell": {"wall_thickness": 2, "open_face": "top"}},
            (60, 40, 25),
        ),
        (
            "mounting_bracket",
            {
                "base": _base(30, 20, 4),
                "ribs": [
                    {
                        "thickness": 3,
                        "height": 8,
                        "face": "top",
                        "offset_from": "center",
                        "offset_x": 0,
                        "offset_y": 0,
                    }
                ],
            },
            (30, 20, 12),
        ),
    ]


def _corpus_more():
    return [
        (
            "vented_panel",
            {
                "base": _base(50, 30, 3),
                "pockets": [
                    {
                        "width": 3,
                        "depth_dim": 20,
                        "cut_depth": 3,
                        "face": "top",
                        "offset_from": "edge",
                        "offset_x": 8,
                        "offset_y": 5,
                    }
                ],
                "pattern": {
                    "type": "linear",
                    "feature_kind": "pockets",
                    "feature_index": 0,
                    "count": 5,
                    "spacing": 8,
                },
            },
            (50, 30, 3),
        ),
        (
            "cylindrical_adapter",
            {
                "base": {"type": "cylinder", "dimensions": {"radius": 15, "height": 12}},
                "holes": [
                    {
                        "diameter": 8,
                        "counterbore": {"diameter": 12, "depth": 3},
                        "face": "top",
                        "offset_from": "center",
                        "offset_x": 0,
                        "offset_y": 0,
                    }
                ],
            },
            (30, 30, 12),
        ),
        (
            "chamfered_block",
            {
                "base": _base(35, 25, 8),
                "chamfers": [{"size": 1, "edges": "top"}, {"size": 0.5, "edges": "bottom"}],
            },
            (35, 25, 8),
        ),
        (
            "filleted_block",
            {"base": _base(35, 25, 8), "fillets": [{"radius": 1, "edges": "all"}]},
            (35, 25, 8),
        ),
    ]


def _corpus_disc():
    return [
        (
            "gearish_disc",
            {
                "base": {"type": "cylinder", "dimensions": {"radius": 18, "height": 6}},
                "holes": [
                    {
                        "diameter": 3,
                        "face": "top",
                        "offset_from": "corner",
                        "offset_x": 28,
                        "offset_y": 18,
                    }
                ],
                "pattern": {
                    "type": "circular",
                    "feature_kind": "holes",
                    "feature_index": 0,
                    "count": 8,
                    "angle": 360,
                },
            },
            (36, 36, 6),
        ),
    ]


CORPUS = _corpus_boxes() + _corpus_more() + _corpus_disc()


@pytest.mark.parametrize(("name", "geometry", "expected"), CORPUS, ids=[item[0] for item in CORPUS])
def test_corpus_emits(name, geometry, expected):
    source = emit_scad(geometry)
    assert source.startswith("// units=mm")
    assert len(source) > 50


@pytest.mark.skipif(shutil.which("openscad") is None, reason="OpenSCAD is not installed")
@pytest.mark.parametrize(("name", "geometry", "expected"), CORPUS, ids=[item[0] for item in CORPUS])
def test_corpus_compiles_watertight_with_expected_bbox(tmp_path, name, geometry, expected):
    scad_path = tmp_path / f"{name}.scad"
    stl_path = tmp_path / f"{name}.stl"
    scad_path.write_text(emit_scad(geometry))
    result = subprocess.run(
        [shutil.which("openscad"), "--render", "-o", str(stl_path), str(scad_path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    mesh = trimesh.load(stl_path, force="mesh")
    assert mesh.is_watertight
    assert tuple(mesh.extents) == pytest.approx(expected, abs=0.15)
