"""Unit tests for the deterministic SCAD emitter (TASK_CAD_MODULE_OVERHAUL_V1 Phase 2).

Structural/coordinate-math validation — no openscad binary or LLM involved.
Mirrors P2.2/P2.6: feature-based box, hole+offset, hole pattern, shell,
standoffs, and one Tier-B escape-hatch fixture.
"""

from __future__ import annotations

import re

import pytest

from portal.modules.cad.tools.scad_emitter import (
    EmitError,
    emit_scad,
    eval_expr,
    resolve_parameters,
    validate_geometry,
)


def _balanced_braces(scad: str) -> bool:
    depth = 0
    for ch in scad:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _assert_structurally_valid(scad: str) -> None:
    assert _balanced_braces(scad)
    assert "difference() {  }" not in scad
    assert "union() {  }" not in scad
    assert re.search(r"^\$fn\s*=\s*\d+;", scad, re.MULTILINE)


# ── fixture 1: feature-based box with named params ─────────────────────────


def test_feature_box_with_named_params():
    geo = {
        "parameters": {"width": 30, "depth": 20, "height": 10},
        "base": {
            "type": "box",
            "dimensions": {"width": "width", "depth": "depth", "height": "height"},
        },
    }
    scad = emit_scad(geo)
    _assert_structurally_valid(scad)
    assert "width = 30;" in scad
    assert "depth = 20;" in scad
    assert "height = 10;" in scad
    assert "cube([30, 20, 10]);" in scad


# ── fixture 2: hole on a named face with offset ─────────────────────────────


def test_hole_on_face_with_offset_lands_at_correct_coordinate():
    geo = {
        "base": {"type": "box", "dimensions": {"width": 20, "depth": 10, "height": 5}},
        "holes": [
            {
                "diameter": 3,
                "face": "top",
                "offset_from": "edge",
                "offset_x": 5,
                "offset_y": 5,
            }
        ],
    }
    scad = emit_scad(geo)
    _assert_structurally_valid(scad)
    # top face, corner-anchored: (5, 5, height + EPSILON=0.5) => (5, 5, 5.5)
    assert "translate([5, 5, 5.5])" in scad
    assert "rotate([180, 0, 0])" in scad
    assert "r=1.5" in scad


def test_hole_5mm_from_each_end_on_20mm_face():
    """'5mm from each end on a 20mm face' — both ends symmetric at width=20."""
    geo = {
        "base": {"type": "box", "dimensions": {"width": 20, "depth": 10, "height": 5}},
        "holes": [
            {"diameter": 3, "face": "front", "offset_from": "edge", "offset_x": 5, "offset_y": 2},
            {"diameter": 3, "face": "front", "offset_from": "edge", "offset_x": 15, "offset_y": 2},
        ],
    }
    scad = emit_scad(geo)
    # front face: corner=(0,0,0), u=x, v=z; offset_x=5 -> x=5; offset_x=15 -> x=15 (20-5)
    assert "translate([5, -0.5, 2])" in scad
    assert "translate([15, -0.5, 2])" in scad


# ── fixture 3: circular hole pattern ────────────────────────────────────────


def test_circular_hole_pattern_count_and_symmetry():
    geo = {
        "base": {"type": "cylinder", "dimensions": {"radius": 20, "height": 5}},
        "holes": [
            {"diameter": 4, "face": "top", "offset_from": "corner", "offset_x": 30, "offset_y": 20}
        ],
        "pattern": {
            "type": "circular",
            "feature_kind": "holes",
            "feature_index": 0,
            "count": 4,
            "angle": 360,
        },
    }
    scad = emit_scad(geo)
    _assert_structurally_valid(scad)
    assert scad.count("cylinder(h=") >= 5  # base cylinder + 4 pattern holes (subtractive)
    # 4 evenly spaced translate() calls for the pattern holes
    translates = re.findall(r"translate\(\[(-?[\d.]+), (-?[\d.]+), 5\.5\]\)", scad)
    assert len(translates) == 4


# ── fixture 4: shell / hollow ────────────────────────────────────────────────


def test_shell_hollow_open_top():
    geo = {
        "base": {"type": "box", "dimensions": {"width": 40, "depth": 30, "height": 20}},
        "shell": {"wall_thickness": 2, "open_face": "top"},
    }
    scad = emit_scad(geo)
    _assert_structurally_valid(scad)
    assert "cube([40, 30, 20]);" in scad
    # inner cavity inset by wall thickness, open through the top (full height)
    assert "translate([2, 2, 2]) cube([36, 26, 20]);" in scad


# ── fixture 5: standoff bosses ───────────────────────────────────────────────


def test_standoff_boss_with_pilot_hole():
    geo = {
        "base": {"type": "box", "dimensions": {"width": 50, "depth": 50, "height": 15}},
        "standoffs": [
            {
                "outer_diameter": 6,
                "inner_diameter": 3,
                "height": 8,
                "face": "top",
                "offset_from": "corner",
                "offset_x": 5,
                "offset_y": 5,
            }
        ],
    }
    scad = emit_scad(geo)
    _assert_structurally_valid(scad)
    assert "union() {" in scad
    assert "r=3" in scad  # outer radius
    assert "r=1.5" in scad  # inner (pilot) radius


# ── fixture 6: Tier-B escape hatch CSG ───────────────────────────────────────


def test_tier_b_escape_hatch_csg_part():
    geo = {
        "base": {"type": "cylinder", "dimensions": {"radius": 10, "height": 20}},
        "escape_hatch": {
            "csg": {
                "op": "difference",
                "children": [
                    {"op": "cylinder", "dimensions": {"radius": 10, "height": 20}},
                    {
                        "op": "translate",
                        "vector": [0, 0, 5],
                        "child": {"op": "cylinder", "dimensions": {"radius": 5, "height": 20}},
                    },
                ],
            }
        },
    }
    scad = emit_scad(geo)
    _assert_structurally_valid(scad)
    assert scad.count("cylinder(h=20, r=10") == 1  # base not double-unioned with escape hatch
    assert "difference() {" in scad
    assert "translate([0, 0, 5])" in scad


# ── error handling ───────────────────────────────────────────────────────────


def test_invalid_geometry_missing_base_returns_structured_error():
    errors = validate_geometry({})
    assert errors and "base" in errors[0]


def test_invalid_geometry_raises_emit_error_not_traceback():
    with pytest.raises(EmitError):
        emit_scad({"base": {"type": "sphere", "dimensions": {}}})


def test_undefined_parameter_reference_is_structured_error():
    with pytest.raises(EmitError) as exc:
        emit_scad(
            {
                "parameters": {"width": "undefined_name * 2"},
                "base": {
                    "type": "box",
                    "dimensions": {"width": "width", "depth": 10, "height": 10},
                },
            }
        )
    assert exc.value.category == "undefined_variable"


def test_restricted_evaluator_rejects_non_arithmetic():
    with pytest.raises(EmitError):
        eval_expr("__import__('os').system('echo hi')", {})


def test_resolve_parameters_supports_forward_references():
    resolved = resolve_parameters({"a": "b + 1", "b": 2})
    assert resolved == {"a": 3.0, "b": 2.0}


def test_resolve_parameters_detects_cycle():
    with pytest.raises(EmitError):
        resolve_parameters({"a": "b", "b": "a"})


def test_deterministic_same_input_same_output():
    geo = {
        "base": {"type": "box", "dimensions": {"width": 10, "depth": 10, "height": 10}},
        "holes": [
            {"diameter": 3, "face": "top", "offset_from": "center", "offset_x": 0, "offset_y": 0}
        ],
    }
    assert emit_scad(geo) == emit_scad(geo)
