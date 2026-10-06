"""Sealed, spec-derived grader for CAD gauntlet v2 (TASK_CAD_ARM_REDEVELOP_V1).

The grader never trusts what a CAD tool *reports* about its own output. It reads
the artifact file an arm produced (STL, or STEP tessellated to STL by the caller)
and checks it against ground truth computed from the task spec by reference
build123d oracles (volumes/bboxes recorded in GAUNTLET_V2_TRUTH). Checks:

  valid      — mesh loads, is watertight, and is a single body
  bbox       — sorted extents within max(0.5 mm, 1 %) of truth, per axis
  volume     — within the per-task relative tolerance of the oracle volume
  genus      — topological genus (through-hole count for these parts) from the
               Euler characteristic: chi = V - E + F = 2 - 2g for one closed
               surface. Mirrors CADGenBench's Betti-number topology axis.

Verdicts: PASS (all four), WRONGSIZE (valid but bbox/volume/genus off),
INVALID (not watertight / multi-body / unreadable), MISSING (no artifact).
Score = fraction of the four checks passed (INVALID/MISSING score 0, validity-gated
like CADGenBench).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, cast

# Ground truth from reference build123d oracles (task-file dry run, build123d 0.11.1).
# bbox is sorted ascending; volume in mm^3; genus = through-holes.
GAUNTLET_V2_TRUTH: dict[str, dict[str, Any]] = {
    "plate_4holes": {"bbox": [5.0, 50.0, 80.0], "volume": 19607.3, "vol_tol": 0.03, "genus": 4},
    "grommet_plate": {"bbox": [4.0, 30.0, 80.0], "volume": 8607.3, "vol_tol": 0.03, "genus": 3},
    "enclosure": {"bbox": [25.0, 40.0, 60.0], "volume": 14212.4, "vol_tol": 0.05, "genus": 0},
    "l_bracket": {"bbox": [25.0, 30.0, 40.0], "volume": 6126.4, "vol_tol": 0.04, "genus": 4},
    "flanged_bushing": {"bbox": [20.0, 30.0, 30.0], "volume": 3967.8, "vol_tol": 0.03, "genus": 1},
    "countersunk_plate": {
        "bbox": [6.0, 30.0, 60.0],
        "volume": 10499.4,
        "vol_tol": 0.03,
        "genus": 2,
    },
    "hex_standoff": {"bbox": [8.0, 9.238, 15.0], "volume": 703.1, "vol_tol": 0.04, "genus": 1},
    # Gear oracle is bd_warehouse SpurGear (involute, 20 deg PA, 0.5 root fillet);
    # tooth-profile approximations legitimately differ, so vol_tol is wide.
    "spur_gear": {"bbox": [8.0, 28.0, 28.0], "volume": 3312.9, "vol_tol": 0.15, "genus": 1},
}


def _bbox_ok(got: list[float], want: list[float]) -> bool:
    return all(abs(g - w) <= max(0.5, 0.01 * w) for g, w in zip(got, want, strict=True))


def grade_mesh(task_id: str, artifact: str | Path | None) -> dict[str, Any]:
    """Grade one artifact against GAUNTLET_V2_TRUTH[task_id]. Never raises."""
    truth = GAUNTLET_V2_TRUTH[task_id]
    out: dict[str, Any] = {"task": task_id, "artifact": str(artifact) if artifact else None}
    if not artifact or not Path(artifact).exists():
        return {**out, "verdict": "MISSING", "score": 0.0}
    try:
        import trimesh

        mesh = cast("trimesh.Trimesh", trimesh.load(str(artifact), force="mesh"))
        mesh.merge_vertices()
        bodies = mesh.split(only_watertight=False)
        watertight = bool(mesh.is_watertight)
        n_bodies = len(bodies)
        ext = sorted(float(x) for x in mesh.extents)
        vol = float(abs(mesh.volume)) if watertight else None
        chi = int(mesh.euler_number)
        genus = (2 - chi) // 2 if n_bodies == 1 else None
    except Exception as e:  # noqa: BLE001 — unreadable artifact is a verdict, not a crash
        return {**out, "verdict": "INVALID", "score": 0.0, "error": f"{type(e).__name__}: {e}"}

    valid = watertight and n_bodies == 1
    checks = {
        "valid": valid,
        "bbox": _bbox_ok(ext, truth["bbox"]),
        "volume": vol is not None and math.isclose(vol, truth["volume"], rel_tol=truth["vol_tol"]),
        "genus": genus == truth["genus"],
    }
    measured = {
        "bbox": [round(x, 3) for x in ext],
        "volume": None if vol is None else round(vol, 1),
        "genus": genus,
        "bodies": n_bodies,
        "watertight": watertight,
    }
    if not valid:
        return {
            **out,
            "verdict": "INVALID",
            "score": 0.0,
            "checks": checks,
            "measured": measured,
            "truth": truth,
        }
    score = sum(checks.values()) / len(checks)
    verdict = "PASS" if all(checks.values()) else "WRONGSIZE"
    return {
        **out,
        "verdict": verdict,
        "score": round(score, 3),
        "checks": checks,
        "measured": measured,
        "truth": truth,
    }
