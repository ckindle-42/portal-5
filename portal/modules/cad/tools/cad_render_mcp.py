"""
CAD Render MCP Server
Headless rendering + format conversion for the code-CAD lane (TASK_CAD_RENDER_MCP_V1).

Exposes: render_mesh, render_openscad, convert_cad

Backend design (see task file §0): mesh-level rendering via trimesh + an offscreen
rasterizer (pyrender/OSMesa/EGL) with a pure-CPU matplotlib fallback, so a PNG is
always produced even when no GL context initializes in the container. OpenSCAD source
is rendered via the openscad binary in headless --render mode. STEP read is best-effort
(build123d/OCP if importable). This server deliberately avoids OCP+VTK offscreen.

Artifacts are written to the shared workspace generated/models3d directory.
Start with: python -m portal.modules.cad.tools.cad_render_mcp
"""

import base64
import logging
import os
import re
import subprocess  # noqa: S404 — openscad invocation is argument-controlled, no shell
import uuid
from pathlib import Path

from mcp.server import MCPServer
from starlette.responses import FileResponse, JSONResponse

from portal.modules.cad.tools.capabilities import cad_capabilities
from portal.modules.cad.tools.mesh_validator import validate_mesh
from portal.modules.cad.tools.scad_emitter import FN_DEFAULT, EmitError, emit_scad
from portal.platform.data_loader import load_data
from portal.platform.mcp_host.workspace import get_generated_dir

logger = logging.getLogger(__name__)

port = int(os.getenv("CAD_RENDER_MCP_PORT", "8926"))
mcp = MCPServer("cad-render")

PUBLIC_URL = os.getenv("CAD_RENDER_PUBLIC_URL", f"http://localhost:{port}/files/models3d").rstrip(
    "/"
)
SAFE_FILENAME = re.compile(r"^[\w\-\.\s]+$")

# Master switch for the vision review loop. Default OFF (see B6). Per-call `review`
# must ALSO be true for the loop to fire.
REVIEW_LOOP_ENABLED = os.getenv("CAD_RENDER_REVIEW_LOOP", "0") == "1"
REVIEW_MODEL = os.getenv("CAD_RENDER_REVIEW_MODEL", "qwen3-vl:32b")
PIPELINE_URL = os.getenv("PORTAL_PIPELINE_URL", "http://localhost:9099")

MESH_EXTS = {".stl", ".3mf", ".obj", ".ply", ".off", ".glb"}


def _out_dir() -> Path:
    return get_generated_dir("models3d")


def _resolve_input(path_str: str) -> Path:
    """Resolve a caller-supplied filename to an absolute path confined to the workspace.

    Only bare filenames are accepted — no absolute paths, no directory components.
    The resolved path must live under the workspace root (realpath check).
    """
    from portal.platform.mcp_host.workspace import get_uploads_dir, get_workspace_root

    # Strip any directory component the caller may have supplied and reject traversal.
    name = Path(path_str).name
    if not name or name != path_str.replace("\\", "/").split("/")[-1]:
        raise ValueError(f"Only bare filenames are accepted, got: {path_str!r}")

    workspace = get_workspace_root().resolve()
    for base in (_out_dir(), get_uploads_dir()):
        cand = (base / name).resolve()
        try:
            cand.relative_to(workspace)
        except ValueError:
            continue
        if cand.is_file():
            return cand
    raise FileNotFoundError(f"Input not found: {name}")


# ── rendering primitives ────────────────────────────────────────────────────
def _render_mesh_to_png(mesh_path: Path, png_path: Path, resolution: int = 1024) -> str:
    """Render a mesh to PNG. Tries trimesh offscreen (GL) first, falls back to a
    pure-CPU matplotlib triangle render. Returns a short note on which path was used."""
    import trimesh

    scene = trimesh.load(str(mesh_path), force="scene")
    # Attempt GL offscreen via trimesh.Scene.save_image (uses pyglet/pyrender +
    # whatever PYOPENGL_PLATFORM points at; osmesa/egl in headless containers).
    try:
        png_bytes = scene.save_image(resolution=(resolution, resolution), visible=False)
        if png_bytes:
            png_path.write_bytes(png_bytes)
            return "rendered via trimesh offscreen GL"
    except Exception as e:  # noqa: BLE001 — any GL init failure -> CPU fallback
        logger.warning("trimesh GL render failed (%s); using matplotlib CPU fallback", e)

    # Pure-CPU fallback: matplotlib 3D trisurf. No GL context required.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    geom = trimesh.load(str(mesh_path), force="mesh")
    fig = plt.figure(figsize=(resolution / 100, resolution / 100), dpi=100)
    ax = fig.add_subplot(111, projection="3d")
    tris = geom.vertices[geom.faces]
    coll = Poly3DCollection(tris, alpha=1.0, edgecolor="none")
    coll.set_facecolor((0.55, 0.65, 0.85))
    ax.add_collection3d(coll)
    b = geom.bounds
    ax.set_xlim(b[0][0], b[1][0])
    ax.set_ylim(b[0][1], b[1][1])
    ax.set_zlim(b[0][2], b[1][2])
    try:
        ax.set_box_aspect(b[1] - b[0])
    except Exception:  # noqa: BLE001 — older mpl lacks set_box_aspect
        pass
    ax.set_axis_off()
    ax.view_init(elev=25, azim=-60)
    fig.savefig(str(png_path), bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return "rendered via matplotlib CPU fallback (no GL context)"


def _maybe_review(png_path: Path, prompt: str) -> str | None:
    """If the review loop is enabled, send the PNG to the vision model for a short
    geometry critique. Returns the critique text or None. Never raises into the tool."""
    if not REVIEW_LOOP_ENABLED:
        return None
    try:
        import httpx

        b64 = base64.b64encode(png_path.read_bytes()).decode()
        payload = {
            "model": REVIEW_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "This is a headless render of a 3D-printed part the user is "
                                "designing: " + prompt + ". In 3-4 sentences, critique the "
                                "geometry for obvious modelling errors, non-manifold hints, "
                                "missing features, or printability red flags. Be concrete."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
            "stream": False,
        }
        with httpx.Client(timeout=120) as client:
            r = client.post(f"{PIPELINE_URL}/v1/chat/completions", json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001 — review is best-effort, never fails the render
        logger.warning("Review loop failed (%s); returning render without critique", e)
        return None


# ── HTTP routes (mirror music_mcp conventions) ──────────────────────────────
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "cad-render-mcp"})


@mcp.custom_route("/capabilities", methods=["GET"])
async def capabilities_route(request):
    return JSONResponse(cad_capabilities())


@mcp.custom_route("/files/models3d/{filename:path}", methods=["GET"])
async def serve_generated_file(request):
    filename = request.path_params["filename"]
    if not SAFE_FILENAME.match(filename):
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    file_path = _out_dir() / filename
    if not file_path.exists() or not file_path.is_file():
        return JSONResponse({"error": "File not found"}, status_code=404)
    media = "image/png" if file_path.suffix == ".png" else "application/octet-stream"
    return FileResponse(path=str(file_path), filename=filename, media_type=media)


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_cad_render_mcp")


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


# ── POST /tools/<name> — pipeline dispatch endpoints ─────────────────────────


@mcp.custom_route("/tools/render_mesh", methods=["POST"])
async def render_mesh_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    result = await render_mesh(
        mesh_path=args.get("mesh_path", ""),
        resolution=int(args.get("resolution", 1024)),
        review=bool(args.get("review", False)),
        prompt=args.get("prompt", ""),
    )
    return JSONResponse(result)


@mcp.custom_route("/tools/render_openscad", methods=["POST"])
async def render_openscad_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    result = await render_openscad(
        code=args.get("code", ""),
        resolution=int(args.get("resolution", 1024)),
    )
    return JSONResponse(result)


@mcp.custom_route("/tools/convert_cad", methods=["POST"])
async def convert_cad_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    result = await convert_cad(
        input_path=args.get("input_path", ""),
        to_format=args.get("to_format", ""),
    )
    return JSONResponse(result)


# ── tools ───────────────────────────────────────────────────────────────────
@mcp.tool()
async def render_mesh(
    mesh_path: str, resolution: int = 1024, review: bool = False, prompt: str = ""
) -> dict:
    """Render a mesh to PNG (headless) and report bounding-box dimensions."""
    import trimesh

    src = _resolve_input(mesh_path)
    if src.suffix.lower() not in MESH_EXTS:
        return {
            "error": f"Unsupported mesh extension {src.suffix!r}. Supported: {sorted(MESH_EXTS)}"
        }
    out_name = f"render_{uuid.uuid4().hex[:8]}.png"
    out_png = _out_dir() / out_name
    note = _render_mesh_to_png(src, out_png, resolution=resolution)

    geom = trimesh.load(str(src), force="mesh")
    extents = getattr(geom, "extents", None)
    dims = (
        {"x": float(extents[0]), "y": float(extents[1]), "z": float(extents[2])}
        if extents is not None
        else None
    )
    validation = validate_mesh(src)

    result = {
        "png_path": str(out_png),
        "png_url": f"{PUBLIC_URL}/{out_name}",
        "bounding_box": dims,
        "render_note": note,
        "watertight": bool(getattr(geom, "is_watertight", False)),
        "validation": validation,
        "problems": validation["problems"],
    }
    critique = _maybe_review(out_png, prompt or f"mesh {src.name}") if review else None
    if critique:
        result["review"] = critique
    elif review and not REVIEW_LOOP_ENABLED:
        result["review_note"] = (
            "review requested but CAD_RENDER_REVIEW_LOOP is off (default); artifact emitted without critique"
        )
    return result


def _compile_scad(
    code: str, scad_path: Path, stl_path: Path, timeout: int = 120
) -> tuple[bool, str, bool]:
    """Run openscad --render. Returns (ok, stderr, timed_out)."""
    scad_path.write_text(code)
    openscad = os.getenv("OPENSCAD_BIN", "openscad")
    cmd = [openscad, "--render", "-o", str(stl_path), str(scad_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)  # noqa: S603
    except FileNotFoundError:
        return False, f"openscad binary not found (set OPENSCAD_BIN). Tried: {openscad}", False
    except subprocess.TimeoutExpired:
        return False, f"openscad render timed out ({timeout}s)", True
    if proc.returncode != 0 or not stl_path.exists():
        return False, proc.stderr, False
    return True, proc.stderr, False


@mcp.tool()
async def render_openscad(code: str, resolution: int = 1024) -> dict:
    """Render OpenSCAD source to PNG.

    Strategy: openscad headless can produce STL without a display; PNG requires GL.
    We export STL first (always works), then feed it through _render_mesh_to_png
    which has a matplotlib CPU fallback — so a PNG is always produced.
    """
    uid = uuid.uuid4().hex[:8]
    scad_path = _out_dir() / f"model_{uid}.scad"
    stl_path = _out_dir() / f"model_{uid}.stl"
    png_name = f"model_{uid}.png"
    png_path = _out_dir() / png_name

    ok, stderr, timed_out = _compile_scad(code, scad_path, stl_path)
    if not ok:
        err = classify_openscad_error(stderr, timed_out=timed_out)
        return {"error": f"openscad failed: {err['raw']}", "error_detail": err}

    note = _render_mesh_to_png(stl_path, png_path, resolution=resolution)
    validation = validate_mesh(stl_path)
    return {
        "png_path": str(png_path),
        "png_url": f"{PUBLIC_URL}/{png_name}",
        "scad_path": str(scad_path),
        "stl_path": str(stl_path),
        "render_note": note,
        "validation": validation,
        "problems": validation["problems"],
    }


@mcp.tool()
async def convert_cad(input_path: str, to_format: str) -> dict:
    """Convert a model between mesh formats. STEP read is best-effort."""
    import trimesh

    to_format = to_format.lower().lstrip(".")
    if to_format not in {"stl", "3mf", "obj", "ply"}:
        return {"error": f"Unsupported target {to_format!r}. Supported: stl, 3mf, obj, ply"}
    src = _resolve_input(input_path)

    if src.suffix.lower() in {".step", ".stp"}:
        if not cad_capabilities()["step_read"]:
            return {
                "error": "STEP read requires build123d/OCP, neither is importable in this "
                "process (cad_capabilities()['step_read'] is False). Export STL from the "
                "sandbox instead, or install the conda-forge OCP layer (see PLATFORM.md)."
            }
        try:
            from build123d import import_step  # type: ignore

            shape = import_step(str(src))
            mesh = shape.tessellate(0.1)
            geom = trimesh.Trimesh(vertices=mesh[0], faces=mesh[1])
        except Exception as e:  # noqa: BLE001
            return {
                "error": f"STEP read requires build123d/OCP and failed: {e}. Export STL from the sandbox instead."
            }
    else:
        geom = trimesh.load(str(src), force="mesh")

    out_name = f"{src.stem}_{uuid.uuid4().hex[:6]}.{to_format}"
    out_path = _out_dir() / out_name
    geom.export(str(out_path))
    return {"output_path": str(out_path), "output_url": f"{PUBLIC_URL}/{out_name}"}


# ── self-correcting feedback loop (TASK_CAD_MODULE_OVERHAUL_V1 Phase 4) ─────


def classify_openscad_error(stderr: str, timed_out: bool = False) -> dict:
    """Categorize openscad stderr into actionable buckets with a fix hint."""
    cats = {
        "syntax_error": bool(re.search(r"syntax error|parse error|expected", stderr, re.I)),
        "undefined_variable": bool(re.search(r"undefined|unknown variable", stderr, re.I)),
        "empty_geometry": bool(
            re.search(r"empty geometry|no geometry|WARNING:.*empty", stderr, re.I)
        ),
        "non_manifold": bool(re.search(r"non.?manifold|self.?intersect", stderr, re.I)),
        "timeout": timed_out,
    }
    active = {k: v for k, v in cats.items() if v}
    return {"raw": (stderr or "")[:800], "categories": active, "suggestion": _suggest_fix(active)}


def _suggest_fix(active: dict) -> str:
    if "timeout" in active:
        return "Render timed out — the CSG tree may be too deep/expensive; simplify or reduce $fn."
    if "undefined_variable" in active:
        return "A dimension references a name not in parameters{}; add it or fix the spelling."
    if "syntax_error" in active:
        return (
            "OpenSCAD syntax error in the emitted/escape-hatch source; check for unbalanced braces."
        )
    if "non_manifold" in active:
        return "Non-manifold geometry — likely a coincident face; nudge overlapping features apart."
    if "empty_geometry" in active:
        return "The CSG tree produced no geometry — check that a difference() didn't remove everything."
    return "Unclassified openscad failure; inspect 'raw' for detail."


def _auto_repair(geometry: dict, err: dict) -> dict | None:
    """Deterministic, safe repairs only — never mutates design intent.
    Returns a repaired geometry dict, or None if this error needs the model's judgment."""
    cats = err.get("categories", {})
    if "timeout" in cats:
        repaired = dict(geometry)
        repaired["_fn_override"] = 24  # coarser tessellation, cheaper render
        return repaired
    return None  # syntax/undefined_variable/non_manifold/empty_geometry need model judgment


def _auto_repair_mesh(geometry: dict, mv: dict) -> dict | None:
    """Deterministic repairs for a validated-but-flawed mesh. None => surface to the model."""
    problems = mv.get("problems", [])
    if problems == ["degenerate_faces"] and not geometry.get("_fn_override"):
        # A common degenerate-face cause is too-coarse tessellation on curved
        # features; bumping $fn is a safe, intent-preserving fix.
        repaired = dict(geometry)
        repaired["_fn_override"] = 96
        return repaired
    return None


@mcp.tool()
async def generate_scad(geometry: dict, resolution: int = 1024, max_retries: int = 2) -> dict:
    """Generate a parametric part from a constrained Tier-A/B JSON geometry description.

    One call: validate JSON -> emit SCAD (scad_emitter.py owns all coordinate-frame
    math) -> compile -> validate mesh -> render PNG -> on failure, auto-retry with
    the classified error fed back (Layer 1). If still not printable after
    max_retries, the model should read `validation`/`problems`/`retry_log` and
    issue a corrected call (Layer 2) — see auto-cad's system_prompt_append.
    """
    retry_log: list[dict] = []
    attempt = 0
    uid = uuid.uuid4().hex[:8]

    while attempt <= max_retries:
        try:
            scad = emit_scad(geometry, fn=geometry.get("_fn_override", FN_DEFAULT))
        except EmitError as e:
            return {
                "error": f"geometry validation failed: {e}",
                "error_category": e.category,
                "attempts": attempt + 1,
                "retry_log": retry_log,
            }

        scad_path = _out_dir() / f"gen_{uid}_{attempt}.scad"
        stl_path = _out_dir() / f"gen_{uid}_{attempt}.stl"
        ok, stderr, timed_out = _compile_scad(scad, scad_path, stl_path)

        if not ok:
            err = classify_openscad_error(stderr, timed_out=timed_out)
            retry_log.append({"attempt": attempt, "stage": "compile", "error": err})
            repaired = _auto_repair(geometry, err)
            if repaired is None or attempt == max_retries:
                return {
                    "error": f"openscad compile failed: {err['raw']}",
                    "error_detail": err,
                    "scad_source": scad,
                    "attempts": attempt + 1,
                    "retry_log": retry_log,
                }
            geometry = repaired
            attempt += 1
            continue

        validation = validate_mesh(stl_path)
        if validation["problems"]:
            retry_log.append(
                {"attempt": attempt, "stage": "validate", "problems": validation["problems"]}
            )
            repaired = _auto_repair_mesh(geometry, validation)
            if repaired is None or attempt == max_retries:
                png_name = f"gen_{uid}_{attempt}.png"
                png_path = _out_dir() / png_name
                note = _render_mesh_to_png(stl_path, png_path, resolution=resolution)
                return {
                    "scad_source": scad,
                    "scad_path": str(scad_path),
                    "stl_path": str(stl_path),
                    "png_path": str(png_path),
                    "png_url": f"{PUBLIC_URL}/{png_name}",
                    "render_note": note,
                    "validation": validation,
                    "bounding_box": validation["bounding_box"],
                    "watertight": validation["watertight"],
                    "attempts": attempt + 1,
                    "retry_log": retry_log,
                }
            geometry = repaired
            attempt += 1
            continue

        # success
        png_name = f"gen_{uid}_{attempt}.png"
        png_path = _out_dir() / png_name
        note = _render_mesh_to_png(stl_path, png_path, resolution=resolution)
        return {
            "scad_source": scad,
            "scad_path": str(scad_path),
            "stl_path": str(stl_path),
            "png_path": str(png_path),
            "png_url": f"{PUBLIC_URL}/{png_name}",
            "render_note": note,
            "validation": validation,
            "bounding_box": validation["bounding_box"],
            "watertight": validation["watertight"],
            "attempts": attempt + 1,
            "retry_log": retry_log,
        }

    # unreachable (loop always returns), but keeps type-checkers happy
    return {
        "error": "retry loop exhausted without a terminal result",
        "attempts": attempt,
        "retry_log": retry_log,
    }


@mcp.custom_route("/tools/generate_scad", methods=["POST"])
async def generate_scad_endpoint(request):
    body = await request.json()
    args = body.get("arguments", {})
    result = await generate_scad(
        geometry=args.get("geometry", {}),
        resolution=int(args.get("resolution", 1024)),
        max_retries=int(args.get("max_retries", 2)),
    )
    return JSONResponse(result)


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
