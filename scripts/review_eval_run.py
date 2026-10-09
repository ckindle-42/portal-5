"""Run one pre-registered review arm on a certified real slice.

Slices without a same-size, separate-day benign interval produce a validated exclusion
report and never enter the product path. A future runner extension can execute admitted
slices only after a calibrated Reference is available from the same recorded corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

import portal.modules.security.core.review.embedding as embedding
import portal.modules.security.core.review.service as service
from portal.modules.security.core.review_eval import arms, report, selftest, stamp

DEFAULT_TRUTH = Path("reports/review_eval/bots_truth_manifest.json")
DEFAULT_EMBEDDER_URL = "http://127.0.0.1:8946"
DEFAULT_MODEL_URL = "http://127.0.0.1:11434"
EMBEDDING_DIM = 768
EMBEDDING_TASK = "sentence similarity"
EMBEDDING_ROLE = "query"


def _get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        body = json.loads(response.read())
    if not isinstance(body, dict):
        raise ValueError(f"expected an object from {url}")
    return body


def _slice_record(manifest: dict[str, Any], slice_name: str) -> dict[str, Any]:
    indexes = manifest.get("benign_slice_derivation", {}).get("indexes", {})
    record = indexes.get(slice_name)
    if not isinstance(record, dict):
        raise ValueError(f"unknown slice {slice_name!r}; expected one of {tuple(indexes)}")
    return record


def run_exclusion_report(*, arm_name: str, slice_name: str, out: Path, manifest_path: Path) -> Path:
    """Stamp a no-run result for an index whose paired slice failed pre-registration."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("truth manifest must be a JSON object")
    slice_row = _slice_record(manifest, slice_name)
    if slice_row.get("status") != "excluded":
        raise ValueError(
            f"slice {slice_name!r} is not excluded; an admitted slice needs a fitted reference"
        )

    arm = arms.get_arm(arm_name)
    embedder_model = stamp.fetch_embedder_identity(_get_json, DEFAULT_EMBEDDER_URL)
    if not embedder_model:
        raise ValueError("embedding service /ready did not report a model")
    embedder_id = (
        f"{embedder_model};dim={EMBEDDING_DIM};task={EMBEDDING_TASK};role={EMBEDDING_ROLE}"
    )
    models = stamp.fetch_model_digests(_get_json, DEFAULT_MODEL_URL, [])
    slice_digest = hashlib.sha256(
        json.dumps(slice_row, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    config = {
        "arm": arm_name,
        "arm_config": repr(arm.config),
        "slice": slice_name,
        "slice_receipt": slice_row,
    }
    run_stamp = stamp.build_stamp(
        repo=Path(__file__).resolve().parents[1],
        embedder_id=embedder_id,
        model_digests=models,
        config=config,
        corpus_snapshot=f"real:{slice_name}:{slice_digest}",
        policy=arm_name,
    )
    # The self-test is deliberately the first scoring operation bound to this stamp.
    known_answer = selftest.run_selftest(stamp_digest=run_stamp.digest)
    rows = [
        {
            "slice": slice_name,
            "eligible": False,
            "status": "excluded",
            "reason": str(slice_row.get("reason") or "no usable paired interval"),
        }
    ]
    metric = report.MetricRow(
        name="slice_eligibility",
        value=0.0,
        n=1,
        denominator=1,
        can_fail="fails when the pre-registered index has no usable attack and benign pair",
    )
    document = report.build_report(
        stamp=run_stamp,
        selftest=known_answer,
        metrics=[metric],
        rows=rows,
        recompute={
            "slice_eligibility": lambda raw: sum(bool(row["eligible"]) for row in raw) / len(raw)
        },
        extra={
            "arm": arm_name,
            "slice": slice_name,
            "executed": False,
            "status": "INCONCLUSIVE",
            "exclusion": slice_row,
            "truth_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "ledger": {
                "status": "not_measured",
                "reason": "the paired slice was excluded before either arm ran",
            },
            "by_class": {},
            "policy": arm_name,
            "workload_B": None,
            "unavailable_metrics": [
                "recall_at_B",
                "false_raise_per_1000_benign_units",
                "concerns_per_1000_units",
                "stage_examined_resolved",
            ],
            "product_service": service.run_review.__module__ + ".run_review",
            "embedder_adapter": embedding.PlatformEmbedder.__module__,
        },
    )
    output_directory = out if out.name == run_stamp.digest else out / run_stamp.digest
    report_path, _ = report.write_report(document, output_directory, f"{slice_name}_{arm_name}")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=tuple(arms.ARMS), required=True)
    parser.add_argument("--slice", dest="slice_name", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--truth-manifest", type=Path, default=DEFAULT_TRUTH)
    args = parser.parse_args()
    path = run_exclusion_report(
        arm_name=args.arm,
        slice_name=args.slice_name,
        out=args.out,
        manifest_path=args.truth_manifest,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
