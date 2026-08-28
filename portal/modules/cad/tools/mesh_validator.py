"""Shared post-render mesh validation (TASK_CAD_MODULE_OVERHAUL_V1 Phase 3).

`validate_mesh()` is the single validation surface for all three render tools
(render_mesh, render_openscad, generate_scad). Its `problems` list is
machine-readable and is exactly what the Phase-4 self-correction loop keys off
of — not just a display field.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[4] / "config/inference/cad_printability.json"


@lru_cache(maxsize=1)
def printability_limits() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def check_printability(mesh, limits: dict | None = None) -> list[dict]:
    import numpy as np
    import trimesh

    cfg = limits or printability_limits()
    warnings: list[dict] = []
    extents = np.asarray(mesh.extents, dtype=float)
    nozzle = float(cfg["nozzle_diameter_mm"])
    minimum = nozzle * float(cfg["minimum_feature_nozzles"])
    measured_min = float(extents.min()) if extents.size else 0.0
    if len(mesh.faces):
        try:
            sample_count = min(len(mesh.faces), 512)
            indices = np.linspace(0, len(mesh.faces) - 1, sample_count, dtype=int)
            local = trimesh.proximity.thickness(
                mesh,
                np.asarray(mesh.triangles_center)[indices],
                normals=np.asarray(mesh.face_normals)[indices],
                method="ray",
            )
            positive = np.asarray(local)[np.isfinite(local) & (np.asarray(local) > 1e-5)]
            if positive.size:
                measured_min = min(measured_min, float(positive.min()))
        except (AttributeError, ImportError, ModuleNotFoundError, ValueError):
            pass
    if measured_min < minimum:
        warnings.append(
            {
                "code": "minimum_feature_thickness",
                "measured_mm": measured_min,
                "limit_mm": minimum,
                "detail": f"minimum part extent {measured_min:.3f}mm is below {minimum:.3f}mm ({cfg['minimum_feature_nozzles']} nozzle widths)",
            }
        )

    max_overhang = float(cfg["max_unsupported_overhang_deg"])
    if len(mesh.faces):
        normals = np.asarray(mesh.face_normals)
        centers = np.asarray(mesh.triangles_center)
        min_z = float(mesh.bounds[0][2])
        # Down-facing faces touching the build plate are supported by the bed.
        candidates = (normals[:, 2] < -1e-6) & (centers[:, 2] > min_z + 1e-4)
        if candidates.any():
            measured = np.degrees(np.arcsin(np.clip(-normals[candidates, 2], 0.0, 1.0)))
            worst = float(measured.max())
            if worst > max_overhang:
                warnings.append(
                    {
                        "code": "unsupported_overhang",
                        "measured_deg": worst,
                        "limit_deg": max_overhang,
                        "detail": f"unsupported downward face reaches {worst:.1f}° from vertical; configured limit is {max_overhang:.1f}°",
                    }
                )

    bed = cfg["bed_size_mm"]
    for index, axis in enumerate(("x", "y", "z")):
        measured = float(extents[index])
        limit = float(bed[axis])
        if measured > limit:
            warnings.append(
                {
                    "code": "bed_size_fit",
                    "axis": axis,
                    "measured_mm": measured,
                    "limit_mm": limit,
                    "detail": f"{axis.upper()} extent {measured:.3f}mm exceeds bed limit {limit:.3f}mm",
                }
            )
    return warnings


def validate_mesh(stl_path: Path, limits: dict | None = None) -> dict:
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

    printability = check_printability(mesh, limits=limits)
    manifold_ok = watertight and len(mesh.faces) > 0 and not problems

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
        "manifold_ok": manifold_ok,
        "printability": printability,
        "printable": manifold_ok and not printability,
    }
