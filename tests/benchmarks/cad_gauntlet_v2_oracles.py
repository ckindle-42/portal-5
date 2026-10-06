#!/usr/bin/env python3
"""Reference build123d oracles for CAD gauntlet v2 (TASK_CAD_ARM_REDEVELOP_V1).

Rebuilds each gauntlet part exactly as specified in its prompt, exports STL, and
grades it with tests/benchmarks/cad_grader.py. Two jobs:
  1. Provenance for GAUNTLET_V2_TRUTH (volumes/bboxes were computed by this file).
  2. An end-to-end platform probe: run inside the CAD container (linux/arm64)
     and on the host (macOS arm64) — every oracle must grade PASS on both.

Usage: python tests/benchmarks/cad_gauntlet_v2_oracles.py [--out DIR] [--json]
Exit 0 iff all oracles PASS.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from build123d import (  # noqa: E402
    Align,
    Axis,
    Box,
    CounterSinkHole,
    Cylinder,
    GeomType,
    Plane,
    Polyline,
    Pos,
    RegularPolygon,
    Rot,
    chamfer,
    export_stl,
    extrude,
    fillet,
    make_face,
    offset,
    revolve,
)

from tests.benchmarks.cad_grader import grade_mesh  # noqa: E402

BASE = (Align.CENTER, Align.CENTER, Align.MIN)


def build_all() -> dict:
    parts = {}
    p = Box(80, 50, 5)
    for x in (-32, 32):
        for y in (-17, 17):
            p -= Pos(x, y) * Cylinder(2.5, 5)
    parts["plate_4holes"] = p

    p = Box(80, 30, 4)
    for x in (-25, 0, 25):
        p -= Pos(x, 0) * Cylinder(5, 4)
    top = p.faces().sort_by(Axis.Z)[-1]
    parts["grommet_plate"] = chamfer(top.edges().filter_by(GeomType.CIRCLE), 1)

    p = Box(60, 40, 25, align=BASE)
    p = offset(p, amount=-2, openings=p.faces().sort_by(Axis.Z)[-1])
    for x in (-23, 23):
        for y in (-13, 13):
            p += Pos(x, y, 2) * Cylinder(3, 6, align=BASE)
            p -= Pos(x, y, 3) * Cylinder(1.25, 5, align=BASE)
    parts["enclosure"] = p

    base = Box(40, 30, 3, align=(Align.CENTER, Align.MIN, Align.MIN))
    up = Box(40, 3, 25, align=(Align.CENTER, Align.MIN, Align.MIN))
    p = base + up
    inner = (
        p.edges()
        .filter_by(Axis.X)
        .filter_by(lambda e: abs(e.center().Y - 3) < 1e-6 and abs(e.center().Z - 3) < 1e-6)
    )
    p = fillet(inner, 3)
    for x in (-12, 12):
        p -= Pos(x, 18, 0) * Cylinder(2.25, 3, align=BASE)
        p -= Pos(x, 0, 15) * Rot(-90, 0, 0) * Cylinder(2.25, 3, align=BASE)
    parts["l_bracket"] = p

    prof = Polyline((5, 0), (15, 0), (15, 3), (8, 3), (8, 20), (5, 20), close=True)
    parts["flanged_bushing"] = revolve(make_face(Plane.XZ * prof), Axis.Z)

    p = Box(60, 30, 6)
    for x in (-20, 20):
        p -= Pos(x, 0, 3) * CounterSinkHole(2.25, 4.5, depth=6)
    parts["countersunk_plate"] = p

    parts["hex_standoff"] = extrude(
        RegularPolygon(8 / math.sqrt(3), 6, major_radius=True), 15
    ) - Cylinder(1.65, 30)

    from bd_warehouse.gear import SpurGear  # ships with build123d-mcp

    gear = SpurGear(module=2, tooth_count=12, pressure_angle=20, root_fillet=0.5, thickness=8)
    parts["spur_gear"] = gear - Cylinder(2.5, 40)
    return parts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    out = args.out or Path(tempfile.mkdtemp(prefix="cad_oracles_"))
    out.mkdir(parents=True, exist_ok=True)
    report = {"machine": platform.machine(), "system": platform.system(), "results": {}}
    ok = True
    for name, part in build_all().items():
        f = out / f"{name}.stl"
        export_stl(part, str(f), tolerance=0.01, angular_tolerance=0.1)
        g = grade_mesh(name, f)
        report["results"][name] = {"verdict": g["verdict"], "measured": g.get("measured")}
        ok &= g["verdict"] == "PASS"
        if not args.json:
            print(f"{name:18s} {g['verdict']:9s} {g.get('measured')}")
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        print(f"machine={report['machine']} system={report['system']} all_pass={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
