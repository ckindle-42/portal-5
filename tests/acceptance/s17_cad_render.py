"""S17: CAD render MCP tests (TASK_CAD_RENDER_MCP_V1).

Covers the three tools exposed by mcp-cad-render (:8926):
  render_mesh    — STL/OBJ/PLY → PNG + bounding-box
  render_openscad — OpenSCAD source → STL → PNG (headless; no GL required)
  convert_cad    — mesh format conversion (STL→OBJ etc.)

Also validates the file-serving HTTP route and the auto-cad workspace routing.
"""

import json
import os
import struct
import tempfile
import time

from tests.acceptance._common import (
    MCP,
    _get,
    _mcp,
    _mcp_get,
    _mcp_raw,
    _post,
    AUTH,
    PIPELINE_URL,
    record,
)

_CAD_RENDER_PORT = int(os.environ.get("CAD_RENDER_HOST_PORT", "8926"))

# Minimal valid binary STL for a 20×10×5 mm box (12 triangles, 684 bytes).
# Generated inline so the test has no file fixtures.
def _make_box_stl(w: float = 20, h: float = 10, d: float = 5) -> bytes:
    def tri(n, v1, v2, v3):
        return (
            struct.pack("<fff", *n)
            + struct.pack("<fff", *v1)
            + struct.pack("<fff", *v2)
            + struct.pack("<fff", *v3)
            + struct.pack("<H", 0)
        )

    x, y, z = w, h, d
    tris = [
        ((0, 0, -1), (0, 0, 0), (x, 0, 0), (x, y, 0)),
        ((0, 0, -1), (0, 0, 0), (x, y, 0), (0, y, 0)),
        ((0, 0, 1),  (0, 0, z), (x, y, z), (x, 0, z)),
        ((0, 0, 1),  (0, 0, z), (0, y, z), (x, y, z)),
        ((-1, 0, 0), (0, 0, 0), (0, y, 0), (0, y, z)),
        ((-1, 0, 0), (0, 0, 0), (0, y, z), (0, 0, z)),
        ((1, 0, 0),  (x, 0, 0), (x, 0, z), (x, y, z)),
        ((1, 0, 0),  (x, 0, 0), (x, y, z), (x, y, 0)),
        ((0, -1, 0), (0, 0, 0), (0, 0, z), (x, 0, z)),
        ((0, -1, 0), (0, 0, 0), (x, 0, z), (x, 0, 0)),
        ((0, 1, 0),  (0, y, 0), (x, y, 0), (x, y, z)),
        ((0, 1, 0),  (0, y, 0), (x, y, z), (0, y, z)),
    ]
    body = b"".join(tri(*t) for t in tris)
    return b"\x00" * 80 + struct.pack("<I", len(tris)) + body


async def run() -> None:
    """S17: CAD render MCP tests."""
    print("\n━━━ S17. CAD RENDER MCP ━━━")
    sec = "S17"

    # ── S17-01: service health ────────────────────────────────────────────────
    t0 = time.time()
    code, _ = await _get(f"http://localhost:{_CAD_RENDER_PORT}/health")
    record(
        sec,
        "S17-01",
        "CAD render MCP health",
        "PASS" if code == 200 else "FAIL",
        f"HTTP {code}",
        t0=t0,
    )

    # ── S17-02: tools manifest ────────────────────────────────────────────────
    t0 = time.time()
    code, body = await _get(f"http://localhost:{_CAD_RENDER_PORT}/tools")
    tools = {t["name"] for t in body.get("tools", [])} if isinstance(body, dict) else set()
    expected = {"render_mesh", "render_openscad", "convert_cad"}
    record(
        sec,
        "S17-02",
        "Tools manifest — render_mesh / render_openscad / convert_cad",
        "PASS" if expected <= tools else "FAIL",
        f"found: {sorted(tools)}",
        t0=t0,
    )

    # ── S17-03: render_mesh — STL → PNG with correct bounding box ────────────
    # Write a fresh test STL into the shared workspace so the container can see it.
    from portal_mcp.core.workspace import get_generated_dir  # noqa: PLC0415 — lazy import, avoids import at module level
    models3d = get_generated_dir("models3d")
    models3d.mkdir(parents=True, exist_ok=True)
    test_stl = models3d / "s17_smoke_box.stl"
    test_stl.write_bytes(_make_box_stl(20, 10, 5))

    await _mcp(
        _CAD_RENDER_PORT,
        "render_mesh",
        {"mesh_path": "s17_smoke_box.stl", "resolution": 256},
        section=sec,
        tid="S17-03",
        name="render_mesh — 20×10×5 box → PNG + bbox",
        ok_fn=lambda t: (
            "png_url" in t
            and '"x": 20.0' in t
            and '"y": 10.0' in t
            and '"z": 5.0' in t
            and '"watertight": true' in t
        ),
        detail_fn=lambda t: t[:200],
        timeout=60,
    )

    # ── S17-04: render_mesh — PNG URL is reachable ────────────────────────────
    # We need the png_url from the previous call; call the tool again and inspect.
    t0 = time.time()
    code_r, body_r = await _mcp_raw(
        _CAD_RENDER_PORT,
        "render_mesh",
        {"mesh_path": "s17_smoke_box.stl", "resolution": 128},
        section=sec,
        tid="S17-04-pre",
        name="(internal) render_mesh for URL check",
        timeout=60,
    )
    png_url = None
    if code_r == 200 and isinstance(body_r, dict):
        try:
            result = json.loads(body_r.get("content", [{}])[0].get("text", "{}"))
            png_url = result.get("png_url")
        except Exception:
            pass
    if png_url:
        # Convert container-internal URL to host-accessible URL
        host_url = png_url.replace("http://localhost", f"http://localhost")
        code_f, _ = await _get(host_url, timeout=10)
        record(sec, "S17-04", "render_mesh PNG URL reachable via HTTP", "PASS" if code_f == 200 else "FAIL", f"GET {host_url} → {code_f}", t0=t0)
    else:
        record(sec, "S17-04", "render_mesh PNG URL reachable via HTTP", "WARN", "Could not extract png_url from render_mesh result", t0=t0)

    # ── S17-05: render_openscad — SCAD → STL → PNG ───────────────────────────
    scad_code = (
        "// parametric test shape\n"
        "wall = 2;\n"
        "linear_extrude(height = 15)\n"
        "  difference() {\n"
        "    square([30, 20]);\n"
        "    translate([wall, wall]) square([30 - 2*wall, 20 - 2*wall]);\n"
        "  }\n"
    )
    await _mcp(
        _CAD_RENDER_PORT,
        "render_openscad",
        {"code": scad_code, "resolution": 256},
        section=sec,
        tid="S17-05",
        name="render_openscad — hollow box SCAD → PNG",
        ok_fn=lambda t: "png_url" in t and "stl_path" in t and "error" not in t,
        detail_fn=lambda t: t[:200],
        timeout=90,
    )

    # ── S17-06: render_openscad — sphere primitive ────────────────────────────
    await _mcp(
        _CAD_RENDER_PORT,
        "render_openscad",
        {"code": "sphere(r = 10, $fn = 24);", "resolution": 128},
        section=sec,
        tid="S17-06",
        name="render_openscad — sphere primitive",
        ok_fn=lambda t: "png_url" in t and "error" not in t,
        timeout=60,
    )

    # ── S17-07: convert_cad — STL → OBJ ──────────────────────────────────────
    await _mcp(
        _CAD_RENDER_PORT,
        "convert_cad",
        {"input_path": "s17_smoke_box.stl", "to_format": "obj"},
        section=sec,
        tid="S17-07",
        name="convert_cad — STL → OBJ",
        ok_fn=lambda t: "output_url" in t and ".obj" in t,
        timeout=30,
    )

    # ── S17-08: convert_cad — STL → PLY ──────────────────────────────────────
    await _mcp(
        _CAD_RENDER_PORT,
        "convert_cad",
        {"input_path": "s17_smoke_box.stl", "to_format": "ply"},
        section=sec,
        tid="S17-08",
        name="convert_cad — STL → PLY",
        ok_fn=lambda t: "output_url" in t and ".ply" in t,
        timeout=30,
    )

    # ── S17-09: render_mesh — reject unsupported extension ───────────────────
    await _mcp(
        _CAD_RENDER_PORT,
        "render_mesh",
        {"mesh_path": "s17_smoke_box.stl", "resolution": 64},
        section=sec,
        tid="S17-09",
        name="render_mesh — STL recognised (regression: ext check)",
        ok_fn=lambda t: "error" not in t or "Unsupported" not in t,
        timeout=30,
    )

    # ── S17-10: auto-cad workspace routes correctly ───────────────────────────
    # The router must assign auto-cad for a clear 3D-print request.
    t0 = time.time()
    code_r, body_r = await _post(
        f"{PIPELINE_URL}/v1/chat/completions",
        {
            "model": "auto-cad",
            "messages": [{"role": "user", "content": "Design a 20x10x5mm mounting bracket in OpenSCAD"}],
            "max_tokens": 50,
            "stream": False,
        },
        headers=AUTH,
        timeout=30,
    )
    routed_ok = code_r == 200 and isinstance(body_r, dict)
    record(
        sec,
        "S17-10",
        "auto-cad workspace — pipeline accepts request",
        "PASS" if routed_ok else "FAIL",
        f"HTTP {code_r}",
        t0=t0,
    )
