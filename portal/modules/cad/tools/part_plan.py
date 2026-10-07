"""Kernel-neutral part plan for the CAD geometry IR (TASK_CAD_ARM_REDEVELOP_V1 P3).

`plan_part(geometry)` validates the IR, resolves parameters, and does ALL the
coordinate-frame math once, returning a `PartPlan` of plain numbers. Two backends
render it: `scad_emitter.render_scad` (OpenSCAD source) and
`b123d_emitter.render_build123d` (build123d BREP script). Neither backend does
spatial reasoning of its own.

Coordinate convention: Z-up, right-handed. The base solid's local frame has its
"min" corner at the origin: a box spans x in [0,width], y in [0,depth],
z in [0,height]; a cylinder's XY footprint also starts at (0,0), with its axis at
(radius,radius), and z in [0,height].
"""

from __future__ import annotations

import ast
import difflib
import json
import math
import operator
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict, cast

from jsonschema import Draft7Validator  # type: ignore[import-untyped]  # no py.typed marker

_PARAM_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
EPSILON = 0.5  # mm — coincident-face overshoot so subtract/union never leaves a knife-edge


class EmitError(Exception):
    """A structured, model-actionable emitter error. Never a raw traceback."""

    def __init__(self, message: str, category: str = "validation") -> None:
        self.category = category
        super().__init__(message)


class _FaceFrame(TypedDict):
    """Global-xyz frame of one box face: origin corner, u/v unit axes, the
    OpenSCAD rotations that point a +Z cylinder into/out of the part, and the
    inward unit normal."""

    corner: tuple[float, float, float]
    u_vec: tuple[float, float, float]
    v_vec: tuple[float, float, float]
    inward_rotate: tuple[float, float, float]
    outward_rotate: tuple[float, float, float]
    inward_normal: tuple[float, float, float]


# ── restricted arithmetic evaluator (no eval()) ─────────────────────────────

_BINOPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARYOPS: dict[type[ast.unaryop], Any] = {ast.UAdd: operator.pos, ast.USub: operator.neg}


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
        value = _BINOPS[type(node.op)](_eval_ast(node.left, names), _eval_ast(node.right, names))
        return cast("float", value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
        value = _UNARYOPS[type(node.op)](_eval_ast(node.operand, names))
        return cast("float", value)
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
    for name in raw:
        if not _PARAM_NAME.fullmatch(str(name)):
            raise EmitError(
                f"parameter name {str(name)[:40]!r} is not a valid identifier "
                "(letters, digits, underscore; must not start with a digit)"
            )
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

SCHEMA_PATH = Path(__file__).resolve().parents[4] / "config/inference/cad_geometry_schema.json"


@lru_cache(maxsize=1)
def geometry_schema() -> dict[str, Any]:
    schema = cast("dict[str, Any]", json.loads(SCHEMA_PATH.read_text()))
    Draft7Validator.check_schema(schema)
    return schema


def _path(parts: list[Any], leaf: str | None = None) -> str:
    out = ""
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else ("." if out else "") + str(part)
    return f"{out}.{leaf}" if leaf and out else leaf or out or "geometry"


def _format_schema_error(error: Any) -> str:
    path = list(error.absolute_path)
    if error.validator == "additionalProperties":
        valid = sorted((error.schema.get("properties") or {}).keys())
        extras = (
            sorted(set(error.instance) - set(valid)) if isinstance(error.instance, dict) else []
        )
        bad = extras[0] if extras else "unknown key"
        location = _path(path, bad)
        hint = difflib.get_close_matches(bad, valid, n=1, cutoff=0.65)
        suggestion = f" Did you mean '{hint[0]}'?" if hint else ""
        if bad == "pattern" and path and path[0] == "holes":
            suggestion = (
                " 'pattern' is a top-level key referencing a feature with "
                "feature_kind + feature_index; for example "
                '{"pattern":{"type":"linear","feature_kind":"holes",'
                '"feature_index":0,"count":3,"spacing":25}}.'
            )
        return f"{location} is not valid here; valid keys: {valid}.{suggestion}".strip()
    location = _path(path)
    if error.validator == "enum":
        return f"{location}: {error.instance!r} is invalid; valid values: {error.validator_value}"
    if error.validator == "required":
        return (
            f"{location}: {error.message}; valid keys: {sorted(error.schema.get('properties', {}))}"
        )
    return f"{location}: {error.message}"


def validate_geometry(geometry: dict[str, Any]) -> list[str]:
    """Validate against the canonical JSON Schema and return actionable errors."""
    public_geometry = (
        {k: v for k, v in geometry.items() if not k.startswith("_")}
        if isinstance(geometry, dict)
        else geometry
    )
    errors = sorted(
        Draft7Validator(geometry_schema()).iter_errors(public_geometry),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    return [_format_schema_error(error) for error in errors]


# ── face frame — the coordinate-math core ───────────────────────────────────


def _face_uv_dims(face: str, width: float, depth: float, height: float) -> tuple[float, float]:
    if face in ("top", "bottom"):
        return width, depth
    if face in ("front", "back"):
        return width, height
    return depth, height  # left, right


def _face_frame(face: str, width: float, depth: float, height: float) -> _FaceFrame:
    """corner: global xyz of this face's (u=0, v=0) point.
    u_vec/v_vec: unit vectors (in global xyz) for the face's local u/v axes.
    inward_rotate/outward_rotate: OpenSCAD rotate([...]) that points a +Z-axis
    cylinder into the part / out of the part from this face.
    inward_normal: unit vector pointing from the face into the part interior.
    """
    frames: dict[str, _FaceFrame] = {
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


def _face_point(frame: _FaceFrame, u: float, v: float) -> tuple[float, float, float]:
    cx, cy, cz = frame["corner"]
    ux, uy, uz = frame["u_vec"]
    vx, vy, vz = frame["v_vec"]
    return (cx + ux * u + vx * v, cy + uy * u + vy * v, cz + uz * u + vz * v)


# ── pattern expansion ────────────────────────────────────────────────────────


def _expand_pattern(
    geometry: dict[str, Any],
    params: dict[str, float],
    width: float,
    depth: float,
    height: float,
) -> dict[str, Any]:
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

    new_items: list[dict[str, Any]] = []
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


# ── the plan ─────────────────────────────────────────────────────────────────

Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class BasePlan:
    kind: str  # "box" | "cylinder" | "prism" | "revolve" | "angle"
    width: float
    depth: float
    height: float  # for a cylinder width == depth == 2 * radius
    thickness: float = 0.0  # angle: leg thickness
    inner_radius: float = 0.0  # angle: inside-corner fillet
    # prism: footprint polygon, shifted so its bounding box starts at the origin.
    # revolve: (radius, z) profile, z shifted to start at 0.
    # angle: the (y, z) L outline, inner-corner arc included.
    points: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class EdgeTreatment:
    kind: str  # "fillet" | "chamfer"
    edges: str  # "all" | "top" | "bottom"
    size: float


@dataclass(frozen=True)
class PrimBox:
    """Axis-aligned box with its min corner at `origin` (already includes any
    EPSILON overshoot — it is a cutter/joiner, not a nominal dimension)."""

    origin: Vec3
    size: Vec3


@dataclass(frozen=True)
class PrimCylinder:
    """+Z-axis cylinder whose bottom-centre is `origin` (EPSILON already applied)."""

    origin: Vec3
    height: float
    radius: float


@dataclass(frozen=True)
class HolePlan:
    face: str
    point: Vec3  # world position on the face where the hole axis enters
    diameter: float
    depth: float  # defaults to the full extent along the hole axis
    chamfer: float | None
    counterbore: tuple[float, float] | None  # (diameter, depth)
    countersink: tuple[float, float] | None  # (diameter, depth along axis)


@dataclass(frozen=True)
class StandoffPlan:
    face: str
    point: Vec3
    outer_diameter: float
    inner_diameter: float | None
    height: float


@dataclass(frozen=True)
class CsgPlan:
    """A resolved Tier-B escape-hatch CSG node (all numbers, no expressions)."""

    op: str
    dims: tuple[float, ...] = ()  # box: (w,d,h) · cylinder: (r,h) · sphere: (r,)
    vector: Vec3 = (0.0, 0.0, 0.0)
    amount: float = 0.0
    child: CsgPlan | None = None
    children: tuple[CsgPlan, ...] = ()


@dataclass(frozen=True)
class PartPlan:
    units: str
    part_name: str
    declared_parameters: bool
    parameters: dict[str, float]
    base: BasePlan
    edge_treatments: tuple[EdgeTreatment, ...]  # fillets first, then chamfers
    additive: tuple[StandoffPlan | PrimBox, ...]  # standoffs, then ribs
    shell: tuple[PrimBox | PrimCylinder, ...]  # cavity cutters (empty = no shell)
    holes: tuple[HolePlan, ...]
    pockets: tuple[PrimBox, ...]
    escape: CsgPlan | None
    has_tier_a_features: bool


_ARC_SEGMENTS = 8  # inside-corner arc of an `angle` base, in SCAD (BREP uses a true fillet)


def _plan_prism(dims: dict[str, Any], params: dict[str, float]) -> BasePlan:
    sides = int(dims["sides"])
    height = resolve_value(dims["height"], params)
    has_flats, has_circ = dims.get("across_flats") is not None, dims.get("circumradius") is not None
    if has_flats == has_circ:
        raise EmitError(
            "prism needs exactly one of dimensions.across_flats or dimensions.circumradius",
            category="intent_error",
        )
    if has_flats:
        circ = resolve_value(dims["across_flats"], params) / (2 * math.cos(math.pi / sides))
    else:
        circ = resolve_value(dims["circumradius"], params)
    if circ <= 0 or height <= 0:
        raise EmitError("prism size must be positive", category="intent_error")
    raw = [
        (circ * math.cos(2 * math.pi * k / sides), circ * math.sin(2 * math.pi * k / sides))
        for k in range(sides)
    ]
    min_x, min_y = min(x for x, _ in raw), min(y for _, y in raw)
    pts = tuple((x - min_x, y - min_y) for x, y in raw)
    return BasePlan(
        "prism",
        max(x for x, _ in pts),
        max(y for _, y in pts),
        height,
        points=pts,
    )


def _plan_revolve(dims: dict[str, Any], params: dict[str, float]) -> BasePlan:
    raw = [(resolve_value(r, params), resolve_value(z, params)) for r, z in dims["profile"]]
    if any(r < 0 for r, _ in raw):
        raise EmitError("revolve profile radii must be >= 0", category="intent_error")
    max_r = max(r for r, _ in raw)
    if max_r <= 0:
        raise EmitError("revolve profile needs a radius > 0", category="intent_error")
    min_z = min(z for _, z in raw)
    pts = tuple((r, z - min_z) for r, z in raw)
    return BasePlan("revolve", max_r * 2, max_r * 2, max(z for _, z in pts), points=pts)


def _plan_angle(dims: dict[str, Any], params: dict[str, float]) -> BasePlan:
    width = resolve_value(dims["width"], params)
    depth = resolve_value(dims["depth"], params)
    height = resolve_value(dims["height"], params)
    t = resolve_value(dims["thickness"], params)
    r = resolve_value(dims["inner_radius"], params) if dims.get("inner_radius") else 0.0
    if t <= 0 or t >= min(depth, height) or r < 0 or r > min(depth, height) - t:
        raise EmitError(
            f"angle thickness {t:g} / inner_radius {r:g} do not fit legs {depth:g} x {height:g}",
            category="intent_error",
        )
    pts: list[tuple[float, float]] = [(0.0, 0.0), (depth, 0.0), (depth, t)]
    if r > 0:
        cy = cz = t + r
        for k in range(_ARC_SEGMENTS + 1):
            a = math.radians(-90.0 - 90.0 * k / _ARC_SEGMENTS)
            pts.append((cy + r * math.cos(a), cz + r * math.sin(a)))
    else:
        pts.append((t, t))
    pts += [(t, height), (0.0, height)]
    return BasePlan("angle", width, depth, height, thickness=t, inner_radius=r, points=tuple(pts))


def _plan_base(geometry: dict[str, Any], params: dict[str, float]) -> BasePlan:
    base = geometry.get("base")
    if not isinstance(base, dict):
        raise EmitError("missing 'base' geometry block")
    dims = base["dimensions"]
    kind = base["type"]
    if kind == "box":
        return BasePlan(
            "box",
            resolve_value(dims["width"], params),
            resolve_value(dims["depth"], params),
            resolve_value(dims["height"], params),
        )
    if kind == "prism":
        return _plan_prism(dims, params)
    if kind == "revolve":
        return _plan_revolve(dims, params)
    if kind == "angle":
        return _plan_angle(dims, params)
    radius = resolve_value(dims["radius"], params)
    return BasePlan("cylinder", radius * 2, radius * 2, resolve_value(dims["height"], params))


# Which Tier-A features each non-box base supports (everything else would be
# positioned against a bounding box that is not the real surface).
_PRISM_FACES = {"top", "bottom"}
_ANGLE_FACES = {"bottom", "front"}
_REVOLVE_FACES = {"top", "bottom"}


def _check_base_features(geometry: dict[str, Any], base: BasePlan) -> None:
    if base.kind not in {"prism", "revolve", "angle"}:
        return
    unsupported = [
        key
        for key in ("shell", "pockets", "standoffs", "ribs", "fillets", "chamfers")
        if geometry.get(key)
    ]
    if unsupported:
        raise EmitError(
            f"base type {base.kind!r} does not support {', '.join(unsupported)}; "
            "keep only holes (and patterns of holes) on this base, or build the part with cad_build",
            category="intent_error",
        )
    faces = {"prism": _PRISM_FACES, "angle": _ANGLE_FACES, "revolve": _REVOLVE_FACES}[base.kind]
    for index, hole in enumerate(geometry.get("holes") or []):
        if hole["face"] not in faces:
            raise EmitError(
                f"holes[{index}].face={hole['face']!r} is not a real surface of a {base.kind} base; "
                f"use one of {sorted(faces)}",
                category="intent_error",
            )


def _plan_edge_treatments(
    geometry: dict[str, Any], params: dict[str, float], base: BasePlan
) -> tuple[EdgeTreatment, ...]:
    out: list[EdgeTreatment] = []
    groups = (
        (geometry.get("fillets") or [], "radius", "fillet"),
        (geometry.get("chamfers") or [], "size", "chamfer"),
    )
    for items, size_key, kind in groups:
        for item in items:
            size = resolve_value(item[size_key], params)
            edges = item.get("edges", "all")
            if base.kind == "box" and (
                size <= 0 or size * 2 >= min(base.width, base.depth, base.height)
            ):
                raise EmitError(
                    f"edge treatment {size:g}mm does not fit base "
                    f"{base.width:g}x{base.depth:g}x{base.height:g}mm",
                    category="intent_error",
                )
            out.append(EdgeTreatment(kind, edges, size))
    return tuple(out)


def _plan_standoff(item: dict[str, Any], params: dict[str, float], base: BasePlan) -> StandoffPlan:
    face = item["face"]
    frame = _face_frame(face, base.width, base.depth, base.height)
    u_dim, v_dim = _face_uv_dims(face, base.width, base.depth, base.height)
    u, v = _anchor_uv(
        item.get("offset_from", "corner"),
        resolve_value(item["offset_x"], params),
        resolve_value(item["offset_y"], params),
        u_dim,
        v_dim,
    )
    outer_d = resolve_value(item["outer_diameter"], params)
    h = resolve_value(item["height"], params)
    inner_d = resolve_value(item["inner_diameter"], params) if item.get("inner_diameter") else None
    return StandoffPlan(face, _face_point(frame, u, v), outer_d, inner_d, h)


def _plan_rib(item: dict[str, Any], params: dict[str, float], base: BasePlan) -> PrimBox:
    """Simplified: a full-span reinforcement wall of `thickness` protruding
    `height` outward from the face, centered on the anchor's u position."""
    width, depth, height = base.width, base.depth, base.height
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

    origin: Vec3
    size: Vec3
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
    return PrimBox(origin, size)


def _plan_pocket(item: dict[str, Any], params: dict[str, float], base: BasePlan) -> PrimBox:
    width, depth, height = base.width, base.depth, base.height
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

    origin: Vec3
    size: Vec3
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
    return PrimBox(origin, size)


def _plan_hole(item: dict[str, Any], params: dict[str, float], base: BasePlan) -> HolePlan:
    width, depth, height = base.width, base.depth, base.height
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
    if base.kind == "angle":
        axis_extent = base.thickness  # both legs are `thickness` thick
    depth_val = (
        resolve_value(item["depth"], params) if item.get("depth") is not None else axis_extent
    )
    chamfer = resolve_value(item["chamfer"], params) if item.get("chamfer") is not None else None
    counterbore = None
    if item.get("counterbore"):
        cb = item["counterbore"]
        counterbore = (resolve_value(cb["diameter"], params), resolve_value(cb["depth"], params))
    countersink = None
    if item.get("countersink"):
        cs = item["countersink"]
        cs_diameter = resolve_value(cs["diameter"], params)
        angle = math.radians(resolve_value(cs["angle"], params) / 2)
        if cs_diameter <= diameter or not 0 < angle < math.pi / 2:
            raise EmitError(
                "countersink requires diameter > hole diameter and included angle between 0 and 180 degrees",
                category="intent_error",
            )
        countersink = (cs_diameter, (cs_diameter - diameter) / 2 / math.tan(angle))
    return HolePlan(
        face, _face_point(frame, u, v), diameter, depth_val, chamfer, counterbore, countersink
    )


def _shell_cavity(
    open_face: str, wall: float, width: float, depth: float, height: float
) -> tuple[Vec3, Vec3]:
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


def _plan_shell(
    geometry: dict[str, Any], params: dict[str, float], base: BasePlan
) -> tuple[PrimBox | PrimCylinder, ...]:
    shell = geometry.get("shell")
    if not shell:
        return ()
    w, d, h = base.width, base.depth, base.height
    wall = resolve_value(shell["wall_thickness"], params)
    open_face = shell.get("open_face", "top")
    if base.kind == "cylinder":
        radius = w / 2
        if wall >= min(radius, h / 2):
            raise EmitError(
                "shell.wall_thickness leaves no cylindrical interior", category="intent_error"
            )
        z0 = -EPSILON if open_face == "bottom" else wall
        cavity_h = h - wall if open_face in {"top", "bottom"} else h - 2 * wall
        if open_face == "top":
            cavity_h += EPSILON
        cuts: list[PrimBox | PrimCylinder] = [
            PrimCylinder(
                (radius, radius, z0),
                cavity_h + (EPSILON if open_face == "bottom" else 0),
                radius - wall,
            )
        ]
        side_tunnels = {
            "left": (-EPSILON, wall, wall, radius + EPSILON, d - 2 * wall, h - 2 * wall),
            "right": (radius, wall, wall, radius + EPSILON, d - 2 * wall, h - 2 * wall),
            "front": (wall, -EPSILON, wall, w - 2 * wall, radius + EPSILON, h - 2 * wall),
            "back": (wall, radius, wall, w - 2 * wall, radius + EPSILON, h - 2 * wall),
        }
        if open_face in side_tunnels:
            x, y, z, sx, sy, sz = side_tunnels[open_face]
            cuts.append(PrimBox((x, y, z), (sx, sy, sz)))
        return tuple(cuts)
    inner_origin, inner_size = _shell_cavity(open_face, wall, w, d, h)
    return (PrimBox(inner_origin, inner_size),)


_PRIMITIVES = {"box", "cylinder", "sphere"}
_TRANSFORMS = {"translate", "rotate", "scale"}
_BOOLEANS = {"union", "difference", "intersection"}
_EXTRUDES = {"linear_extrude", "rotate_extrude"}


def _plan_csg(node: dict[str, Any], params: dict[str, float]) -> CsgPlan:
    op = node.get("op")
    if op == "box":
        dims = node["dimensions"]
        return CsgPlan(
            "box",
            dims=(
                resolve_value(dims["width"], params),
                resolve_value(dims["depth"], params),
                resolve_value(dims["height"], params),
            ),
        )
    if op == "cylinder":
        dims = node["dimensions"]
        return CsgPlan(
            "cylinder",
            dims=(resolve_value(dims["radius"], params), resolve_value(dims["height"], params)),
        )
    if op == "sphere":
        return CsgPlan("sphere", dims=(resolve_value(node["dimensions"]["radius"], params),))
    if op in _TRANSFORMS:
        child = node.get("child")
        if child is None:
            raise EmitError(f"'{op}' requires a 'child' node")
        vec = cast("Vec3", tuple(resolve_value(v, params) for v in node.get("vector", [0, 0, 0])))
        return CsgPlan(str(op), vector=vec, child=_plan_csg(child, params))
    if op in _BOOLEANS:
        children = node.get("children") or []
        if not children:
            raise EmitError(f"'{op}' requires at least one child")
        return CsgPlan(str(op), children=tuple(_plan_csg(c, params) for c in children))
    if op in _EXTRUDES:
        child = node.get("child")
        if child is None:
            raise EmitError(f"'{op}' requires a 'child' node")
        amount = resolve_value(node.get("amount", 0), params)
        return CsgPlan(str(op), amount=amount, child=_plan_csg(child, params))
    raise EmitError(f"unsupported Tier-B op: {op!r}")


def plan_part(geometry: dict[str, Any]) -> PartPlan:
    """Validate + resolve the IR into a kernel-neutral `PartPlan`. Deterministic."""
    errors = validate_geometry(geometry)
    if errors:
        raise EmitError("; ".join(errors))

    params = resolve_parameters(geometry.get("parameters"))
    base = _plan_base(geometry, params)
    _check_base_features(geometry, base)
    edge_treatments = _plan_edge_treatments(geometry, params, base)
    geometry = _expand_pattern(geometry, params, base.width, base.depth, base.height)

    for index, hole in enumerate(geometry.get("holes") or []):
        face = hole["face"]
        diameter = resolve_value(hole["diameter"], params)
        u_dim, v_dim = _face_uv_dims(face, base.width, base.depth, base.height)
        if diameter > min(u_dim, v_dim):
            raise EmitError(
                f"holes[{index}].diameter={diameter:g}mm exceeds the {face} face's "
                f"smallest extent {min(u_dim, v_dim):g}mm; correct the design dimensions",
                category="intent_error",
            )

    additive: list[StandoffPlan | PrimBox] = [
        _plan_standoff(s, params, base) for s in geometry.get("standoffs") or []
    ]
    additive += [_plan_rib(r, params, base) for r in geometry.get("ribs") or []]
    shell = _plan_shell(geometry, params, base)
    holes = tuple(_plan_hole(h, params, base) for h in geometry.get("holes") or [])
    pockets = tuple(_plan_pocket(p, params, base) for p in geometry.get("pockets") or [])

    escape_node = geometry.get("escape_hatch")
    escape = (
        _plan_csg(escape_node["csg"], params) if escape_node and escape_node.get("csg") else None
    )
    has_tier_a = bool(
        geometry.get("holes")
        or geometry.get("pockets")
        or geometry.get("standoffs")
        or geometry.get("ribs")
        or geometry.get("shell")
    )
    return PartPlan(
        units=geometry.get("units", "mm"),
        part_name=str((geometry.get("metadata") or {}).get("part_name", "unnamed")),
        declared_parameters=bool(geometry.get("parameters")),
        parameters=params,
        base=base,
        edge_treatments=edge_treatments,
        additive=tuple(additive),
        shell=shell,
        holes=holes,
        pockets=pockets,
        escape=escape,
        has_tier_a_features=has_tier_a,
    )
