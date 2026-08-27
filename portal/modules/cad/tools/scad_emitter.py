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
z in [0,height]; a cylinder is centered on the Z axis, z in [0,height].
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any

FN_DEFAULT = 48
EPSILON = 0.5  # mm — coincident-face overshoot so subtract/union never leaves a knife-edge


class EmitError(Exception):
    """A structured, model-actionable emitter error. Never a raw traceback."""

    def __init__(self, message: str, category: str = "validation") -> None:
        self.category = category
        super().__init__(message)


# ── restricted arithmetic evaluator (no eval()) ─────────────────────────────

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_ast(node: ast.AST, names: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body, names)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        raise EmitError(f"non-numeric constant in expression: {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise EmitError(
                f"undefined parameter reference: {node.id!r}", category="undefined_variable"
            )
        return names[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval_ast(node.left, names), _eval_ast(node.right, names))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
        return _UNARYOPS[type(node.op)](_eval_ast(node.operand, names))
    raise EmitError(f"disallowed expression node: {type(node).__name__}")


def eval_expr(expr: str, names: dict[str, float]) -> float:
    """Evaluate a restricted arithmetic expression over `names` only. No eval()."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise EmitError(f"invalid expression syntax: {expr!r} ({e})") from e
    return _eval_ast(tree, names)


def resolve_parameters(parameters: dict[str, Any] | None) -> dict[str, float]:
    """Resolve name -> number|expression into name -> float.

    Parameters may reference each other in any order (forward references are
    fine); a genuine cycle or undefined reference is a structured EmitError.
    """
    raw = dict(parameters or {})
    resolved: dict[str, float] = {}
    pending = dict(raw)
    for _ in range(len(raw) + 1):
        if not pending:
            break
        progressed = False
        for name, value in list(pending.items()):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                resolved[name] = float(value)
                del pending[name]
                progressed = True
                continue
            try:
                resolved[name] = eval_expr(str(value), resolved)
                del pending[name]
                progressed = True
            except EmitError:
                continue
        if not progressed:
            break
    if pending:
        raise EmitError(
            f"could not resolve parameter(s) — undefined reference or a cycle: {sorted(pending)}",
            category="undefined_variable",
        )
    return resolved


def resolve_value(value: Any, params: dict[str, float]) -> float:
    """Resolve a single dimension/offset: a literal number or expression string."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if value is None:
        raise EmitError("missing required numeric value")
    return eval_expr(str(value), params)


# ── validation ───────────────────────────────────────────────────────────────

_BOX_DIMS = {"width", "depth", "height"}
_CYL_DIMS = {"radius", "height"}
_FACES = {"top", "bottom", "front", "back", "left", "right"}


def validate_geometry(geometry: dict) -> list[str]:
    """Structural presence checks. Returns a list of error strings (empty = OK)."""
    errors: list[str] = []
    if not isinstance(geometry, dict):
        return ["geometry must be a JSON object"]
    base = geometry.get("base")
    if not isinstance(base, dict):
        errors.append("missing required 'base'")
    else:
        btype = base.get("type")
        dims = base.get("dimensions") or {}
        if btype == "box":
            missing = _BOX_DIMS - set(dims)
            if missing:
                errors.append(f"base box missing dimensions: {sorted(missing)}")
        elif btype == "cylinder":
            missing = _CYL_DIMS - set(dims)
            if missing:
                errors.append(f"base cylinder missing dimensions: {sorted(missing)}")
        else:
            errors.append(f"base.type must be 'box' or 'cylinder', got {btype!r}")

    for kind, required in (
        ("holes", {"diameter", "face", "offset_from", "offset_x", "offset_y"}),
        (
            "pockets",
            {"width", "depth_dim", "cut_depth", "face", "offset_from", "offset_x", "offset_y"},
        ),
        ("standoffs", {"outer_diameter", "height", "face", "offset_from", "offset_x", "offset_y"}),
        ("ribs", {"thickness", "height", "face", "offset_from", "offset_x", "offset_y"}),
    ):
        for i, item in enumerate(geometry.get(kind) or []):
            missing = required - set(item)
            if missing:
                errors.append(f"{kind}[{i}] missing fields: {sorted(missing)}")
            face = item.get("face")
            if face is not None and face not in _FACES:
                errors.append(f"{kind}[{i}].face invalid: {face!r}")

    return errors


# ── face frame — the coordinate-math core ───────────────────────────────────


def _face_uv_dims(face: str, width: float, depth: float, height: float) -> tuple[float, float]:
    if face in ("top", "bottom"):
        return width, depth
    if face in ("front", "back"):
        return width, height
    return depth, height  # left, right


def _face_frame(face: str, width: float, depth: float, height: float) -> dict:
    """corner: global xyz of this face's (u=0, v=0) point.
    u_vec/v_vec: unit vectors (in global xyz) for the face's local u/v axes.
    inward_rotate/outward_rotate: OpenSCAD rotate([...]) that points a +Z-axis
    cylinder into the part / out of the part from this face.
    inward_normal: unit vector pointing from the face into the part interior.
    """
    frames = {
        "top": {
            "corner": (0, 0, height),
            "u_vec": (1, 0, 0),
            "v_vec": (0, 1, 0),
            "inward_rotate": (180, 0, 0),
            "outward_rotate": (0, 0, 0),
            "inward_normal": (0, 0, -1),
        },
        "bottom": {
            "corner": (0, 0, 0),
            "u_vec": (1, 0, 0),
            "v_vec": (0, 1, 0),
            "inward_rotate": (0, 0, 0),
            "outward_rotate": (180, 0, 0),
            "inward_normal": (0, 0, 1),
        },
        "front": {
            "corner": (0, 0, 0),
            "u_vec": (1, 0, 0),
            "v_vec": (0, 0, 1),
            "inward_rotate": (-90, 0, 0),
            "outward_rotate": (90, 0, 0),
            "inward_normal": (0, 1, 0),
        },
        "back": {
            "corner": (0, depth, 0),
            "u_vec": (1, 0, 0),
            "v_vec": (0, 0, 1),
            "inward_rotate": (90, 0, 0),
            "outward_rotate": (-90, 0, 0),
            "inward_normal": (0, -1, 0),
        },
        "left": {
            "corner": (0, 0, 0),
            "u_vec": (0, 1, 0),
            "v_vec": (0, 0, 1),
            "inward_rotate": (0, 90, 0),
            "outward_rotate": (0, -90, 0),
            "inward_normal": (1, 0, 0),
        },
        "right": {
            "corner": (width, 0, 0),
            "u_vec": (0, 1, 0),
            "v_vec": (0, 0, 1),
            "inward_rotate": (0, -90, 0),
            "outward_rotate": (0, 90, 0),
            "inward_normal": (-1, 0, 0),
        },
    }
    if face not in frames:
        raise EmitError(f"unknown face: {face!r}")
    return frames[face]


def _anchor_uv(
    offset_from: str, offset_x: float, offset_y: float, u_dim: float, v_dim: float
) -> tuple[float, float]:
    if offset_from == "center":
        return u_dim / 2 + offset_x, v_dim / 2 + offset_y
    return offset_x, offset_y  # corner / edge: measured from the (0,0) face corner


def _face_point(frame: dict, u: float, v: float) -> tuple[float, float, float]:
    cx, cy, cz = frame["corner"]
    ux, uy, uz = frame["u_vec"]
    vx, vy, vz = frame["v_vec"]
    return (cx + ux * u + vx * v, cy + uy * u + vy * v, cz + uz * u + vz * v)


def _fmt(n: float) -> str:
    if abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    return f"{n:.4f}".rstrip("0").rstrip(".")


def _vec(v: tuple[float, float, float]) -> str:
    return f"[{_fmt(v[0])}, {_fmt(v[1])}, {_fmt(v[2])}]"


# ── pattern expansion ────────────────────────────────────────────────────────


def _expand_pattern(
    geometry: dict, params: dict, width: float, depth: float, height: float
) -> dict:
    pattern = geometry.get("pattern")
    if not pattern:
        return geometry
    kind = pattern["feature_kind"]
    idx = pattern["feature_index"]
    count = int(pattern["count"])
    items = list(geometry.get(kind) or [])
    if idx >= len(items):
        raise EmitError(f"pattern.feature_index {idx} out of range for {kind}")
    template = items[idx]
    face = template["face"]
    u_dim, v_dim = _face_uv_dims(face, width, depth, height)
    offset_from = template.get("offset_from", "corner")
    ox = resolve_value(template["offset_x"], params)
    oy = resolve_value(template["offset_y"], params)
    u0, v0 = _anchor_uv(offset_from, ox, oy, u_dim, v_dim)

    new_items: list[dict] = []
    if pattern["type"] == "linear":
        spacing = resolve_value(pattern.get("spacing", 0), params)
        for i in range(count):
            item = dict(template)
            item["offset_from"] = "corner"
            item["offset_x"] = u0 + i * spacing
            item["offset_y"] = v0
            new_items.append(item)
    else:  # circular
        cu, cv = u_dim / 2, v_dim / 2
        du, dv = u0 - cu, v0 - cv
        radius = math.hypot(du, dv)
        angle0 = math.atan2(dv, du)
        total_angle = math.radians(resolve_value(pattern.get("angle", 360), params))
        step = total_angle / count
        for i in range(count):
            a = angle0 + i * step
            item = dict(template)
            item["offset_from"] = "corner"
            item["offset_x"] = cu + radius * math.cos(a)
            item["offset_y"] = cv + radius * math.sin(a)
            new_items.append(item)

    out = dict(geometry)
    remaining = [it for i, it in enumerate(items) if i != idx]
    out[kind] = remaining + new_items
    return out


# ── feature emitters ─────────────────────────────────────────────────────────


def _emit_hole(item: dict, params: dict, width: float, depth: float, height: float) -> str:
    face = item["face"]
    frame = _face_frame(face, width, depth, height)
    u_dim, v_dim = _face_uv_dims(face, width, depth, height)
    u, v = _anchor_uv(
        item.get("offset_from", "corner"),
        resolve_value(item["offset_x"], params),
        resolve_value(item["offset_y"], params),
        u_dim,
        v_dim,
    )
    diameter = resolve_value(item["diameter"], params)
    axis_extent = {
        "top": height,
        "bottom": height,
        "front": depth,
        "back": depth,
        "left": width,
        "right": width,
    }[face]
    depth_val = (
        resolve_value(item["depth"], params) if item.get("depth") is not None else axis_extent
    )
    px, py, pz = _face_point(frame, u, v)
    nx, ny, nz = frame["inward_normal"]
    start = (px - nx * EPSILON, py - ny * EPSILON, pz - nz * EPSILON)
    length = depth_val + 2 * EPSILON
    r = _fmt(diameter / 2)
    return (
        f"translate({_vec(start)}) rotate({_vec(frame['inward_rotate'])}) "
        f"cylinder(h={_fmt(length)}, r={r}, $fn=$fn);"
    )


def _emit_standoff(item: dict, params: dict, width: float, depth: float, height: float) -> str:
    face = item["face"]
    frame = _face_frame(face, width, depth, height)
    u_dim, v_dim = _face_uv_dims(face, width, depth, height)
    u, v = _anchor_uv(
        item.get("offset_from", "corner"),
        resolve_value(item["offset_x"], params),
        resolve_value(item["offset_y"], params),
        u_dim,
        v_dim,
    )
    outer_d = resolve_value(item["outer_diameter"], params)
    h = resolve_value(item["height"], params)
    px, py, pz = _face_point(frame, u, v)
    nx, ny, nz = frame["inward_normal"]
    start = (px + nx * EPSILON, py + ny * EPSILON, pz + nz * EPSILON)
    length = h + EPSILON
    boss = (
        f"translate({_vec(start)}) rotate({_vec(frame['outward_rotate'])}) "
        f"cylinder(h={_fmt(length)}, r={_fmt(outer_d / 2)}, $fn=$fn)"
    )
    if item.get("inner_diameter"):
        inner_d = resolve_value(item["inner_diameter"], params)
        bore = (
            f"translate({_vec(start)}) rotate({_vec(frame['outward_rotate'])}) "
            f"cylinder(h={_fmt(length + EPSILON)}, r={_fmt(inner_d / 2)}, $fn=$fn)"
        )
        return f"difference() {{ {boss}; {bore}; }}"
    return f"{boss};"


def _emit_pocket(item: dict, params: dict, width: float, depth: float, height: float) -> str:
    face = item["face"]
    u_dim, v_dim = _face_uv_dims(face, width, depth, height)
    w = resolve_value(item["width"], params)
    d = resolve_value(item["depth_dim"], params)
    cut = resolve_value(item["cut_depth"], params)
    u0, v0 = _anchor_uv(
        item.get("offset_from", "corner"),
        resolve_value(item["offset_x"], params),
        resolve_value(item["offset_y"], params),
        u_dim,
        v_dim,
    )
    if item.get("offset_from") == "center":
        u0, v0 = u0 - w / 2, v0 - d / 2

    if face == "top":
        origin, size = (u0, v0, height - cut - EPSILON), (w, d, cut + 2 * EPSILON)
    elif face == "bottom":
        origin, size = (u0, v0, -EPSILON), (w, d, cut + 2 * EPSILON)
    elif face == "front":
        origin, size = (u0, -EPSILON, v0), (w, cut + 2 * EPSILON, d)
    elif face == "back":
        origin, size = (u0, depth - cut - EPSILON, v0), (w, cut + 2 * EPSILON, d)
    elif face == "left":
        origin, size = (-EPSILON, u0, v0), (cut + 2 * EPSILON, w, d)
    else:  # right
        origin, size = (width - cut - EPSILON, u0, v0), (cut + 2 * EPSILON, w, d)
    return f"translate({_vec(origin)}) cube({_vec(size)});"


def _emit_rib(item: dict, params: dict, width: float, depth: float, height: float) -> str:
    """Simplified: a full-span reinforcement wall of `thickness` protruding
    `height` outward from the face, centered on the anchor's u position."""
    face = item["face"]
    u_dim, v_dim = _face_uv_dims(face, width, depth, height)
    thickness = resolve_value(item["thickness"], params)
    h = resolve_value(item["height"], params)
    u0, _v0 = _anchor_uv(
        item.get("offset_from", "corner"),
        resolve_value(item["offset_x"], params),
        resolve_value(item["offset_y"], params),
        u_dim,
        v_dim,
    )
    u0 -= thickness / 2

    if face == "top":
        origin, size = (u0, 0, height - EPSILON), (thickness, v_dim, h + EPSILON)
    elif face == "bottom":
        origin, size = (u0, 0, -h + EPSILON), (thickness, v_dim, h + EPSILON)
    elif face == "front":
        origin, size = (u0, -h + EPSILON, 0), (thickness, h + EPSILON, v_dim)
    elif face == "back":
        origin, size = (u0, depth - EPSILON, 0), (thickness, h + EPSILON, v_dim)
    elif face == "left":
        origin, size = (-h + EPSILON, u0, 0), (h + EPSILON, thickness, v_dim)
    else:  # right
        origin, size = (width - EPSILON, u0, 0), (h + EPSILON, thickness, v_dim)
    return f"translate({_vec(origin)}) cube({_vec(size)});"


def _emit_base(geometry: dict, params: dict) -> tuple[str, float, float, float]:
    base = geometry["base"]
    dims = base["dimensions"]
    if base["type"] == "box":
        width = resolve_value(dims["width"], params)
        depth = resolve_value(dims["depth"], params)
        height = resolve_value(dims["height"], params)
        solid = f"cube({_vec((width, depth, height))});"
    else:  # cylinder
        radius = resolve_value(dims["radius"], params)
        height = resolve_value(dims["height"], params)
        width = depth = radius * 2
        solid = f"cylinder(h={_fmt(height)}, r={_fmt(radius)}, $fn=$fn);"

    for fillet in geometry.get("fillets") or []:
        r = resolve_value(fillet["radius"], params)
        # Approximation: round all edges via minkowski (shrink then grow by r).
        solid = (
            f"translate({_vec((r, r, r))}) minkowski() {{ "
            f"cube({_vec((max(width - 2 * r, 0.01), max(depth - 2 * r, 0.01), max(height - 2 * r, 0.01)))}); "
            f"sphere(r={_fmt(r)}, $fn=24); }}"
        )
    for chamfer in geometry.get("chamfers") or []:
        s = resolve_value(chamfer["size"], params)
        # Approximation: soften all edges via minkowski with a small cube.
        solid = (
            f"translate({_vec((s, s, s))}) minkowski() {{ "
            f"cube({_vec((max(width - 2 * s, 0.01), max(depth - 2 * s, 0.01), max(height - 2 * s, 0.01)))}); "
            f"cube({_vec((s, s, s))}, center=true); }}"
        )
    return solid, width, depth, height


def _shell_cavity(
    open_face: str, wall: float, width: float, depth: float, height: float
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Inner cavity for `shell`: inset by `wall` on every side except
    `open_face`, which is cut through (with a small overshoot past that face
    — harmless for a subtractive boolean, guarantees a clean opening)."""
    origin = [wall, wall, wall]
    size = [width - 2 * wall, depth - 2 * wall, height - 2 * wall]
    axis_for_face = {"left": 0, "right": 0, "front": 1, "back": 1, "bottom": 2, "top": 2}
    full_extent = {
        "left": width,
        "right": width,
        "front": depth,
        "back": depth,
        "bottom": height,
        "top": height,
    }
    if open_face in axis_for_face:
        axis = axis_for_face[open_face]
        size[axis] = full_extent[open_face]
        if open_face in ("left", "front", "bottom"):
            origin[axis] = -EPSILON
    return (origin[0], origin[1], origin[2]), (size[0], size[1], size[2])


def _collect_additive(
    geometry: dict, params: dict, base_solid: str, w: float, d: float, h: float
) -> list[str]:
    additive = [base_solid]
    for standoff in geometry.get("standoffs") or []:
        additive.append(_emit_standoff(standoff, params, w, d, h))
    for rib in geometry.get("ribs") or []:
        additive.append(_emit_rib(rib, params, w, d, h))
    return additive


def _collect_subtractive(geometry: dict, params: dict, w: float, d: float, h: float) -> list[str]:
    subtractive: list[str] = []
    shell = geometry.get("shell")
    if shell:
        wall = resolve_value(shell["wall_thickness"], params)
        open_face = shell.get("open_face", "top")
        inner_origin, inner_size = _shell_cavity(open_face, wall, w, d, h)
        subtractive.append(f"translate({_vec(inner_origin)}) cube({_vec(inner_size)});")
    for hole in geometry.get("holes") or []:
        subtractive.append(_emit_hole(hole, params, w, d, h))
    for pocket in geometry.get("pockets") or []:
        subtractive.append(_emit_pocket(pocket, params, w, d, h))
    return subtractive


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


def emit_scad(geometry: dict, fn: int = FN_DEFAULT) -> str:
    """Validate + resolve + build parametric OpenSCAD source. Deterministic:
    the same geometry JSON + fn always produces the same SCAD string.

    `fn` overrides $fn (tessellation) — used by generate_scad's auto-repair
    loop (P4.2) to cheapen a timing-out render or smooth a degenerate mesh,
    without touching the model's design intent.
    """
    errors = validate_geometry(geometry)
    if errors:
        raise EmitError("; ".join(errors))

    params = resolve_parameters(geometry.get("parameters"))
    base_solid, width, depth, height = _emit_base(geometry, params)
    geometry = _expand_pattern(geometry, params, width, depth, height)

    additive = _collect_additive(geometry, params, base_solid, width, depth, height)
    subtractive = _collect_subtractive(geometry, params, width, depth, height)

    escape = geometry.get("escape_hatch")
    escape_stmt = (
        _emit_csg_node(escape["csg"], params) + ";" if escape and escape.get("csg") else None
    )
    has_tier_a_features = bool(
        geometry.get("holes")
        or geometry.get("pockets")
        or geometry.get("standoffs")
        or geometry.get("ribs")
        or geometry.get("shell")
    )
    body_parts = _compose_body(additive, subtractive, escape_stmt, has_tier_a_features)

    lines = [
        "// units=mm — generated by scad_emitter.py (TASK_CAD_MODULE_OVERHAUL_V1 Phase 2)",
        f"$fn = {fn};",
        "",
    ]
    for name, value in resolve_parameters(geometry.get("parameters")).items():
        lines.append(f"{name} = {_fmt(value)};")
    if geometry.get("parameters"):
        lines.append("")
    lines.extend(body_parts)
    return "\n".join(lines) + "\n"


# ── Tier-B escape-hatch CSG ──────────────────────────────────────────────────

_PRIMITIVES = {"box", "cylinder", "sphere"}
_TRANSFORMS = {"translate", "rotate", "scale"}
_BOOLEANS = {"union", "difference", "intersection"}
_EXTRUDES = {"linear_extrude", "rotate_extrude"}


def _emit_csg_node(node: dict, params: dict) -> str:
    op = node.get("op")
    if op == "box":
        dims = node["dimensions"]
        w = resolve_value(dims["width"], params)
        d = resolve_value(dims["depth"], params)
        h = resolve_value(dims["height"], params)
        return f"cube({_vec((w, d, h))})"
    if op == "cylinder":
        dims = node["dimensions"]
        r = resolve_value(dims["radius"], params)
        h = resolve_value(dims["height"], params)
        return f"cylinder(h={_fmt(h)}, r={_fmt(r)}, $fn=$fn)"
    if op == "sphere":
        r = resolve_value(node["dimensions"]["radius"], params)
        return f"sphere(r={_fmt(r)}, $fn=$fn)"
    if op in _TRANSFORMS:
        child = node.get("child")
        if child is None:
            raise EmitError(f"'{op}' requires a 'child' node")
        vec = tuple(resolve_value(v, params) for v in node.get("vector", [0, 0, 0]))
        inner = _emit_csg_node(child, params)
        if op == "scale":
            return f"scale({_vec(vec)}) {inner}"
        if op == "rotate":
            return f"rotate({_vec(vec)}) {inner}"
        return f"translate({_vec(vec)}) {inner}"
    if op in _BOOLEANS:
        children = node.get("children") or []
        if not children:
            raise EmitError(f"'{op}' requires at least one child")
        inner = " ".join(f"{_emit_csg_node(c, params)};" for c in children)
        return f"{op}() {{ {inner} }}"
    if op in _EXTRUDES:
        child = node.get("child")
        if child is None:
            raise EmitError(f"'{op}' requires a 'child' node")
        amount = resolve_value(node.get("amount", 0), params)
        arg = f"height={_fmt(amount)}" if op == "linear_extrude" else f"angle={_fmt(amount)}"
        return f"{op}({arg}) {_emit_csg_node(child, params)}"
    raise EmitError(f"unsupported Tier-B op: {op!r}")
