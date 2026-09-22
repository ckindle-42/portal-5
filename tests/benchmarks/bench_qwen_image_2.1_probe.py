"""Same-session A/B: seated qwen-image-edit vs the newer, different Qwen-Image-2.1.

The prior P2 probe (reverted) tested Qwen-Image-Edit-2509, a point-update to
the model already wired as the seated `qwen-image-edit` roster key. That was
not what was asked for. Qwen-Image-2.1 (`Qwen/Qwen-Image-2.1`) is a separate,
newer, unified txt2img+editing model with a different architecture
(single-stream block-causal DiT, Qwen3-VL text encoder, 64-channel causal
VAE). mflux 0.19.1 (seated) has no support for it; the host-native mflux venv
was upgraded to 0.20.0, which adds native `mflux-generate-qwen-2.1` support
(txt2img, img2img via --image PATH STRENGTH, optional true CFG).

Qwen-Image-2.1 does not have a dedicated instruction-following edit mode like
qwen-image-edit — img2img here uses --image as an init/starting point with a
strength parameter, not "follow this instruction on this photo." That's a
real capability difference, not a bench artifact; it's called out per-item
below and in the report.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import time
from pathlib import Path

CORPUS = Path("tests/benchmarks/fixtures/qwen21_corpus")
OUT_DIR = Path("tests/benchmarks/results/qwen21_outputs")

BASELINE_BIN = os.environ.get(
    "MFLUX_QWEN_EDIT_BIN", os.path.expanduser("~/.portal5/mflux/.venv/bin/mflux-generate-qwen-edit")
)
QWEN21_BIN = os.environ.get(
    "MFLUX_QWEN21_BIN", os.path.expanduser("~/.portal5/mflux/.venv/bin/mflux-generate-qwen-2.1")
)
BASELINE_TAG = os.environ.get("QWEN_EDIT_TAG", "qwen-image-edit")  # seated default

ITEMS = [
    # id, images, edit_prompt (baseline: instruction-style), gen_prompt (2.1: full-scene description), category
    (
        "id01",
        ["portrait_1.png"],
        "same person, wearing a red sweater",
        "photorealistic portrait of the same young woman with brown hair, wearing a red sweater, studio lighting",
        "identity_preservation",
    ),
    (
        "id02",
        ["portrait_2.png"],
        "same person, wearing a blue hat",
        "photorealistic portrait of the same older man with grey beard, wearing a blue hat, studio lighting",
        "identity_preservation",
    ),
    (
        "id03",
        ["portrait_3.png"],
        "same person, smiling broadly",
        "photorealistic portrait of the same middle-aged woman with red hair, smiling broadly, studio lighting",
        "identity_preservation",
    ),
    (
        "id04",
        ["portrait_4.png"],
        "same person, looking to the left, side profile",
        "photorealistic portrait of the same young man with black hair and glasses, side profile looking left, studio lighting",
        "identity_preservation",
    ),
    (
        "tx01",
        ["portrait_1.png"],
        "add the text 'HELLO' in white on the sweater",
        "photorealistic portrait of the same young woman with brown hair wearing a sweater with the text HELLO printed in white",
        "text_editing",
    ),
    (
        "tx02",
        ["portrait_2.png"],
        "add the text 'PORTAL 5' in black on the hat",
        "photorealistic portrait of the same older man with grey beard wearing a hat with the text PORTAL 5 printed in black",
        "text_editing",
    ),
    (
        "gen01",
        [],
        None,
        "a modern office desk with a laptop, a red apple beside the keyboard, natural window light, photorealistic",
        "base_generation",
    ),
    (
        "gen02",
        [],
        None,
        "a cobblestone European street at dusk with warm streetlamp light and light rain reflections, photorealistic",
        "base_generation",
    ),
]

IMG2IMG_STRENGTH = float(os.environ.get("QWEN21_IMG2IMG_STRENGTH", "0.5"))


def _run(cmd: list[str], out_path: Path, timeout_s: int) -> dict:
    t0 = time.perf_counter()
    row: dict = {"cmd_tail": cmd[-10:]}
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        row["returncode"] = completed.returncode
        row["stderr_tail"] = (completed.stderr or completed.stdout)[-800:]
        row["output_path"] = str(out_path) if out_path.exists() else None
        row["output_size"] = out_path.stat().st_size if out_path.exists() else 0
        row["mechanical_ok"] = out_path.exists() and out_path.stat().st_size > 5000
    except subprocess.TimeoutExpired:
        row["mechanical_ok"] = False
        row["error"] = "timeout"
    except Exception as exc:  # noqa: BLE001
        row["mechanical_ok"] = False
        row["error"] = f"{type(exc).__name__}: {exc}"[:400]
    row["wall_s"] = round(time.perf_counter() - t0, 2)
    return row


def _baseline(item_id: str, images: list[str], edit_prompt: str) -> dict:
    out_path = OUT_DIR / "baseline" / f"{item_id}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        BASELINE_BIN,
        "--model",
        BASELINE_TAG,
        "--prompt",
        edit_prompt,
        "--steps",
        "20",
        "--quantize",
        "8",
        "--low-ram",
        "--seed",
        "42",
        "--width",
        "768",
        "--height",
        "768",
        "--output",
        str(out_path),
        "--image-paths",
        *[str(CORPUS / img) for img in images],
    ]
    return _run(cmd, out_path, int(os.environ.get("MFLUX_TIMEOUT", "900")))


def _qwen21(item_id: str, images: list[str], gen_prompt: str) -> dict:
    out_path = OUT_DIR / "2.1" / f"{item_id}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        QWEN21_BIN,
        "--prompt",
        gen_prompt,
        "--steps",
        "20",
        "--quantize",
        "8",
        "--low-ram",
        "--seed",
        "42",
        "--width",
        "768",
        "--height",
        "768",
        "--output",
        str(out_path),
    ]
    if images:
        cmd += ["--image", str(CORPUS / images[0]), str(IMG2IMG_STRENGTH)]
    return _run(cmd, out_path, int(os.environ.get("MFLUX_TIMEOUT", "900")))


def run() -> dict:
    started_at = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for item_id, images, edit_prompt, gen_prompt, category in ITEMS:
        if edit_prompt is not None:
            print(f"  [{item_id}/baseline] {category}", flush=True)
            row = _baseline(item_id, images, edit_prompt)
            row.update(
                {"arm": "baseline", "id": item_id, "category": category, "prompt": edit_prompt}
            )
            results.append(row)
            print(f"    ok={row['mechanical_ok']} t={row['wall_s']}s", flush=True)

        print(f"  [{item_id}/2.1] {category}", flush=True)
        row = _qwen21(item_id, images, gen_prompt)
        row.update(
            {
                "arm": "2.1",
                "id": item_id,
                "category": category,
                "prompt": gen_prompt,
                "img2img_strength": IMG2IMG_STRENGTH if images else None,
            }
        )
        results.append(row)
        print(f"    ok={row['mechanical_ok']} t={row['wall_s']}s", flush=True)

    per_arm = {"baseline": {"n": 0, "ok": 0}, "2.1": {"n": 0, "ok": 0}}
    for row in results:
        per_arm[row["arm"]]["n"] += 1
        per_arm[row["arm"]]["ok"] += 1 if row["mechanical_ok"] else 0

    return {
        "started_at_utc": started_at,
        "head_commit": head,
        "baseline_tag": BASELINE_TAG,
        "qwen21_note": "Qwen/Qwen-Image-2.1 via mflux 0.20.0 mflux-generate-qwen-2.1",
        "img2img_strength": IMG2IMG_STRENGTH,
        "n_items": len(results),
        "per_arm_mechanical": per_arm,
        "results": results,
    }


def write_report(receipt: dict, md_path: Path) -> None:
    by_key = {(r["arm"], r["id"]): r for r in receipt["results"]}
    lines = [
        "# Qwen-Image-2.1 probe (correct model — supersedes the reverted 2509 probe)",
        "",
        f"- Portal HEAD: `{receipt['head_commit']}`",
        f"- Baseline tag: `{receipt['baseline_tag']}` (seated qwen-image-edit)",
        f"- 2.1: {receipt['qwen21_note']}",
        f"- img2img strength for identity/text items: {receipt['img2img_strength']}",
        f"- Started: {receipt['started_at_utc']}",
        "",
        "Qwen-Image-2.1 has no instruction-following edit mode like qwen-image-edit — "
        "its arm uses --image as an img2img init at the strength above, with the target "
        "description as the prompt, not an editing instruction. gen01/gen02 are base "
        "generation only (no baseline arm — qwen-image-edit requires a source image).",
        "",
        "## Mechanical rates",
        "",
    ]
    for arm, stats in receipt["per_arm_mechanical"].items():
        rate = stats["ok"] / stats["n"] if stats["n"] else 0.0
        lines.append(f"- {arm}: {stats['ok']}/{stats['n']} ({rate:.1%})")
    lines += [
        "",
        "## Items",
        "",
        "| id | category | baseline | 2.1 | baseline_s | 2.1_s | operator score (1-5) |",
        "|---|---|---|---|---|---|---|",
    ]
    for item_id, _images, _edit_prompt, _gen_prompt, category in ITEMS:
        base = by_key.get(("baseline", item_id))
        new = by_key.get(("2.1", item_id))
        lines.append(
            "| {id} | {cat} | `{bp}` | `{np}` | {bs} | {ns} |  |".format(
                id=item_id,
                cat=category,
                bp=(base or {}).get("output_path") or "",
                np=(new or {}).get("output_path") or "",
                bs=(base or {}).get("wall_s", ""),
                ns=(new or {}).get("wall_s", ""),
            )
        )
    lines += [
        "",
        "## Operator gate",
        "",
        "Score identity preservation, text editing, and base-generation quality 1-5.",
        "Promotion is not applied by this task.",
        "",
        "Operator scores: PENDING",
        "",
    ]
    md_path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    receipt = run()
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_json = Path(args.out or f"tests/benchmarks/results/qwen_image_2.1_probe_{ts}.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(receipt, indent=2))
    md_path = out_json.with_suffix(".md")
    write_report(receipt, md_path)
    print(f"\nWrote {out_json}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
