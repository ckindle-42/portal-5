#!/usr/bin/env python3
"""Milestone P1 driver: hunt one environment the way an analyst does, through Open WebUI.

1. Ask the `security-reviewer` workspace (streamed, like the chat UI) to start a hunt.
2. Read the job id out of the model's own answer.
3. Wait for the job (status read from the hunt store the MCP writes).
4. Ask Open WebUI for the top leads and case 1, and keep the transcripts the analyst sees.

Writes <out>/<index>.json with the transcripts and the job id; scoring is a separate step that
reads ~/AI_Output/review/hunts/<job>.json against the out-of-band key.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

HUNTS = Path.home() / "AI_Output" / "review" / "hunts"
TERMINAL = {"COMPLETE", "PARTIAL", "FAILED"}


def _write_receipt(path: Path, record: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(record, indent=1))
    temporary.replace(path)


def _job_snapshot(status: dict) -> dict:
    progress = status.get("progress")
    if not isinstance(progress, dict):
        progress = {}
    return {
        "status": status.get("status"),
        "stage": status.get("stage"),
        "phase": progress.get("phase"),
        "seed_rank": progress.get("seed_rank"),
        "lead_count": progress.get("lead_count"),
        "pivot_count": progress.get("pivot_count"),
        "query_count": progress.get("query_count"),
        "cell_count": progress.get("cell_count"),
        "event_count": progress.get("event_count"),
        "coverage_complete": status.get("coverage_complete"),
        "coverage_reason": status.get("coverage_reason"),
        "error": status.get("error"),
    }


def ask(prompt: str, key: str, model: str) -> str:
    body = json.dumps(
        {"model": model, "stream": True, "messages": [{"role": "user", "content": prompt}]}
    ).encode()
    req = urllib.request.Request(
        "http://localhost:8080/api/chat/completions",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    out = []
    with urllib.request.urlopen(req, timeout=1800) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                chunk = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            for choice in chunk.get("choices", []):
                out.append((choice.get("delta") or {}).get("content") or "")
    return "".join(out)


def _turn(prompt: str, key: str, model: str, record: dict) -> str:
    answer = ask(prompt, key, model)
    record["transcripts"].append({"prompt": prompt, "answer": answer, "at": time.time()})
    print(f">>> {prompt}\n{answer}\n", flush=True)
    return answer


def _wait_for_job(
    hunt_dir: Path, job: str, record: dict, receipt: Path, timeout_s: float, poll_s: float
) -> dict:
    deadline = time.monotonic() + timeout_s
    last_snapshot = None
    status = {"status": "PENDING"}
    while time.monotonic() < deadline:
        try:
            status = json.loads((hunt_dir / f"{job}.json").read_text())
            if not isinstance(status, dict):
                raise json.JSONDecodeError("status is not an object", "", 0)
        except FileNotFoundError:
            status = {"status": "PENDING"}
        except json.JSONDecodeError as exc:
            status = {"status": "STATUS_UNREADABLE", "error": str(exc)}
        snapshot = _job_snapshot(status)
        if snapshot != last_snapshot:
            record["status_samples"] = (record["status_samples"] + [snapshot])[-20:]
            last_snapshot = snapshot
        record["job_progress"] = status.get("progress")
        record["coverage_complete"] = status.get("coverage_complete")
        record["coverage_reason"] = status.get("coverage_reason")
        _write_receipt(receipt, record)
        if status.get("status") in TERMINAL:
            return status
        time.sleep(min(poll_s, max(0.0, deadline - time.monotonic())))
    status["supervision_timeout"] = True
    status["error"] = "job did not reach a terminal status before the supervision deadline"
    return status


def _exit_code(status: str, coverage_complete: bool | None) -> int:
    if status == "COMPLETE" and coverage_complete is True:
        return 0
    if status == "FAILED":
        return 1
    if status in {"PARTIAL", "COMPLETE"}:
        return 2
    return 3


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--index", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model", default="security-reviewer")
    ap.add_argument("--job-timeout-s", type=float, default=900)
    ap.add_argument("--poll-s", type=float, default=5)
    args = ap.parse_args()
    if args.job_timeout_s <= 0 or args.poll_s <= 0:
        ap.error("--job-timeout-s and --poll-s must be positive")
    key = os.environ["OWUI_API_KEY"]
    hunt_dir = Path(os.environ.get("PORTAL5_HUNT_DIR", str(HUNTS)))
    args.out.mkdir(parents=True, exist_ok=True)
    record: dict = {"index": args.index, "started": time.time(), "transcripts": []}
    receipt = args.out / f"{args.index}.json"
    answer = _turn(
        f"Start a hunt over the {args.index} environment and give me the job id.",
        key,
        args.model,
        record,
    )
    found = list(dict.fromkeys(re.findall(r"(?<![\w-])hunt-[0-9a-f]{12}(?![\w-])", answer)))
    if len(found) != 1:
        record.update(
            error="start outcome unknown: response did not contain exactly one valid hunt id",
            job_status="START_ID_UNKNOWN",
            finished=time.time(),
        )
        _write_receipt(receipt, record)
        return 4
    job = found[0]
    record.update(job_id=job, status_samples=[])
    status = _wait_for_job(hunt_dir, job, record, receipt, args.job_timeout_s, args.poll_s)
    record["job_status"] = (
        "SUPERVISION_TIMEOUT" if status.pop("supervision_timeout", False) else status.get("status")
    )
    record["job_error"] = status.get("error")
    if status.get("status") in {"COMPLETE", "PARTIAL"}:
        _turn(
            f"Show me the top 10 leads for hunt {job} using its exact job id.",
            key,
            args.model,
            record,
        )
        _turn(
            f"Show me case 1 for hunt {job} using its exact job id: "
            "what it pivoted on and its evidence picture.",
            key,
            args.model,
            record,
        )
    record["finished"] = time.time()
    _write_receipt(receipt, record)
    elapsed = record["finished"] - record["started"]
    print(f"{args.index}: job {job} {record['job_status']} in {elapsed:.0f}s")
    return _exit_code(record["job_status"], record.get("coverage_complete"))


if __name__ == "__main__":
    sys.exit(main())
