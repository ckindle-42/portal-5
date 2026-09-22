"""Same-session A/B of Qwen image edit: August HF repo vs the 2509 weights.

mflux 0.19.1 maps the seated tag ``qwen-image-edit`` to
``Qwen/Qwen-Image-Edit-2509``. The August checkpoint is therefore the HF repo
``Qwen/Qwen-Image-Edit`` with ``--base-model qwen-image-edit``, and the 2509
arm is the built-in alias ``qwen-edit-2509`` (the string ``qwen-image-edit-2509``
is not an alias). Tags come from the environment so this file does not change
the seated default.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import time
from pathlib import Path

CORPUS = Path("tests/benchmarks/fixtures/qwen_edit_corpus")
OUT_DIR = Path("tests/benchmarks/results/qwen_edit_2509_outputs")

BASELINE_TAG = os.environ.get("QIE_BASELINE_TAG", "Qwen/Qwen-Image-Edit")
QIE_2509_TAG = os.environ.get("QIE_2509_TAG", "qwen-edit-2509")
MFLUX_QWEN_EDIT_BIN = os.environ.get(
    "MFLUX_QWEN_EDIT_BIN",
    os.path.expanduser("~/.portal5/mflux/.venv/bin/mflux-generate-qwen-edit"),
)
INVOCATION_CASE = os.environ.get(
    "QIE_INVOCATION_CASE",
    "alias-qwen-edit-2509; august baseline is HF Qwen/Qwen-Image-Edit because "
    "the seated tag qwen-image-edit already resolves to Qwen/Qwen-Image-Edit-2509 "
    "in mflux 0.19.1",
)

ITEMS = [
    (
        "id01",
        {"baseline", "2509"},
        ["portrait_1.png"],
        "same person, wearing a red sweater",
        "identity_preservation",
    ),
    (
        "id02",
        {"baseline", "2509"},
        ["portrait_2.png"],
        "same person, wearing a blue hat",
        "identity_preservation",
    ),
    (
        "id03",
        {"baseline", "2509"},
        ["portrait_3.png"],
        "same person, smiling broadly",
        "identity_preservation",
    ),
    (
        "id04",
        {"baseline", "2509"},
        ["portrait_4.png"],
        "same person, looking to the left, side profile",
        "identity_preservation",
    ),
    (
        "mi01",
        {"2509"},
        ["portrait_1.png", "scene_1.png"],
        "place the person from the first image on the park bench in the second image",
        "multi_image",
    ),
    (
        "mi02",
        {"2509"},
        ["portrait_2.png", "scene_2.png"],
        "place the person from the first image seated at the office desk in the second image",
        "multi_image",
    ),
    (
        "mi03",
        {"2509"},
        ["portrait_3.png", "scene_3.png"],
        "place the person from the first image walking on the cobblestone street in the second image",
        "multi_image",
    ),
    (
        "tx01",
        {"baseline", "2509"},
        ["portrait_1.png"],
        "add the text 'HELLO' in white on the sweater",
        "text_editing",
    ),
    (
        "tx02",
        {"baseline", "2509"},
        ["portrait_2.png"],
        "add the text 'PORTAL 5' in black on the hat",
        "text_editing",
    ),
    (
        "ct01",
        {"2509"},
        ["portrait_4.png"],
        "same person, hands raised above head, three-quarter view",
        "controlnet_style_pose",
    ),
]


def _generate(arm: str, tag: str, item_id: str, images: list[str], prompt: str) -> dict:
    out_path = OUT_DIR / arm / f"{item_id}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        MFLUX_QWEN_EDIT_BIN,
        "--model",
        tag,
        "--prompt",
        prompt,
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
    if "/" in tag:
        cmd += ["--base-model", "qwen-image-edit"]
    # Live CLI: --image-paths takes one or more sources. --image is a
    # PATH+STRENGTH pair and does not accumulate repeated flags.
    cmd += ["--image-paths", *[str(CORPUS / img) for img in images]]

    t0 = time.perf_counter()
    row: dict = {"arm": arm, "id": item_id, "cmd_tail": cmd[-8:], "images": images}
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("MFLUX_TIMEOUT", "900")),
        )
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


def run() -> dict:
    started_at = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for item_id, arms, images, prompt, category in ITEMS:
        for arm in ("baseline", "2509"):
            if arm not in arms:
                continue
            tag = BASELINE_TAG if arm == "baseline" else QIE_2509_TAG
            print(f"  [{item_id}/{arm}] {category}", flush=True)
            row = _generate(arm, tag, item_id, images, prompt)
            row["category"] = category
            row["prompt"] = prompt
            results.append(row)
            print(f"    ok={row['mechanical_ok']} t={row['wall_s']}s", flush=True)

    per_arm = {"baseline": {"n": 0, "ok": 0}, "2509": {"n": 0, "ok": 0}}
    for row in results:
        per_arm[row["arm"]]["n"] += 1
        per_arm[row["arm"]]["ok"] += 1 if row["mechanical_ok"] else 0

    return {
        "started_at_utc": started_at,
        "head_commit": head,
        "invocation_case": INVOCATION_CASE,
        "baseline_tag": BASELINE_TAG,
        "qie_2509_tag": QIE_2509_TAG,
        "mflux_version_note": "0.19.1 seated qwen-image-edit -> Qwen/Qwen-Image-Edit-2509",
        "n_items": len(results),
        "per_arm_mechanical": per_arm,
        "results": results,
    }


def write_report(receipt: dict, md_path: Path) -> None:
    by_key = {(r["arm"], r["id"]): r for r in receipt["results"]}
    lines = [
        "# Qwen-Image-Edit-2509 probe",
        "",
        f"- Portal HEAD: `{receipt['head_commit']}`",
        f"- Invocation: {receipt['invocation_case']}",
        f"- Baseline tag: `{receipt['baseline_tag']}`",
        f"- 2509 tag: `{receipt['qie_2509_tag']}`",
        f"- Started: {receipt['started_at_utc']}",
        "",
        receipt["mflux_version_note"],
        "",
        "No persistent config change. The seated `MFLUX_QWEN_EDIT_TAG` is untouched.",
        "",
        "## Mechanical rates",
        "",
    ]
    for arm, stats in receipt["per_arm_mechanical"].items():
        rate = stats["ok"] / stats["n"] if stats["n"] else 0.0
        lines.append(f"- {arm}: {stats['ok']}/{stats['n']} ({rate:.1%})")
    lines += [
        "",
        "## Pairs",
        "",
        "| id | category | baseline | 2509 | baseline_s | 2509_s | operator score (1-5) |",
        "|---|---|---|---|---|---|---|",
    ]
    for item_id, _arms, _images, _prompt, category in ITEMS:
        base = by_key.get(("baseline", item_id))
        new = by_key.get(("2509", item_id))
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
        "## Operator gate (P2.G1)",
        "",
        "Score identity preservation, multi-image faithfulness, text editing,",
        "and pose accuracy from 1 to 5. Promotion is not applied by this task.",
        "A follow-up that switches the seated tag is reasonable when 2509 beats",
        "the August baseline on at least 3 of 4 identity items, at least 2 of 3",
        "multi-image items score at least 3, and text editing does not regress.",
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
    out_json = Path(args.out or f"tests/benchmarks/results/qwen_image_edit_2509_probe_{ts}.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(receipt, indent=2))
    md_path = out_json.with_suffix(".md")
    write_report(receipt, md_path)
    print(f"\nWrote {out_json}")
    print(f"Wrote {md_path}")
    for arm, stats in receipt["per_arm_mechanical"].items():
        rate = stats["ok"] / stats["n"] if stats["n"] else 0.0
        print(f"  {arm}: {stats['ok']}/{stats['n']} mechanical ({rate:.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
