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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--index", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model", default="security-reviewer")
    args = ap.parse_args()
    key = os.environ["OWUI_API_KEY"]
    args.out.mkdir(parents=True, exist_ok=True)
    rec: dict = {"index": args.index, "started": time.time(), "transcripts": []}

    def turn(prompt: str) -> str:
        answer = ask(prompt, key, args.model)
        rec["transcripts"].append({"prompt": prompt, "answer": answer, "at": time.time()})
        print(f">>> {prompt}\n{answer}\n", flush=True)
        return answer

    job = None
    for attempt in range(3):
        a = turn(f"Start a hunt over the {args.index} environment and give me the job id.")
        if m := re.search(r"hunt-[0-9a-f]{12}", a):
            job = m.group(0)
            break
    if job is None:
        rec["error"] = "model never returned a job id"
        (args.out / f"{args.index}.json").write_text(json.dumps(rec, indent=1))
        return 1
    rec["job_id"] = job
    while True:
        try:
            st = json.loads((HUNTS / f"{job}.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            st = {"status": "PENDING"}
        if st.get("status") in ("COMPLETE", "FAILED"):
            break
        time.sleep(30)
    rec["job_status"] = st.get("status")
    rec["job_error"] = st.get("error")
    if st.get("status") == "COMPLETE":
        turn(f"Show me the top 10 leads for hunt {job}.")
        turn(f"Show me case 1 for hunt {job}: what it pivoted on and its evidence picture.")
    rec["finished"] = time.time()
    (args.out / f"{args.index}.json").write_text(json.dumps(rec, indent=1))
    print(f"{args.index}: job {job} {rec['job_status']} in {rec['finished'] - rec['started']:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
