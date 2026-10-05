"""DATA_TRUTH DD4 — one real turn through the deployed pipeline with the DD3
payload at the largest document set (CIP-007).

Re-measures, per turn: wall time, prompt tokens (final hop), the payload's own
token estimate, and the derived persona/tools reserve =
prompt_tokens − payload_estimate — the number the payload's window block
prices with (PERSONA_TOOLS_RESERVE_TOKENS). The turn is a REAL workspace turn:
compliance-reading's persona and tool list ride along exactly as served.

One heavy job: run alone; the Ollama 128k copy must not be resident.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import httpx  # noqa: E402
from compliance_acceptance import WorkspaceThread, router_base_url  # noqa: E402

from portal.modules.compliance.core import dual_document  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402
from portal.modules.compliance.core.runtime_config import (  # noqa: E402
    reading_context_limits,
    reading_route_ceiling,
)
from scripts.compliance.truth import _local  # noqa: E402

QUESTION = (
    "For CIP-007-6 R2, what does our change management procedure require for "
    "emergency changes, and where do we exceed the standard's baseline?"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--ref", default="CIP-007-6 R2")
    args = parser.parse_args()
    _local.refusal(args.out_dir, "--out-dir")

    repo = Repository()
    try:
        limits = reading_context_limits()
        ceiling = reading_route_ceiling()
        t0 = time.monotonic()
        payload = dual_document.build(
            repo,
            requirement_ref=args.ref,
            context_limit=min(limits["context_limit"], ceiling or limits["context_limit"]),
            predict_limit=limits["predict_limit"],
            served_ceiling=ceiling,
        )
        build_s = round(time.monotonic() - t0, 2)
    finally:
        repo.close()
    if not payload.get("resolved"):
        print(json.dumps({"error": payload.get("error")}, indent=1))
        return 1

    question = f"{payload['text']}\n\nQuestion: {QUESTION}"
    router = router_base_url()
    record: dict[str, Any]
    with httpx.Client(timeout=30.0) as session:
        thread = WorkspaceThread(session, "compliance-reading", router)
        record = thread.turn(question, timeout=1800.0)

    prompt_tokens = record.get("prompt_tokens_high_water") or record.get("prompt_tokens_final_hop")
    payload_tokens = payload["window"]["estimated_tokens"]
    receipt = {
        "measurement": "dd4_payload_turn",
        "ref": args.ref,
        "build_s": build_s,
        "payload_tokens_estimate": payload_tokens,
        "payload_window": payload["window"],
        "documents_included": len(payload["documents_included"]),
        "documents_deferred": [d["title"] for d in payload["documents_deferred"]],
        "question_chars": len(question),
        "prompt_tokens": prompt_tokens,
        "wall_s": record.get("wall_s"),
        "finish_reason": record.get("finish_reason"),
        "served_model": record.get("served_model"),
        "answer_chars": len(str(record.get("answer") or "")),
        "answer_excerpt": str(record.get("answer") or "")[:600],
        "persona_tools_reserve_derived": (
            prompt_tokens - payload_tokens if prompt_tokens else None
        ),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / "dd4_payload_turn.json"
    out.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k != "answer_excerpt"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
