"""The window census (TASK_COMPLIANCE_PIPELINE_ALIGNMENT_V1 §P2).

Renders every register node's sweep material and prices it against the
windows in play on the pipeline path:

* 32,768 — the compliance-reading seat's declared context_limit (the window
  the pipeline serves; request-time num_ctx is dropped);
* 65,536 — the overflow window an overflow seat would have to hold.

Priced at the MEASURED bytes-per-token for this seat on this corpus
(module_complete/p0_5/seat_bytes_per_token.json, median 3.28), with the sweep's
conservative 3.3 constant reported alongside — a guard that under-counts tokens
is the one direction a truncation guard may never err.

Local computation only: no model call. This says how big the oversized-material
problem is before anything is built.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from portal.modules.compliance.core.repository import Repository

OUT_DEFAULT = Path("reports/compliance/pipeline_alignment/p2/window_census.json")
MEASURED_BPT_ARTIFACT = Path("reports/compliance/module_complete/p0_5/seat_bytes_per_token.json")

#: The sweep's mapping-call answer budget (sweep.map_read default).
ANSWER_BUDGET = 3072

#: The windows priced.
WINDOWS = {"seat_32768": 32768, "overflow_65536": 65536}


def _measured_bytes_per_token() -> float:
    try:
        data = json.loads(MEASURED_BPT_ARTIFACT.read_text())
        return float(data["median_bytes_per_token"])
    except Exception:  # noqa: BLE001 — fall back to the sweep constant, never crash
        return 3.3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()

    from portal.modules.compliance.core import reading_material
    from portal.modules.compliance.core.cip_register import Register
    from portal.modules.compliance.core.sweep import (
        SEAT_BYTES_PER_TOKEN,
        load_mapping_prompt,
        sweep_order,
        window_fit,
    )

    bpt_measured = _measured_bytes_per_token()
    prompt_body, prompt_version, prompt_sha = load_mapping_prompt()
    repo = Repository()
    refs = sweep_order(repo)
    reg = Register.load()
    by_revision: dict[str, list[str]] = {}
    for node in reg.nodes:
        by_revision.setdefault(node.id.split(" ")[0], []).append(node.id)

    rows: list[dict[str, Any]] = []
    started = time.time()
    for ref in refs:
        revision = ref.split(" ")[0]
        fixed = reading_material.fixed_body(repo, revision)
        fixed_payload = None if "error" in fixed else fixed
        material = reading_material.render(repo, ref, question=prompt_body, fixed=fixed_payload)
        if "error" in material:
            rows.append({"ref": ref, "error": material["error"]})
            continue
        prompt_bytes = len(material["text"].encode())
        row: dict[str, Any] = {
            "ref": ref,
            "revision": revision,
            "prompt_bytes": prompt_bytes,
        }
        for label, num_ctx in WINDOWS.items():
            fit = window_fit(prompt_bytes, num_ctx, ANSWER_BUDGET, bytes_per_token=bpt_measured)
            row[label] = {
                "fits": fit["fits"],
                "estimated_tokens": fit["estimated_tokens"],
                "available_tokens": fit["available_tokens"],
            }
            fit_const = window_fit(
                prompt_bytes, num_ctx, ANSWER_BUDGET, bytes_per_token=SEAT_BYTES_PER_TOKEN
            )
            row[label]["fits_at_sweep_constant"] = fit_const["fits"]
        rows.append(row)
    repo.close()

    def _count(pred: Any) -> int:
        return sum(1 for r in rows if "error" not in r and pred(r))

    n_ok = sum(1 for r in rows if "error" not in r)
    document = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prompt_version": prompt_version,
        "prompt_sha": prompt_sha,
        "bytes_per_token_measured": bpt_measured,
        "bytes_per_token_sweep_constant": SEAT_BYTES_PER_TOKEN,
        "answer_budget": ANSWER_BUDGET,
        "windows": WINDOWS,
        "n_nodes": len(rows),
        "n_rendered": n_ok,
        "n_errors": len(rows) - n_ok,
        "over_seat_window": _count(lambda r: not r["seat_32768"]["fits"]),
        "over_seat_window_at_sweep_constant": _count(
            lambda r: not r["seat_32768"]["fits_at_sweep_constant"]
        ),
        "over_overflow_window": _count(lambda r: not r["overflow_65536"]["fits"]),
        "rows": rows,
        "elapsed_s": round(time.time() - started, 1),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2))
    print(
        f"census: {n_ok}/{len(rows)} nodes rendered; "
        f"{document['over_seat_window']} exceed the 32k seat window "
        f"({document['over_seat_window_at_sweep_constant']} at the sweep constant), "
        f"{document['over_overflow_window']} exceed the 65k overflow window"
    )
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
