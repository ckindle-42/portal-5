"""Build tests/wfe/suites/cad_production.jsonl, auto-coding::cad's production suite
(WFE P3 triage §4; master plan S8/O5).

Every part is a generated solid with a closed-form volume the generator computes and
never writes by hand; the spec (lengths, hole count, diameters) is stated in the
instruction, the derived volume never is. Three kinds, 36 tasks, 12 in the screen tier (four per kind on screen):

- plate-holes (12)  an L×W×H plate with N through holes of diameter d:
                   volume = L·W·H − N·π·(d/2)²·H;
- extrusion (12)    a right-triangle or trapezoid profile extruded by L:
                   volume = (a·b/2)·L or ((p+q)/2·t)·L;
- revolve (12)      a cylinder or truncated cone revolved: π·r²·h or π·h/3·(R²+Rr+r²).

Every task is graded on its answer (`answer_contains`, the stated JSON keys) AND on
where it came from: `tool_grounded` twice — once on a successful `cad_build`
(`"ok": true`, stage `validated` — portal/modules/cad/tools/b123d_bridge.py:353-357)
and once on the measured volume: `cad_build` measures as it builds and `cad_measure`
returns `{"ok": ..., "measure": {"volume": <float>}}` (b123d_bridge.py:369-374; the
engine measure tail's shape in the repo's own bridge tests,
tests/unit/test_cad_b123d_bridge.py:98-104). The volume evidence matches the FLOOR of
the true volume, which no hand-computed answer can satisfy without a part whose
measured volume really is the spec's — a plate built without its holes fails here.
The tool output legitimately carries the gold (that IS the grounding), so unlike the
absent-kind research tasks nothing is forbidden in tool output; the no-leak rule this
suite enforces is that the instruction states the spec and never the derived volume
(tested), and that grounding only counts through the cad_* tools.

Tool output shapes are declared from the bridge source above and backlogged in
coding_task/WFE_LIVE_BACKLOG.md for live verification; the engine's find_holes tail is
unverified and deliberately unused by any checker.

    uv run python tests/wfe/suites/build_cad_production.py
"""

from __future__ import annotations

import json
import math
import random
import re
from pathlib import Path

from tests.wfe.suites._publish import publish_text
from tests.wfe.suites.build_research_production import Fact

OUT = Path(__file__).with_name("cad_production.jsonl")
COUNTS = {"plate-holes": 12, "extrusion": 12, "revolve": 12}
SCREEN = {"plate-holes": 4, "extrusion": 4, "revolve": 4}
LANE = "cad"
SEEDS = {"plate-holes": 9200, "extrusion": 9300, "revolve": 9400}
#: Gold volumes already used by a built task (reset by build()); the spec drawers
#: re-seed on a collision so the suite's golds stay unique.
_USED_GOLDS: set[str] = set()
#: The cad_* pipeline surface (b123d_bridge.py TOOL_NAMES) the allowlist offers.
CAD_TOOLS = [
    "cad_build",
    "cad_execute",
    "cad_measure",
    "cad_find_holes",
    "cad_render",
    "cad_finalize",
]
GROUND_TOOLS = ["cad_build", "cad_measure"]
FORMAT_HOLES = 'Answer only as JSON {"volume_mm3": <whole number>, "holes": <count>}.'
FORMAT_VOL = 'Answer only as JSON {"volume_mm3": <whole number>}.'

DECIDING_FACTS: dict[str, list[dict]] = {}


def _usable(vol: float) -> bool:
    """A volume whose truncated whole number is stable: the true value stays clear of
    the next integer, so the engine's float and the model's rounding cannot disagree
    at the digit the answer and the measure evidence are both graded on."""
    frac = vol - math.floor(vol)
    return 0.08 <= frac <= 0.98


def _pattern(gold: str) -> str:
    return rf'"volume_mm3"\s*:\s*"?{re.escape(gold)}"?(?![\w.-])'


def _holes_pattern(n: int) -> str:
    return rf'"holes"\s*:\s*"?{n}"?(?![\w.-])'


def _volume_evidence(vol: float) -> str:
    """The measure tail must show the true volume's whole-number part (the same digit
    the answer states — the volume is reported rounded down) with a decimal fraction:
    no hand-computed answer can satisfy this without a part whose measured volume
    really is the spec's."""
    return rf'"volume"\s*:\s*{math.floor(vol)}\.'


def _phrase(imperative: bool, question: str, command: str) -> str:
    return command if imperative else question


def _reference_code(kind: str, s: dict) -> str:
    """A build123d script in the module emitter's own idiom (b123d_emitter.py:
    `part = Box(...)`, `part -= ... * Cylinder(...)`, `extrude(make_face(Polyline(...),
    close=True))`, `revolve(...)`), used for the control trace's code argument and the
    attainability probe's build call."""
    if kind == "plate-holes":
        lines = [f"part = Box({s['L']}, {s['W']}, {s['H']})"]
        step = (s["L"] - 2 * s["d"]) / max(s["N"] - 1, 1)
        for i in range(s["N"]):
            x = s["d"] + i * step - s["L"] / 2
            lines.append(
                f"part -= Plane.XY.offset({s['H'] / 2}) * Pos({x:.4g}, 0, 0) "
                f"* Cylinder({s['d'] / 2}, {s['H'] + 2})"
            )
        return "\n".join(lines)
    if kind == "extrusion":
        if s["shape"] == "triangle":
            pts = f"((0, 0), ({s['a']}, 0), (0, {s['b']}))"
        else:
            pts = f"((0, 0), ({s['q']}, 0), ({s['q']}, {s['t']}), (0, {s['t']}))"
        return (
            f"profile = make_face(Polyline({pts}, close=True))\npart = extrude(profile, {s['L']})"
        )
    if s["shape"] == "cylinder":
        pts = f"((0, 0), ({s['r']}, 0), ({s['r']}, {s['h']}), (0, {s['h']}))"
    else:
        pts = f"((0, 0), ({s['R']}, 0), (0, {s['h']}))"
    return f"profile = make_face(Polyline({pts}, close=True))\npart = revolve(profile, Axis.Y, 360)"


# ---------------------------------------------------------------- specs


def plate_spec(r: random.Random) -> dict:
    while True:
        ln, wd, ht = 5 * r.randint(6, 18), 5 * r.randint(6, 18), r.randint(4, 12)
        n, d = r.randint(2, 6), 2 * r.randint(2, 5)
        if d >= min(ln, wd) - 10 or n * d > ln:
            continue
        vol = ln * wd * ht - n * math.pi * (d / 2) ** 2 * ht
        if vol > 0 and _usable(vol):
            return {
                "L": ln,
                "W": wd,
                "H": ht,
                "N": n,
                "d": d,
                "vol": vol,
                "wrong": float(ln * wd * ht),
                "detail": "plate with through holes",
            }


def extrusion_spec(r: random.Random) -> dict:
    """Polyhedral volumes are half-integer granular (the profile area carries a /2),
    so the dimensions are drawn with odd parities that land the fraction on .5 —
    comfortably inside _usable's window. Millimetre specs stay whole numbers."""
    if r.random() < 0.5:  # right-triangle profile, legs a and b
        while True:
            a, b = r.choice(range(13, 62, 2)), r.choice(range(13, 62, 2))
            ln = r.choice(range(31, 80, 2))
            vol = a * b / 2 * ln
            if _usable(vol):
                return {
                    "shape": "triangle",
                    "a": a,
                    "b": b,
                    "L": ln,
                    "vol": vol,
                    "wrong": float(a * b * ln),
                    "detail": "right-triangle profile extruded",
                }
    while True:  # trapezoid profile, parallel sides p and q, thickness t
        p, q = r.choice(range(13, 62, 2)), r.choice(range(14, 62, 2))
        t, ln = r.choice(range(7, 26, 2)), r.choice(range(31, 80, 2))
        vol = (p + q) / 2 * t * ln
        if _usable(vol):
            return {
                "shape": "trapezoid",
                "p": max(p, q),
                "q": min(p, q),
                "t": t,
                "L": ln,
                "vol": vol,
                "wrong": max(p, q) * t * ln,
                "detail": "trapezoid profile extruded",
            }


def revolve_spec(r: random.Random) -> dict:
    if r.random() < 0.5:  # solid cylinder
        while True:
            rr, h = r.randint(5, 30), 5 * r.randint(4, 14)
            vol = math.pi * rr**2 * h
            if _usable(vol):
                return {
                    "shape": "cylinder",
                    "r": rr,
                    "h": h,
                    "vol": vol,
                    "wrong": math.pi * (2 * rr) ** 2 * h,
                    "detail": "solid cylinder",
                }
    while True:  # truncated cone, radii rb at the base and rr at the top
        rb, rr, h = r.randint(10, 30), r.randint(3, 9), 5 * r.randint(4, 12)
        if rr >= rb:
            continue
        vol = math.pi * h / 3 * (rb**2 + rb * rr + rr**2)
        if _usable(vol):
            return {
                "shape": "frustum",
                "R": rb,
                "r": rr,
                "h": h,
                "vol": vol,
                "wrong": math.pi * rb**2 * h,
                "detail": "truncated cone",
            }


# ---------------------------------------------------------------- assembly


def _statement(kind: str, s: dict) -> str:
    if kind == "plate-holes":
        return (
            f"A plate is {s['L']} mm long, {s['W']} mm wide and {s['H']} mm thick, with "
            f"{s['N']} through holes of diameter {s['d']} mm drilled through the thickness."
        )
    if kind == "extrusion":
        if s["shape"] == "triangle":
            return (
                f"A part is a right triangle with legs {s['a']} mm and {s['b']} mm, "
                f"extruded {s['L']} mm."
            )
        return (
            f"A part has a trapezoid profile with parallel sides {s['p']} mm and {s['q']} mm "
            f"and thickness {s['t']} mm, extruded {s['L']} mm."
        )
    if s["shape"] == "cylinder":
        return f"A part is a solid cylinder with radius {s['r']} mm and height {s['h']} mm."
    return (
        f"A part is a truncated cone with base radius {s['R']} mm, top radius {s['r']} mm "
        f"and height {s['h']} mm."
    )


def _instruction(kind: str, n: int, s: dict) -> str:
    body = _statement(kind, s)
    fmt = FORMAT_HOLES if kind == "plate-holes" else FORMAT_VOL
    ask = (
        "Build the part with the CAD tools, measure what you built, and report its volume "
        "in cubic millimetres, rounded down to the nearest whole number"
        + (", together with the number of holes you built" if kind == "plate-holes" else "")
        + "."
    )
    return _phrase(n % 3 == 0, f"{body} {ask} {fmt}", f"Build it: {body} {ask} {fmt}")


def _task(tid: str, kind: str, n: int, s: dict) -> dict:
    gold, wrong = str(math.floor(s["vol"])), str(math.floor(s["wrong"]))
    if gold == wrong:
        raise RuntimeError(f"{tid}: confuser volume rounds to the gold")
    name = {"plate-holes": "plate", "extrusion": "profile_part", "revolve": "turned_part"}[kind]
    code = _reference_code(kind, s)
    build_out = json.dumps(
        {
            "ok": True,
            "stage": "validated",
            "delivered": False,
            "execute": "OK",
            "measure": {"volume": round(s["vol"], 4)},
            "validate": {"valid": True},
            "next": "NOT DELIVERED YET — the user has no files until you call cad_finalize now",
        }
    )
    measure_out = json.dumps({"ok": True, "measure": {"volume": round(s["vol"], 4)}})
    trace = [
        {"name": "cad_build", "args": {"code": code}, "output": build_out, "error": None},
        {
            "name": "cad_measure",
            "args": {"object_name": name},
            "output": measure_out,
            "error": None,
        },
    ]
    answer = {"volume_mm3": gold}
    if kind == "plate-holes":
        answer["holes"] = str(s["N"])
    ins = _instruction(kind, n, s)
    t = {
        "id": tid,
        "kind": kind,
        "lane": LANE,
        "agentic": True,
        "screen": n < SCREEN[kind],
        "instruction": ins,
        "requires_tools": sorted(GROUND_TOOLS),
        "checkers": [
            {"type": "answer_contains", "patterns": [_pattern(gold)]},
            {
                "type": "tool_grounded",
                "tools": ["cad_build"],
                "evidence": ['"ok"\\s*:\\s*true', "validated"],
            },
            {
                "type": "tool_grounded",
                "tools": GROUND_TOOLS,
                "evidence": [_volume_evidence(s["vol"])],
            },
        ],
        "controls": {
            "pass": [{"answer": json.dumps(answer), "tool_calls": trace}],
            "fail": [
                {"answer": json.dumps(answer), "tool_calls": []},
                {"answer": json.dumps({"volume_mm3": wrong}), "tool_calls": trace},
            ],
        },
    }
    facts = [
        Fact(
            "cad_build",
            {"code": code},
            r'"ok"\s*:\s*true',
            f"the reference {s['detail']} build validates",
        ),
        Fact(
            "cad_measure",
            {"object_name": name},
            _volume_evidence(s["vol"]),
            "the measured volume shows the spec geometry's whole-number part",
        ),
    ]
    DECIDING_FACTS[tid] = facts
    return t


def build_task(kind: str, n: int) -> dict:
    tid = f"cad-{kind}-{n:02d}"
    for attempt in range(1000):
        r = random.Random(SEEDS[kind] + n + attempt * 1000)
        s = {"plate-holes": plate_spec, "extrusion": extrusion_spec, "revolve": revolve_spec}[kind](
            r
        )
        gold = str(math.floor(s["vol"]))
        if gold not in _USED_GOLDS:
            break
    else:
        raise RuntimeError(f"{tid}: no unique gold volume found")
    _USED_GOLDS.add(gold)
    return _task(tid, kind, n, s)


def build() -> list[dict]:
    DECIDING_FACTS.clear()
    _USED_GOLDS.clear()
    tasks = [build_task(k, n) for k, count in COUNTS.items() for n in range(count)]
    golds = [json.loads(t["controls"]["pass"][0]["answer"])["volume_mm3"] for t in tasks]
    if len(golds) != len(set(golds)):
        raise RuntimeError(f"duplicate gold volumes across the suite: {sorted(golds)}")
    for t in tasks:
        if (gold := json.loads(t["controls"]["pass"][0]["answer"])["volume_mm3"]) in t[
            "instruction"
        ]:
            raise RuntimeError(f"{t['id']}: the instruction states the gold volume {gold}")
    tasks.sort(key=lambda t: not t["screen"])
    return tasks


def main() -> None:
    tasks = build()
    publish_text(OUT, "".join(json.dumps(t) + "\n" for t in tasks))
    print(f"wrote {OUT.name}: {len(tasks)} tasks, {sum(t['screen'] for t in tasks)} screen")


if __name__ == "__main__":
    main()
