"""PROVE_THEN_SCALE_V1 §P4 — the twenty-call cache measurement over CIP-007-6.

Twenty sequential map readings, shared body first, on the settled seat
(gemma4). ``prompt_eval_duration`` per call is the cache signal —
``prompt_eval_count`` reports total prompt length and cannot answer this (the
last campaign established that the hard way; see WINDOW_AND_SEAT_V1 §P3.1).
This run is also the real CIP-007-6 sweep: determinations are written at
``machine_determined`` with provenance, and every call retains its receipt.

Usage: uv run python scripts/prove_then_scale/p4_cache_sweep.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core import sweep  # noqa: E402
from portal.modules.compliance.core.repository import Repository  # noqa: E402

ART = REPO_ROOT / "reports" / "compliance" / "prove_then_scale" / "p4_cip007_cache.json"

SEAT = "gemma4:26b-a4b-it-q4_K_M-ctx32k"


def main() -> int:
    repo = Repository()
    try:
        summary = sweep.sweep_standard(repo, "CIP-007-6", model=SEAT, write=True)
        ART.write_text(json.dumps(summary, indent=2, default=str))
        print(
            f"\nCIP-007-6: {summary['n_requirements']} requirements, "
            f"total {summary['total_wall_s']} s "
            f"({summary['wall_per_requirement_s']} s/requirement)"
        )
        print(
            f"cache: first-call prefill {summary['first_call_prefill_s']} s, "
            f"rest mean {summary['rest_mean_prefill_s']} s, "
            f"collapse x{summary['cache_collapse_ratio']}"
        )
        print(
            f"determinations: {summary['determined']} determined, "
            f"{summary['corroborated']} corroborated, {summary['rejected']} rejected"
        )
    finally:
        repo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
