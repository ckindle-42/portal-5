"""Shared post-render mesh validation (TASK_CAD_MODULE_OVERHAUL_V1 Phase 3).

`validate_mesh()` is the single validation surface for all three render tools
(render_mesh, render_openscad, generate_scad). Its `problems` list is
machine-readable and is exactly what the Phase-4 self-correction loop keys off
of — not just a display field.
"""

from __future__ import annotations

from pathlib import Path


def validate_mesh(stl_path: Path) -> dict:
    """Load `stl_path` and report watertightness, volume, bbox, and problems[]."""
    import trimesh

    mesh = trimesh.load(str(stl_path), force="mesh")
    extents = getattr(mesh, "extents", None)
    watertight = bool(mesh.is_watertight)

    problems: list[str] = []
    if len(mesh.faces) == 0:
        problems.append("empty_geometry")
    if not watertight:
        problems.append("non_watertight")
    if hasattr(mesh, "degenerate_faces") and mesh.degenerate_faces.sum() > 0:
        problems.append("degenerate_faces")

    return {
        "watertight": watertight,
        "volume_mm3": float(mesh.volume) if watertight else None,
        "bounding_box": (
            {"x": float(extents[0]), "y": float(extents[1]), "z": float(extents[2])}
            if extents is not None
            else None
        ),
        "face_count": len(mesh.faces),
        "vertex_count": len(mesh.vertices),
        "problems": problems,
        "printable": watertight and len(mesh.faces) > 0,
    }
