"""Replay the EXACT live packet from a stored trace, varying only `think`.

The reconstructed-packet proof was not faithful: on a hand-built two-candidate
packet all three seats read L22 correctly, yet in the live run granite and
mistral both voted DIFFERENT. So the flip is caused by something in the real
packet, and the only honest instrument is the real packet.

Every trace record stores `system` and `input` verbatim plus their sha256, so
this replays byte-identical bytes and can prove it did.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/chris/projects/portal-5")

from portal.modules.compliance.core.obligation_alignment import (  # noqa: E402
    _response_contract,
)
from portal.modules.compliance.core.reading_transport import chat  # noqa: E402


def summarise(content: str) -> str:
    try:
        obj = json.loads(content)
    except json.JSONDecodeError as exc:
        return f"JSON PARSE FAILED: {exc}; head={content[:120]!r}"
    bits = []
    for rec in obj.get("records", []):
        cid = str(rec.get("candidate_id", "?"))[:8]
        binds = [
            (
                b.get("governing_quantity", {}).get("value"),
                b.get("internal_quantity", {}).get("value"),
            )
            for b in rec.get("constraint_bindings", [])
        ]
        bits.append(f"{cid}={rec.get('relation')}{binds if binds else ''}")
    if "determination" in obj:
        bits.append(f"determination={obj['determination']} cites={obj.get('cited_refs')}")
    return "  ".join(bits) if bits else content[:160]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True)
    ap.add_argument("--think", default="false,low,medium")
    ap.add_argument("--model", default="")
    ap.add_argument("--budget", type=int, default=8192)
    args = ap.parse_args()

    rec = json.loads(Path(args.trace).read_text())
    system, user = rec["system"], rec["input"]
    model = args.model or rec["model"]

    sys_ok = hashlib.sha256(system.encode()).hexdigest() == rec["system_sha256"]
    inp_ok = hashlib.sha256(user.encode()).hexdigest() == rec["input_sha256"]
    print(f"trace   {args.trace}")
    print(f"stage   {rec['stage']}   recorded model {rec['model']}")
    print(
        f"bytes   system {len(system)} ({'sha OK' if sys_ok else 'SHA MISMATCH'})  "
        f"input {len(user)} ({'sha OK' if inp_ok else 'SHA MISMATCH'})"
    )
    print(f"replay  {model}")
    print(f"\nRECORDED  {rec['elapsed_seconds']:.1f}s  {summarise(rec['response'])}\n")
    if not (sys_ok and inp_ok):
        print("refusing to replay: stored bytes do not match their own digest")
        return 1

    fmt = _response_contract("clause_alignment") if rec["stage"] == "alignment" else "json"
    for token in [t.strip() for t in args.think.split(",") if t.strip()]:
        think: bool | str = {"false": False, "true": True}.get(token, token)
        started = time.time()
        try:
            result = chat(model, system, user, budget=args.budget, fmt=fmt, think=think)
        except Exception as exc:  # noqa: BLE001 - report, never mask
            print(f"  think:{token:<7} ERROR {exc!r}", flush=True)
            continue
        print(
            f"  think:{token:<7} {time.time() - started:6.1f}s "
            f"think={len(result.thinking):6d}ch eval={result.get('eval_count', 0):5d}  "
            f"{summarise(result.content)}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
