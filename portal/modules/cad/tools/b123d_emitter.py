"""build123d (BREP) backend for the CAD geometry IR (TASK_CAD_ARM_REDEVELOP_V1 P3).

`emit_build123d(geometry)` = `plan_part` -> a self-contained build123d algebra-mode
script. It does no coordinate math of its own: every position, size and overshoot
comes from `part_plan.PartPlan`, so this backend and `scad_emitter.render_scad`
describe the same part. Origin matches the SCAD backend (box corner at the origin).

Edge treatments are applied to the base *before* features, so feature edges are
untouched (same as the SCAD intersection envelopes). Fillets always round the
vertical edges of a box (the SCAD envelope does) plus the requested top/bottom set.
Not supported (EmitError category "kernel_gap" -> use cad_build): Tier-B
linear_extrude / rotate_extrude (the IR has no 2D primitives to extrude), and a base
with both fillets and chamfers.
"""

from __future__ import annotations

from typing import Any

from portal.modules.cad.tools.part_plan import (
    EPSILON,
    BasePlan,
    CsgPlan,
    EdgeTreatment,
    EmitError,
    HolePlan,
    PartPlan,
    PrimBox,
    PrimCylinder,
    StandoffPlan,
    _face_frame,
    plan_part,
)

_MIN = "align=(Align.MIN, Align.MIN, Align.MIN)"
_CZ = "align=(Align.CENTER, Align.CENTER, Align.MIN)"


def _comment(text: str) -> str:
    """User text inside a `#` comment: escape everything non-printable (newlines, \\r,
    \\x0b, \\u2028...) so it can never terminate the comment and start a statement."""
    return repr(str(text))[1:-1]


def _n(x: float) -> str:
    return repr(round(float(x), 6))


def _v(v: tuple[float, ...]) -> str:
    return "(" + ", ".join(_n(c) for c in v) + ")"


def _plane(origin: tuple[float, float, float], z_dir: tuple[float, float, float]) -> str:
    return f"Plane(origin={_v(origin)}, z_dir={_v(z_dir)})"


def _edge_selection(base: BasePlan, treatment: EdgeTreatment) -> str:
    edges = treatment.edges
    if base.kind == "box":
        top, bottom = "part.edges().group_by(Axis.Z)[-1]", "part.edges().group_by(Axis.Z)[0]"
        vertical = "part.edges().filter_by(Axis.Z)"
        if treatment.kind == "fillet":
            # SCAD fillet envelopes round the vertical edges regardless of `edges`.
            return {
                "all": "part.edges()",
                "top": f"{vertical} + {top}",
                "bottom": f"{vertical} + {bottom}",
            }[edges]
        return {"all": "part.edges()", "top": top, "bottom": bottom}[edges]
    circles = "part.edges().filter_by(GeomType.CIRCLE)"
    return {
        "all": circles,
        "top": f"{circles}.group_by(Axis.Z)[-1]",
        "bottom": f"{circles}.group_by(Axis.Z)[0]",
    }[edges]


def _prim(prim: PrimBox | PrimCylinder) -> str:
    if isinstance(prim, PrimBox):
        return f"Pos{_v(prim.origin)} * Box{_v(prim.size)[:-1]}, {_MIN})"
    return f"Pos{_v(prim.origin)} * Cylinder({_n(prim.radius)}, {_n(prim.height)}, {_CZ})"


def _hole_lines(hole: HolePlan, base: BasePlan) -> list[str]:
    nx, ny, nz = _face_frame(hole.face, base.width, base.depth, base.height)["inward_normal"]
    px, py, pz = hole.point
    plane = _plane((px - nx * EPSILON, py - ny * EPSILON, pz - nz * EPSILON), (nx, ny, nz))
    r = hole.diameter / 2
    out = [
        f"part -= {plane} * Cylinder({_n(r)}, {_n(hole.depth + 2 * EPSILON)}, {_CZ})",
    ]
    if hole.chamfer is not None:  # 45 degree cone, extended past the face to keep the slope
        size = hole.chamfer
        out.append(
            f"part -= {plane} * Cone({_n(r + size + EPSILON)}, {_n(r)}, {_n(size + EPSILON)}, {_CZ})"
        )
    if hole.counterbore:
        cb_d, cb_depth = hole.counterbore
        out.append(f"part -= {plane} * Cylinder({_n(cb_d / 2)}, {_n(cb_depth + EPSILON)}, {_CZ})")
    if hole.countersink:
        cs_d, cs_depth = hole.countersink
        slope = (cs_d / 2 - r) / cs_depth
        out.append(
            f"part -= {plane} * Cone({_n(cs_d / 2 + slope * EPSILON)}, {_n(r)}, "
            f"{_n(cs_depth + EPSILON)}, {_CZ})"
        )
    return out


def _standoff_lines(item: StandoffPlan, base: BasePlan) -> list[str]:
    nx, ny, nz = _face_frame(item.face, base.width, base.depth, base.height)["inward_normal"]
    px, py, pz = item.point
    plane = _plane((px + nx * EPSILON, py + ny * EPSILON, pz + nz * EPSILON), (-nx, -ny, -nz))
    length = item.height + EPSILON
    boss = f"{plane} * Cylinder({_n(item.outer_diameter / 2)}, {_n(length)}, {_CZ})"
    if item.inner_diameter:
        bore = f"{plane} * Cylinder({_n(item.inner_diameter / 2)}, {_n(length + EPSILON)}, {_CZ})"
        return [f"part += ({boss}) - ({bore})"]
    return [f"part += {boss}"]


def _csg(node: CsgPlan) -> str:
    op = node.op
    if op == "box":
        return f"Box({_n(node.dims[0])}, {_n(node.dims[1])}, {_n(node.dims[2])}, {_MIN})"
    if op == "cylinder":
        return f"Cylinder({_n(node.dims[0])}, {_n(node.dims[1])}, {_CZ})"
    if op == "sphere":
        return f"Sphere({_n(node.dims[0])})"
    if op in {"translate", "rotate", "scale"} and node.child is not None:
        inner = _csg(node.child)
        if op == "translate":
            return f"(Pos{_v(node.vector)} * {inner})"
        if op == "rotate":
            return f"(Rot{_v(node.vector)} * {inner})"
        return f"scale({inner}, by={_v(node.vector)})"
    if op in {"union", "difference", "intersection"}:
        sep = {"union": " + ", "difference": " - ", "intersection": " & "}[op]
        return "(" + sep.join(_csg(c) for c in node.children) + ")"
    raise EmitError(
        f"Tier-B '{op}' has no build123d equivalent here (the IR has no 2D primitives to "
        "extrude); build this part with cad_build instead",
        category="kernel_gap",
    )


def _header(plan: PartPlan) -> list[str]:
    lines = [
        f"# units={_comment(plan.units)} — generated by b123d_emitter.py",
        f"# part={_comment(plan.part_name)}",
        "from build123d import *",
        "",
    ]
    for name, value in plan.parameters.items():
        lines.append(f"param_{name} = {_n(value)}")
    if plan.declared_parameters:
        lines.append("")
    return lines


def _poly(points: tuple[tuple[float, float], ...]) -> str:
    return ", ".join(_v(p) for p in points)


def _base_solid_lines(base: BasePlan) -> list[str]:
    if base.kind == "box":
        return [f"part = Box({_n(base.width)}, {_n(base.depth)}, {_n(base.height)}, {_MIN})"]
    if base.kind == "prism":
        return [
            f"part = extrude(make_face(Polyline({_poly(base.points)}, close=True)), "
            f"amount={_n(base.height)})"
        ]
    if base.kind == "revolve":
        r = _n(base.width / 2)
        return [
            f"part = Pos({r}, {r}, 0) * revolve("
            f"make_face(Plane.XZ * Polyline({_poly(base.points)}, close=True)), Axis.Z)"
        ]
    if base.kind == "angle":
        t = _n(base.thickness)
        lines = [
            f"part = Box({_n(base.width)}, {_n(base.depth)}, {t}, {_MIN}) + "
            f"Box({_n(base.width)}, {t}, {_n(base.height)}, {_MIN})"
        ]
        if base.inner_radius > 0:
            lo, hi = _n(base.thickness - 0.01), _n(base.thickness + 0.01)
            lines.append(
                "part = fillet(part.edges().filter_by(Axis.X)"
                f".filter_by_position(Axis.Y, {lo}, {hi}).filter_by_position(Axis.Z, {lo}, {hi}), "
                f"{_n(base.inner_radius)})"
            )
        return lines
    return [f"part = Cylinder({_n(base.width / 2)}, {_n(base.height)}, {_MIN})"]


def _base_lines(plan: PartPlan) -> list[str]:
    base = plan.base
    kinds = {t.kind for t in plan.edge_treatments}
    if kinds == {"fillet", "chamfer"}:
        raise EmitError(
            "mixing fillets and chamfers on one base has no stable BREP edge selection "
            "(the second op would target the first op's blended edges); use one kind, or "
            "build this part with cad_build",
            category="kernel_gap",
        )
    lines = _base_solid_lines(base)
    for treatment in plan.edge_treatments:
        op = "fillet" if treatment.kind == "fillet" else "chamfer"
        lines.append(f"part = {op}({_edge_selection(base, treatment)}, {_n(treatment.size)})")
    return lines


def render_build123d(plan: PartPlan) -> str:
    """Render a `PartPlan` as a build123d algebra-mode script ending in show(part, 'part')."""
    lines = _header(plan)
    if plan.escape and not plan.has_tier_a_features:
        lines.append(f"part = {_csg(plan.escape)}")
    else:
        lines.extend(_base_lines(plan))
        for item in plan.additive:
            if isinstance(item, StandoffPlan):
                lines.extend(_standoff_lines(item, plan.base))
            else:
                lines.append(f"part += {_prim(item)}")
        lines.extend(f"part -= {_prim(cut)}" for cut in plan.shell)
        for hole in plan.holes:
            lines.extend(_hole_lines(hole, plan.base))
        lines.extend(f"part -= {_prim(pocket)}" for pocket in plan.pockets)
        if plan.escape:
            lines.append(f"part += {_csg(plan.escape)}")
    lines.append("show(part, 'part')")
    return "\n".join(lines) + "\n"


def emit_build123d(geometry: dict[str, Any]) -> str:
    """Validate + resolve the IR and emit a build123d script. Deterministic."""
    return render_build123d(plan_part(geometry))
