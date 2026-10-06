"""Deterministic SCAD emitter for generate_scad's Tier-A/B geometry schema
(TASK_CAD_MODULE_OVERHAUL_V1 Phase 2 — config/inference/cad_geometry_schema.json).

Pure code, no LLM calls: same JSON in -> same SCAD out. This module owns ALL
coordinate-frame math and CSG ordering so the model never computes a 3D
translate/rotate itself — Tier A lets the model say "an M3 hole on the top
face, 5mm from each end" and this emitter turns that into the actual
`translate([...]) rotate([...]) cylinder(...)`. That is the entire point: it
removes the spatial-reasoning burden that breaks LLM OpenSCAD past ~20 lines.

Coordinate convention: Z-up, right-handed. The base solid's local frame has
its "min" corner at the origin: a box spans x in [0,width], y in [0,depth],
z in [0,height]; a cylinder's XY footprint also starts at (0,0), with its
axis at (radius,radius), and z in [0,height].
"""

from __future__ import annotations

import math
from typing import Any

from portal.modules.cad.tools.part_plan import (
    EPSILON,
    SCHEMA_PATH,
    BasePlan,
    CsgPlan,
    EdgeTreatment,
    EmitError,
    HolePlan,
    PartPlan,
    PrimBox,
    PrimCylinder,
    StandoffPlan,
    Vec3,
    _face_frame,
    eval_expr,
    geometry_schema,
    plan_part,
    resolve_parameters,
    resolve_value,
    validate_geometry,
)

__all__ = [
    "EPSILON",
    "FN_DEFAULT",
    "SCHEMA_PATH",
    "EmitError",
    "emit_scad",
    "eval_expr",
    "geometry_schema",
    "render_scad",
    "resolve_parameters",
    "resolve_value",
    "validate_geometry",
]

FN_DEFAULT = 48


def _fmt(n: float) -> str:
    if abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    return f"{n:.4f}".rstrip("0").rstrip(".")


def _vec(v: Vec3) -> str:
    return f"[{_fmt(v[0])}, {_fmt(v[1])}, {_fmt(v[2])}]"


# ── feature renderers (plan -> SCAD text) ────────────────────────────────────


def _emit_hole(hole: HolePlan, base: BasePlan) -> str:
    frame = _face_frame(hole.face, base.width, base.depth, base.height)
    px, py, pz = hole.point
    nx, ny, nz = frame["inward_normal"]
    start = (px - nx * EPSILON, py - ny * EPSILON, pz - nz * EPSILON)
    length = hole.depth + 2 * EPSILON
    diameter = hole.diameter
    r = _fmt(diameter / 2)
    transform = f"translate({_vec(start)}) rotate({_vec(frame['inward_rotate'])})"
    cuts = [f"{transform} cylinder(h={_fmt(length)}, r={r}, $fn=$fn);"]
    if hole.chamfer is not None:
        size = hole.chamfer
        cuts.append(
            f"{transform} cylinder(h={_fmt(size + EPSILON)}, r1={_fmt(diameter / 2 + size)}, "
            f"r2={r}, $fn=$fn);"
        )
    if hole.counterbore:
        cb_diameter, cb_depth = hole.counterbore
        cuts.append(
            f"{transform} cylinder(h={_fmt(cb_depth + EPSILON)}, r={_fmt(cb_diameter / 2)}, $fn=$fn);"
        )
    if hole.countersink:
        cs_diameter, cs_depth = hole.countersink
        cuts.append(
            f"{transform} cylinder(h={_fmt(cs_depth + EPSILON)}, r1={_fmt(cs_diameter / 2)}, "
            f"r2={r}, $fn=$fn);"
        )
    return cuts[0] if len(cuts) == 1 else "union() { " + " ".join(cuts) + " }"


def _emit_standoff(item: StandoffPlan, base: BasePlan) -> str:
    frame = _face_frame(item.face, base.width, base.depth, base.height)
    px, py, pz = item.point
    nx, ny, nz = frame["inward_normal"]
    start = (px + nx * EPSILON, py + ny * EPSILON, pz + nz * EPSILON)
    length = item.height + EPSILON
    boss = (
        f"translate({_vec(start)}) rotate({_vec(frame['outward_rotate'])}) "
        f"cylinder(h={_fmt(length)}, r={_fmt(item.outer_diameter / 2)}, $fn=$fn)"
    )
    if item.inner_diameter:
        bore = (
            f"translate({_vec(start)}) rotate({_vec(frame['outward_rotate'])}) "
            f"cylinder(h={_fmt(length + EPSILON)}, r={_fmt(item.inner_diameter / 2)}, $fn=$fn)"
        )
        return f"difference() {{ {boss}; {bore}; }}"
    return f"{boss};"


def _emit_prim(prim: PrimBox | PrimCylinder) -> str:
    if isinstance(prim, PrimBox):
        return f"translate({_vec(prim.origin)}) cube({_vec(prim.size)});"
    return (
        f"translate({_vec(prim.origin)}) "
        f"cylinder(h={_fmt(prim.height)}, r={_fmt(prim.radius)}, $fn=$fn);"
    )


def _box_profile(width: float, depth: float, z: float, inset: float, radius: float = 0) -> str:
    inner_w = max(width - 2 * (inset + radius), 0.01)
    inner_d = max(depth - 2 * (inset + radius), 0.01)
    return (
        f"translate({_vec((inset + radius, inset + radius, z))}) "
        f"linear_extrude(height=0.01) offset(r={_fmt(radius)}) "
        f"square([{_fmt(inner_w)}, {_fmt(inner_d)}]);"
    )


def _box_edge_envelope(
    width: float, depth: float, height: float, amount: float, edges: str, rounded: bool
) -> str:
    layers: list[tuple[float, float, float]] = [(0.0, 0.0, amount if rounded else 0.0)]
    steps = 5 if rounded else 1
    if edges in {"all", "bottom"}:
        layers = []
        for i in range(steps + 1):
            t = i / steps
            inset = amount * (1 - math.sin(t * math.pi / 2)) if rounded else amount * (1 - t)
            radius = amount if rounded else 0.0
            layers.append((amount * t, inset, radius))
    if edges not in {"all", "bottom"}:
        layers = [(0.0, 0.0, amount if rounded else 0.0)]
    if edges in {"all", "top"}:
        for i in range(steps + 1):
            t = i / steps
            inset = amount * (1 - math.sin(t * math.pi / 2)) if rounded else amount * (1 - t)
            radius = amount if rounded else 0.0
            layers.append((height - amount * t, inset, radius))
    else:
        layers.append((height, 0.0, amount if rounded else 0.0))
    slices = " ".join(_box_profile(width, depth, z, inset, radius) for z, inset, radius in layers)
    return f"hull() {{ {slices} }}"


def _emit_base(base: BasePlan, treatments: tuple[EdgeTreatment, ...]) -> str:
    width, depth, height = base.width, base.depth, base.height
    if base.kind == "box":
        solid = f"cube({_vec((width, depth, height))});"
    else:  # cylinder
        radius = width / 2
        solid = (
            f"translate([{_fmt(radius)}, {_fmt(radius)}, 0]) "
            f"cylinder(h={_fmt(height)}, r={_fmt(radius)}, $fn=$fn);"
        )
    for treatment in treatments:
        r = treatment.size
        edges = treatment.edges
        if base.kind == "box":
            envelope = _box_edge_envelope(
                width, depth, height, r, edges, rounded=treatment.kind == "fillet"
            )
        else:
            radius = width / 2
            bottom = r if edges in {"all", "bottom"} else 0
            top = r if edges in {"all", "top"} else 0
            envelope = (
                f"hull() {{ translate([{_fmt(radius)},{_fmt(radius)},{_fmt(bottom)}]) cylinder(h=0.01,r={_fmt(radius - bottom)},$fn=$fn); "
                f"translate([{_fmt(radius)},{_fmt(radius)},{_fmt(height - top)}]) cylinder(h=0.01,r={_fmt(radius - top)},$fn=$fn); }}"
            )
        solid = f"intersection() {{ {solid} {envelope} }}"
    return solid


def _compose_body(
    additive: list[str], subtractive: list[str], escape_stmt: str | None, has_tier_a: bool
) -> list[str]:
    if escape_stmt and not has_tier_a:
        # Escape-hatch-only part: `base` is a required schema stub, the CSG
        # subtree is the definitive geometry — don't also union in the base
        # (it would double up whatever the escape hatch already describes).
        return [escape_stmt]
    additive_expr = "union() { " + " ".join(additive) + " }" if len(additive) > 1 else additive[0]
    body = [
        "difference() { " + additive_expr + " " + " ".join(subtractive) + " }"
        if subtractive
        else additive_expr
    ]
    if escape_stmt:
        body.append(escape_stmt)
    return body


def render_scad(plan: PartPlan, fn: int = FN_DEFAULT) -> str:
    """Render a `PartPlan` as OpenSCAD source. Deterministic."""
    base = plan.base
    additive = [_emit_base(base, plan.edge_treatments)]
    for item in plan.additive:
        additive.append(
            _emit_standoff(item, base) if isinstance(item, StandoffPlan) else _emit_prim(item)
        )
    subtractive = [_emit_prim(cut) for cut in plan.shell]
    subtractive += [_emit_hole(hole, base) for hole in plan.holes]
    subtractive += [_emit_prim(pocket) for pocket in plan.pockets]
    escape_stmt = _emit_csg_node(plan.escape) + ";" if plan.escape else None
    body_parts = _compose_body(additive, subtractive, escape_stmt, plan.has_tier_a_features)

    lines = [
        f"// units={plan.units} — generated by scad_emitter.py",
        f"// part={plan.part_name.replace(chr(10), ' ')}",
        f"$fn = {fn};",
        "",
    ]
    for name, value in plan.parameters.items():
        lines.append(f"{name} = {_fmt(value)};")
    if plan.declared_parameters:
        lines.append("")
    lines.extend(body_parts)
    return "\n".join(lines) + "\n"


def emit_scad(geometry: dict[str, Any], fn: int = FN_DEFAULT) -> str:
    """Validate + resolve + build parametric OpenSCAD source. Deterministic:
    the same geometry JSON + fn always produces the same SCAD string.

    `fn` overrides $fn (tessellation) — used by generate_scad's auto-repair
    loop (P4.2) to cheapen a timing-out render or smooth a degenerate mesh,
    without touching the model's design intent.
    """
    return render_scad(plan_part(geometry), fn)


# ── Tier-B escape-hatch CSG ──────────────────────────────────────────────────


def _emit_csg_node(node: CsgPlan) -> str:
    op = node.op
    if op == "box":
        return f"cube({_vec((node.dims[0], node.dims[1], node.dims[2]))})"
    if op == "cylinder":
        return f"cylinder(h={_fmt(node.dims[1])}, r={_fmt(node.dims[0])}, $fn=$fn)"
    if op == "sphere":
        return f"sphere(r={_fmt(node.dims[0])}, $fn=$fn)"
    if op in {"translate", "rotate", "scale"}:
        assert node.child is not None
        return f"{op}({_vec(node.vector)}) {_emit_csg_node(node.child)}"
    if op in {"union", "difference", "intersection"}:
        inner = " ".join(f"{_emit_csg_node(c)};" for c in node.children)
        return f"{op}() {{ {inner} }}"
    assert node.child is not None  # linear_extrude / rotate_extrude
    arg = f"height={_fmt(node.amount)}" if op == "linear_extrude" else f"angle={_fmt(node.amount)}"
    return f"{op}({arg}) {_emit_csg_node(node.child)}"
