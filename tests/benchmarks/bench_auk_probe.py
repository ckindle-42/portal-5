"""Bounded 10-item AuK spike probe.

Runs against the AuK MCP at the port recorded in the P0 discover receipt.
Corpus clips are staged into the shared uploads directory by basename so
``resolve_upload_path`` can see them (Rule 11). Quality is not scored here.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import time
import wave
from pathlib import Path

import httpx

DISCOVER = json.load(open("tests/benchmarks/results/landscape_2026Q3_p0_discover.json"))
DEFAULT_PORT = int(DISCOVER["free_port_chosen_for_auk"] or 8940)

CORPUS = Path("tests/benchmarks/fixtures/auk_corpus")
TWO_SPEAKERS = Path("tests/fixtures/sample_two_speakers.wav")


def _uploads_dir() -> Path:
    root = Path(os.environ.get("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))
    dest = root / "uploads"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _stage(path: Path) -> str:
    dest = _uploads_dir() / path.name
    if dest.resolve() != path.resolve():
        shutil.copyfile(path, dest)
    return path.name


ITEMS = [
    ("s01", "synthesize", {"text": "hello from Portal five"}, "tts_baseline", False),
    (
        "s02",
        "synthesize",
        {
            "text": "hello from Portal five",
            "reference_audio_url": "reference_voice.wav",
        },
        "voice_cloning",
        False,
    ),
    (
        "e01",
        "edit_content",
        {
            "source_audio_url": "neutral_a.wav",
            "instruction": "replace 'Monday' with 'Tuesday'",
        },
        "content_edit",
        True,
    ),
    (
        "e02",
        "edit_content",
        {
            "source_audio_url": "neutral_b.wav",
            "instruction": "replace 'compliance' with 'security'",
        },
        "content_edit",
        True,
    ),
    (
        "p01",
        "edit_paralinguistic",
        {
            "source_audio_url": "neutral_a.wav",
            "instruction": "make this sound cheerful",
        },
        "paralinguistic_edit",
        True,
    ),
    (
        "p02",
        "edit_paralinguistic",
        {
            "source_audio_url": "neutral_b.wav",
            "instruction": "make this sound sad",
        },
        "paralinguistic_edit",
        True,
    ),
    (
        "p03",
        "edit_paralinguistic",
        {
            "source_audio_url": "neutral_a.wav",
            "instruction": "convert to a whisper",
        },
        "paralinguistic_edit",
        True,
    ),
    (
        "sep01",
        "separate",
        {"source_audio_url": "mixed_voice_noise.wav"},
        "separation",
        True,
    ),
    (
        "sep02",
        "separate",
        {"source_audio_url": "sample_two_speakers.wav"},
        "separation",
        True,
    ),
    (
        "enh01",
        "enhance",
        {"source_audio_url": "mixed_voice_noise.wav"},
        "enhancement",
        True,
    ),
]


def _wav_ok(path: str) -> tuple[bool, dict]:
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return False, {"reason": "missing_or_empty", "path": str(p)}
    try:
        with wave.open(str(p), "rb") as handle:
            info = {
                "channels": handle.getnchannels(),
                "sample_rate": handle.getframerate(),
                "duration_s": round(handle.getnframes() / handle.getframerate(), 3),
                "size_bytes": p.stat().st_size,
            }
        return info["duration_s"] > 0.2, info
    except Exception as exc:  # noqa: BLE001
        return False, {"reason": "not_valid_wav", "error": str(exc)}


def _stage_corpus() -> None:
    for name in ("neutral_a.wav", "neutral_b.wav", "reference_voice.wav", "mixed_voice_noise.wav"):
        _stage(CORPUS / name)
    _stage(TWO_SPEAKERS)


def run(port: int) -> dict:
    base = f"http://localhost:{port}"
    started_at = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    variant = os.environ.get("AUK_VARIANT", "flash")
    auk_repo = Path(os.path.expanduser("~/.portal5/auk/repo"))
    auk_head = ""
    if (auk_repo / ".git").exists():
        auk_head = subprocess.check_output(
            ["git", "-C", str(auk_repo), "rev-parse", "HEAD"], text=True
        ).strip()

    _stage_corpus()
    health = httpx.get(f"{base}/health", timeout=10.0).json()
    if health.get("status") != "ok":
        raise SystemExit(f"AuK health not ok: {health}")

    results = []
    for item_id, tool, args, capability, seat_relevant in ITEMS:
        t0 = time.perf_counter()
        row: dict = {
            "id": item_id,
            "tool": tool,
            "capability": capability,
            "seat_relevant": seat_relevant,
            "args": args,
        }
        try:
            response = httpx.post(
                f"{base}/tools/{tool}",
                json=args,
                timeout=int(os.environ.get("AUK_TIMEOUT", "600")),
            )
            response.raise_for_status()
            payload = response.json()
            row["response"] = payload
            ok, info = _wav_ok(payload.get("output_path", ""))
            row["mechanical_ok"] = ok
            row["output_info"] = info
        except Exception as exc:  # noqa: BLE001
            row["mechanical_ok"] = False
            row["error"] = f"{type(exc).__name__}: {exc}"[:500]
        row["wall_s"] = round(time.perf_counter() - t0, 2)
        results.append(row)
        print(f"  [{item_id}] {tool}/{capability}: ok={row['mechanical_ok']} t={row['wall_s']}s")

    n_seat = sum(1 for row in results if row["seat_relevant"])
    n_seat_ok = sum(1 for row in results if row["seat_relevant"] and row["mechanical_ok"])
    return {
        "started_at_utc": started_at,
        "head_commit": head,
        "auk_repo_head": auk_head,
        "variant": variant,
        "port": port,
        "health": health,
        "n_items": len(results),
        "n_seat_relevant": n_seat,
        "n_seat_mechanical_ok": n_seat_ok,
        "mechanical_seat_rate": round(n_seat_ok / n_seat, 3) if n_seat else 0.0,
        "cli_delta": (
            "MLX branch exposes python -m auk_mlx.cli (--instruction/--audio/--output/--flash), "
            "not inference_mlx.py --task. Enhance and separate use cookbook instruction templates."
        ),
        "results": results,
    }


def write_report(receipt: dict, md_path: Path) -> None:
    lines = [
        "# AuK MLX probe",
        "",
        f"- Portal HEAD: `{receipt['head_commit']}`",
        f"- AuK repo HEAD: `{receipt.get('auk_repo_head') or 'unknown'}`",
        f"- Variant: `{receipt['variant']}`",
        f"- Port: {receipt['port']}",
        f"- Started: {receipt['started_at_utc']}",
        (
            f"- Mechanical seat rate: {receipt['n_seat_mechanical_ok']}/"
            f"{receipt['n_seat_relevant']} ({receipt['mechanical_seat_rate']:.1%})"
        ),
        "",
        "Mechanical seat rate is the fraction of seat-relevant items that produced",
        "a valid WAV. It is not the promotion criterion. Quality is the operator gate.",
        "",
        receipt.get("cli_delta", ""),
        "",
        "## Items",
        "",
        "| id | capability | seat | mechanical | wall_s | wav | operator score (1-5) |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in receipt["results"]:
        wav = ""
        if row.get("response"):
            wav = row["response"].get("output_path") or ""
        score = "" if row["seat_relevant"] else "n/a"
        lines.append(
            f"| {row['id']} | {row['capability']} | {row['seat_relevant']} | "
            f"{row['mechanical_ok']} | {row['wall_s']} | `{wav}` | {score} |"
        )
    lines += [
        "",
        "## Operator gate (P1.G1)",
        "",
        "Listen to the seven seat-relevant WAVs and fill the score column.",
        "Promotion is not applied by this task. A follow-up task is reasonable when:",
        "",
        "- at least 2 of 3 paralinguistic items score at least 3, and",
        "- at least 1 of 2 content-edit items scores at least 3, and",
        "- at least 1 of 2 separation items scores at least 3, and",
        "- the enhancement item scores at least 3.",
        "",
        "Operator scores: PENDING",
        "",
    ]
    md_path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    receipt = run(args.port)
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_json = Path(args.out or f"tests/benchmarks/results/auk_probe_{ts}.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(receipt, indent=2))
    md_path = out_json.with_suffix(".md")
    write_report(receipt, md_path)
    print(f"\nWrote {out_json}")
    print(f"Wrote {md_path}")
    print(
        "Mechanical pass on seat-relevant items: "
        f"{receipt['n_seat_mechanical_ok']}/{receipt['n_seat_relevant']} "
        f"({receipt['mechanical_seat_rate']:.1%})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
