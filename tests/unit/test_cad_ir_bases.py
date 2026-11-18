"""IR base types prism / revolve / angle (TASK_CAD_ARM_REDEVELOP_V1, IR extension).

Deterministic checks only — no model. The three reference IRs below describe the
same parts as the gauntlet's hex_standoff / flanged_bushing / l_bracket oracles, and the
BREP result is graded by the sealed grader: proof the IR can *express* them, so a model
that fails them has failed to describe the part, not hit a vocabulary wall.
"""

from __future__ import annotations

import pytest

from portal.modules.cad.tools.part_plan import EmitError
from portal.modules.cad.tools.scad_emitter import emit_scad, validate_geometry

HEX = {
    "base": {"type": "prism", "dimensions": {"sides": 6, "across_flats": 8, "height": 15}},
    "holes": [
        {"diameter": 3.3, "face": "top", "offset_from": "center", "offset_x": 0, "offset_y": 0}
    ],
}

BUSHING = {
    "base": {
        "type": "revolve",
        "dimensions": {"profile": [[5, 0], [15, 0], [15, 3], [8, 3], [8, 20], [5, 20]]},
    }
}

ANGLE = {
    "base": {
        "type": "angle",
        "dimensions": {"width": 40, "depth": 30, "height": 25, "thickness": 3, "inner_radius": 3},
    },
    "holes": [
        {"diameter": 4.5, "face": "bottom", "offset_from": "corner", "offset_x": x, "offset_y": 18}
        for x in (8, 32)
    ]
    + [
        {"diameter": 4.5, "face": "front", "offset_from": "corner", "offset_x": x, "offset_y": 15}
        for x in (8, 32)
    ],
}

REFERENCE = [("hex_standoff", HEX), ("flanged_bushing", BUSHING), ("l_bracket", ANGLE)]


@pytest.mark.parametrize(("task", "geometry"), REFERENCE, ids=[r[0] for r in REFERENCE])
def test_schema_accepts_reference_irs(task, geometry):
    assert validate_geometry(geometry) == []


@pytest.mark.parametrize(("task", "geometry"), REFERENCE, ids=[r[0] for r in REFERENCE])
def test_scad_is_deterministic_and_balanced(task, geometry):
    scad = emit_scad(geometry)
    assert scad == emit_scad(geometry)
    assert scad.count("{") == scad.count("}") and scad.count("(") == scad.count(")")


@pytest.mark.parametrize(
    ("geometry", "needle"),
    [
        (
            {"base": {"type": "prism", "dimensions": {"sides": 6, "height": 10}}},
            "exactly one of",
        ),
        (
            {
                "base": {
                    "type": "prism",
                    "dimensions": {"sides": 6, "across_flats": 8, "circumradius": 5, "height": 10},
                }
            },
            "exactly one of",
        ),
        (
            {
                "base": HEX["base"],
                "shell": {"wall_thickness": 1, "open_face": "top"},
            },
            "does not support shell",
        ),
        (
            {
                "base": ANGLE["base"],
                "holes": [
                    {
                        "diameter": 4,
                        "face": "top",
                        "offset_from": "corner",
                        "offset_x": 5,
                        "offset_y": 5,
                    }
                ],
            },
            "not a real surface",
        ),
        (
            {"base": {"type": "revolve", "dimensions": {"profile": [[-1, 0], [5, 0], [5, 4]]}}},
            "radii must be >= 0",
        ),
        (
            {
                "base": {
                    "type": "angle",
                    "dimensions": {"width": 20, "depth": 10, "height": 10, "thickness": 12},
                }
            },
            "do not fit",
        ),
    ],
)
def test_unsupported_combinations_are_explicit_errors(geometry, needle):
    with pytest.raises(EmitError, match=needle):
        emit_scad(geometry)
