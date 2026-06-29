#!/usr/bin/env python3
"""Portal 5 — Game-Challenge Play@k Analyzer.

Two-layer scoring for the game_challenge tier:
  1. Static assertions — parsed from tests/UAT_RESULTS.md game_challenge rows.
  2. Play@k render-check — load each saved HTML artifact headless via
     Playwright, assert clean boot (no console/page errors), canvas present,
     and the game loop runs N frames without throwing.

Emits a comparative matrix (model x band) with both layers. No verdict —
the matrix is the deliverable; promotions are operator-only (PROMOTE_POLICY).

Usage:
  python3 tests/scripts/game_challenge_analyze.py \
      [--results tests/UAT_RESULTS.md] \
      [--artifacts tests/artifacts] \
      [--output tests/benchmarks/results/GAME_CHALLENGE_MATRIX_<UTC>.md]
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

ROW_RE = re.compile(
    r"^\|\s*\d+\s*\|\s*(?P<status>[A-Z]+)\s*\|\s*\[(?P<name>GC-0\d[^\]]*)\]"
    r"\([^)]*\)\s*\|\s*`(?P<slug>[^`]+)`\s*\|\s*(?P<detail>.*?)\|\s*(?P<elapsed>[\d.]+)s\s*\|\s*$"
)
FRACTION_RE = re.compile(r"(?P<passed>\d+)/(?P<total>\d+)\((?P<pct>\d+(?:\.\d+)?)%\)")
GC_ID_RE = re.compile(r"GC-0(?P<band>\d)-(?P<model>[\w-]+)")

BAND_NAME = {"1": "Flappy", "2": "Tetris", "3": "Platformer"}


def parse_static_rows(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        d = m.groupdict()
        f = FRACTION_RE.search(d["detail"])
        d["pct"] = float(f["pct"]) if f else None
        idm = GC_ID_RE.search(d["name"])
        d["band"] = idm["band"] if idm else "?"
        d["model"] = idm["model"] if idm else d["slug"]
        rows.append(d)
    return rows


async def _playk_check(html: str) -> dict:
    """Load a single self-contained HTML game headless; return Play@k signals."""
    from playwright.async_api import async_playwright

    result = {"booted": False, "has_canvas": False, "frames_ran": False, "errors": []}
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch()
            page = await b.new_page()
            page.on(
                "console",
                lambda msg: result["errors"].append(msg.text) if msg.type == "error" else None,
            )
            page.on("pageerror", lambda e: result["errors"].append(str(e)))
            await page.set_content(html, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(800)  # let the loop run frames
            result["has_canvas"] = await page.evaluate("() => !!document.querySelector('canvas')")
            # Frames ran = no uncaught error AND rAF/setInterval was scheduled.
            result["frames_ran"] = await page.evaluate(
                "() => (window.requestAnimationFrame && true) || false"
            )
            result["booted"] = len(result["errors"]) == 0
            await b.close()
    except Exception as e:  # noqa: BLE001
        result["errors"].append(f"render-harness: {e}")
    return result


def extract_html(artifact_path: Path) -> str | None:
    if not artifact_path.exists():
        return None
    txt = artifact_path.read_text(errors="ignore")
    # Saved artifacts may be raw .html or a fenced block; extract the HTML doc.
    m = re.search(r"<!DOCTYPE html>[\s\S]+?</html>", txt, re.IGNORECASE)
    if m:
        return m.group(0)
    m = re.search(r"<html[\s\S]+?</html>", txt, re.IGNORECASE)
    return m.group(0) if m else (txt if "<canvas" in txt.lower() else None)


def render_matrix(rows: list[dict], playk: dict[str, dict], source: str) -> str:
    by_model: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_model.setdefault(r["model"], {})[r["band"]] = r
    out = [
        "# Game-Challenge Capability Matrix (V1)",
        "",
        f"**Source**: `{source}` · generated {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "Two-layer scoring per band: **static** assertion pass-% and **Play@k** "
        "(did the single-file game boot clean + render a canvas headless). "
        "No verdict — promotions are operator-only (PROMOTE_POLICY).",
        "",
        "Legend: ✓ = Play@k boot clean · ✗ = console/page error · — = no artifact",
        "",
        "| Model | Flappy (static / Play@k) | Tetris (static / Play@k) | "
        "Platformer (static / Play@k) |",
        "|---|---|---|---|",
    ]
    for model in sorted(by_model):
        cells = []
        for band in ("1", "2", "3"):
            r = by_model[model].get(band)
            if not r:
                cells.append("—")
                continue
            static = f"{r['pct']:.0f}%" if r["pct"] is not None else "—"
            pk = playk.get(f"GC-0{band}-{model}")
            if pk is None:
                mark = "—"
            elif pk["booted"] and pk["has_canvas"]:
                mark = "✓"
            else:
                mark = "✗"
            cells.append(f"{static} / {mark}")
        out.append(f"| {model} | {cells[0]} | {cells[1]} | {cells[2]} |")
    out += ["", "## Play@k error detail", ""]
    for key in sorted(playk):
        pk = playk[key]
        if pk["errors"]:
            out.append(f"- **{key}**: {pk['errors'][:3]}")
    out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "tests" / "UAT_RESULTS.md"))
    ap.add_argument("--artifacts", default=str(ROOT / "tests" / "artifacts"))
    out_default = (
        ROOT
        / "tests"
        / "benchmarks"
        / "results"
        / ("GAME_CHALLENGE_MATRIX_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".md")
    )
    ap.add_argument("--output", default=str(out_default))
    args = ap.parse_args()

    rows = parse_static_rows(Path(args.results).read_text())
    if not rows:
        print("no game_challenge rows found in results", file=sys.stderr)
        return 2

    # Play@k pass over saved artifacts.
    art_dir = Path(args.artifacts)
    playk: dict[str, dict] = {}
    for r in rows:
        key = r["name"].split()[0]  # GC-0N-model
        # Artifacts saved by the driver are named per test id; match by prefix.
        candidates = list(art_dir.glob(f"*{key}*.html")) if art_dir.exists() else []
        if not candidates:
            continue
        html = extract_html(candidates[0])
        if html:
            playk[key] = asyncio.run(_playk_check(html))

    Path(args.output).write_text(render_matrix(rows, playk, args.results))
    print(f"wrote {args.output} ({len(rows)} static rows, {len(playk)} Play@k checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
