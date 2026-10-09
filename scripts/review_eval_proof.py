#!/usr/bin/env python3
"""Run the T6 real-corpus proof on fixed, stratified, read-only replay windows.

The only product call is ``ReviewRuntime.start``. The shipped legacy funnel receives the exact
same cached window as the comparison control. All persisted proof receipts are aggregate-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import signal
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY  # noqa: E402
from portal.modules.security.core.review.constants import PROOF_WORKLOAD_B  # noqa: E402
from portal.modules.security.core.review.contracts import ReviewResult, to_plain  # noqa: E402
from portal.modules.security.core.review.embedding import PlatformEmbedder  # noqa: E402
from portal.modules.security.core.review.funnel import FunnelPolicy  # noqa: E402
from portal.modules.security.core.review.intake import (  # noqa: E402
    build_window_units,
    event_id_for,
)
from portal.modules.security.core.review.knowledge import AnchorIndex, Embedder  # noqa: E402
from portal.modules.security.core.review.pipeline import (  # noqa: E402
    Reference,
    ReviewConfig,
    build_reference,
)
from portal.modules.security.core.review.runs import RunStatus  # noqa: E402
from portal.modules.security.core.review.service import ReviewRequest, ReviewRuntime  # noqa: E402
from portal.modules.security.core.review.store import ReviewStore  # noqa: E402
from portal.modules.security.core.review.verdicts import cards_from_store  # noqa: E402
from portal.modules.security.core.review.window import (  # noqa: E402
    InMemoryWindowSource,
    SourceSpec,
    SplunkWindowSource,
    WindowBatch,
)
from portal.modules.security.core.review_eval import claims, report, selftest, stamp  # noqa: E402
from portal.modules.security.core.review_eval.captures import validate_capture  # noqa: E402
from portal.modules.security.core.review_eval.proof import (  # noqa: E402
    ProofRunStore,
    window_digest,
)
from portal.modules.security.core.review_eval.truth import (  # noqa: E402
    TruthItem,
    _matching_entities,
    derive_capture_truth,
)

CAPTURE_DATA_DIR = Path(
    "/Users/chris/projects/portal-5/portal/modules/security/core/results/captures"
)

OUTPUT = REPO / "reports" / "review_eval" / "e2e"
PRIVATE_OUTPUT = Path("/Users/chris/AI_Output/review/t6_proof")
TRUTH_MANIFEST = REPO / "reports" / "review_eval" / "bots_truth_manifest.json"
CAPTURE_MANIFEST = REPO / "reports" / "review_eval" / "capture_admission_manifest.json"
CALIBRATION_SLICE = Path("/Users/chris/AI_Output/review/calibration_slice.json")
DEFAULT_BOT_POLICY = FunnelPolicy(
    alpha_unusual=0.2,
    alpha_similar=0.2,
    levels=("L2_ENTITY", "L3_CHAIN"),
)
DEFAULT_CONFIG = ReviewConfig(policy=DEFAULT_BOT_POLICY)


@dataclass(frozen=True)
class ProofSlice:
    window_id: str
    environment: str
    index: str
    sourcetype: str
    start: float
    end: float
    calibration_start: float
    calibration_end: float

    @property
    def source(self) -> SourceSpec:
        return SourceSpec(self.index, self.sourcetype)


PLAN: tuple[ProofSlice, ...] = (
    ProofSlice(
        "botsv1_selected_http",
        "botsv1",
        "botsv1",
        "stream:http",
        1470865005.625,
        1470865065.625,
        1470951405.625,
        1470951465.625,
    ),
    ProofSlice(
        "botsv1_unselected_application",
        "botsv1",
        "botsv1",
        "WinEventLog:Application",
        1470013200.0,
        1470013800.0,
        1470099600.0,
        1470100200.0,
    ),
    ProofSlice(
        "botsv2_selected_dns",
        "botsv2",
        "botsv2",
        "stream:dns",
        1501784416.022,
        1501784576.955,
        1501870816.022,
        1501870976.955,
    ),
    ProofSlice(
        "botsv2_unselected_registry",
        "botsv2",
        "botsv2",
        "winregistry",
        1501549200.0,
        1501549260.0,
        1501635600.0,
        1501635660.0,
    ),
    ProofSlice(
        "botsv3_selected_http",
        "botsv3",
        "botsv3",
        "stream:http",
        1534759200.0,
        1534759800.0,
        1534845600.0,
        1534846200.0,
    ),
    ProofSlice(
        "botsv3_unselected_syslog",
        "botsv3",
        "botsv3",
        "syslog",
        1534759200.0,
        1534759260.0,
        1534845600.0,
        1534845660.0,
    ),
)


class FixedBatchSource:
    """Serve a previously fetched, content-hashed live window to the public runtime API."""

    def __init__(self, batch: WindowBatch) -> None:
        self.batch = batch

    def fetch(self, sources: Sequence[SourceSpec], start: float, end: float) -> WindowBatch:
        requested = {source.source_id for source in sources}
        present = set(self.batch.records_by_source)
        if (
            requested != present
            or self.batch.receipts
            and (self.batch.receipts[0].start != start or self.batch.receipts[-1].end != end)
        ):
            raise ValueError("cached proof window does not match the ReviewRuntime request")
        return self.batch


class BlockingFixedBatchSource(FixedBatchSource):
    """Hold a real cached batch inside the live worker so SIGKILL lands mid-run."""

    def __init__(self, batch: WindowBatch, entered: Any, release: Any) -> None:
        super().__init__(batch)
        self.entered = entered
        self.release = release

    def fetch(self, sources: Sequence[SourceSpec], start: float, end: float) -> WindowBatch:
        batch = super().fetch(sources, start, end)
        self.entered.set()
        if not self.release.wait(timeout=3600.0):
            raise TimeoutError("T6 recovery drill release was not signalled")
        return batch


def _recovery_worker(
    batch: WindowBatch,
    sources: Sequence[SourceSpec],
    start: float,
    end: float,
    environment: str,
    reference: Reference,
    embedder: Embedder,
    index: AnchorIndex | None,
    runtime_dir: Path,
    entered: Any,
    release: Any,
    run_ids: Any,
) -> None:
    runtime = ReviewRuntime(
        source=BlockingFixedBatchSource(batch, entered, release),
        embedder=embedder,
        index=index,
        reference=reference,
        config=DEFAULT_CONFIG,
        environment_id=environment,
        review_dir=runtime_dir,
    )
    request = ReviewRequest(sources, start, end, environment, DEFAULT_CONFIG)
    run_id = runtime.start(request)
    run_ids.put(run_id)
    while True:
        record = runtime.status(run_id)
        if record is None or record.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
            break
        time.sleep(0.1)
    runtime.close()


def _embedder(dim: int = 768) -> Embedder:
    from portal.platform.embedding.contract import Role, Task

    return PlatformEmbedder(task=Task.SENTENCE_SIMILARITY, dim=dim, role=Role.QUERY)


def _index(embedder: Embedder) -> AnchorIndex | None:
    path = Path("/Users/chris/AI_Output/review/review.sqlite3")
    if not path.is_file():
        return None
    store = ReviewStore(path)
    try:
        cards = cards_from_store(store)
    finally:
        store.close()
    return AnchorIndex.build(cards, embedder) if cards else None


def _load_lab_split() -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    raw = json.loads(CALIBRATION_SLICE.read_text(encoding="utf-8"))
    calibration: dict[str, list[dict[str, Any]]] = {}
    test: dict[str, list[dict[str, Any]]] = {}
    for source, source_records in raw.items():
        calibration[source] = []
        test[source] = []
        for record in source_records:
            day = datetime.fromtimestamp(float(record["_time"]), UTC).date().isoformat()
            if day == "2026-06-11":
                calibration[source].append(record)
            elif day == "2026-06-16":
                test[source].append(record)
            else:
                raise ValueError(f"unexpected portal5_lab calibration-slice date {day}")
    if not calibration or not test or sum(map(len, test.values())) == 0:
        raise ValueError("the held-out portal5_lab day split is empty")
    return calibration, test


def _event_ids(batch: WindowBatch) -> list[str]:
    return sorted(
        event_id_for(source_id, row)
        for source_id, records in batch.records_by_source.items()
        for row in records
    )


def _batch_from_records(records: Mapping[str, Sequence[Mapping[str, Any]]]) -> WindowBatch:
    return InMemoryWindowSource(records, partition_seconds=86_400).fetch(
        [SourceSpec(*source.split(":", 1)) for source in records],
        min(float(row["_time"]) for rows in records.values() for row in rows),
        max(float(row["_time"]) for rows in records.values() for row in rows) + 1.0,
    )


def _small_window_batch(
    batch: WindowBatch, source_id: str, *, max_events: int = 20
) -> tuple[WindowBatch, float, float]:
    rows = sorted(batch.records_by_source.get(source_id, []), key=lambda row: float(row["_time"]))[
        :max_events
    ]
    if not rows:
        raise ValueError(f"recovery source {source_id} has no records")
    start = min(float(row["_time"]) for row in rows)
    end = max(float(row["_time"]) for row in rows) + 1.0
    return _batch_from_records({source_id: rows}), start, end


def _safe_result(result: Mapping[str, Any]) -> dict[str, Any]:
    concerns: list[dict[str, Any]] = []
    for group in ("concerns", "suppressed"):
        for row in result.get(group, []):
            if not isinstance(row, Mapping):
                continue
            concerns.append(
                {
                    "group": group,
                    "unit_id": str(row.get("unit_id") or ""),
                    "outcome": str(row.get("outcome") or ""),
                    "priority_p": float(row.get("priority_p") or 0.0),
                    "evidence_event_ids": sorted(
                        str(item.get("event_id"))
                        for item in row.get("evidence", [])
                        if isinstance(item, Mapping) and item.get("event_id")
                    ),
                    "absence_receipt": bool(row.get("absence")),
                    "judge_verdict": str((row.get("judge") or {}).get("verdict") or "")
                    if isinstance(row.get("judge"), Mapping)
                    else "",
                    "judge_degraded": str((row.get("judge") or {}).get("degraded") or "")
                    if isinstance(row.get("judge"), Mapping)
                    else "",
                    "judge_claim_count": len((row.get("judge") or {}).get("claims") or [])
                    if isinstance(row.get("judge"), Mapping)
                    and isinstance((row.get("judge") or {}).get("claims"), list)
                    else 0,
                }
            )
    return {
        "concerns": concerns,
        "receipts": list(result.get("receipts") or []),
        "degraded": list(result.get("degraded") or []),
        "fingerprint": dict(result.get("fingerprint") or {}),
    }


def _safe_review_result(result: ReviewResult) -> dict[str, Any]:
    plain = to_plain(result)
    if not isinstance(plain, Mapping):
        raise TypeError("ReviewRuntime result is not an object")
    return _safe_result(plain)


def _run_review_runtime(
    *,
    batch: WindowBatch,
    sources: Sequence[SourceSpec],
    start: float,
    end: float,
    environment: str,
    reference: Reference,
    embedder: Embedder,
    index: AnchorIndex | None,
    runtime_dir: Path,
    judge: Any = None,
) -> tuple[str, dict[str, Any], float]:
    runtime = ReviewRuntime(
        source=FixedBatchSource(batch),
        embedder=embedder,
        index=index,
        reference=reference,
        config=DEFAULT_CONFIG,
        environment_id=environment,
        review_dir=runtime_dir,
        judge=judge,
    )
    request = ReviewRequest(sources, start, end, environment, DEFAULT_CONFIG)
    started = time.monotonic()
    try:
        run_id = runtime.start(request)
        deadline = time.monotonic() + 3600.0
        record = runtime.status(run_id)
        while record is None or record.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
            if time.monotonic() >= deadline:
                runtime.cancel(run_id)
                raise TimeoutError(f"ReviewRuntime run {run_id} exceeded one hour")
            time.sleep(0.1)
            record = runtime.status(run_id)
        if record.status != RunStatus.COMPLETE:
            raise RuntimeError(
                f"ReviewRuntime run {run_id} ended {record.status.value}: {record.error}"
            )
        saved = runtime.result(run_id)
        if not isinstance(saved, Mapping):
            raise TypeError(f"ReviewRuntime run {run_id} has no result object")
        return run_id, _safe_result(saved), time.monotonic() - started
    finally:
        runtime.close()


def _runtime_metrics(summary: Mapping[str, Any]) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    outcomes: Counter[str] = Counter()
    groups: Counter[str] = Counter()
    for row in summary.get("concerns", []):
        if not isinstance(row, Mapping):
            continue
        group = str(row.get("group") or "")
        outcome = str(row.get("outcome") or "")
        groups[group] += 1
        outcomes[outcome] += 1
        decisions.append(
            {
                "group": group,
                "unit_id_sha256": hashlib.sha256(
                    str(row.get("unit_id") or "").encode()
                ).hexdigest(),
                "outcome": outcome,
                "priority_p": round(float(row.get("priority_p") or 0.0), 12),
                "evidence_count": len(row.get("evidence_event_ids") or []),
                "absence_receipt": bool(row.get("absence_receipt")),
            }
        )
    receipts = [
        {
            "name": str(row.get("name") or ""),
            "examined": int(row.get("examined") or 0),
            "resolved": int(row.get("resolved") or 0),
        }
        for row in summary.get("receipts", [])
        if isinstance(row, Mapping)
    ]
    payload = {
        "decisions": sorted(decisions, key=lambda row: str(row["unit_id_sha256"])),
        "receipts": sorted(receipts, key=lambda row: str(row["name"])),
    }
    return {
        "concern_count": groups["concerns"],
        "suppressed_count": groups["suppressed"],
        "outcome_counts": dict(sorted(outcomes.items())),
        "decision_receipt_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _wait_for_runtime(runtime: ReviewRuntime, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 3600.0
    record = runtime.status(run_id)
    while record is None or record.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
        if time.monotonic() >= deadline:
            runtime.cancel(run_id)
            raise TimeoutError(f"ReviewRuntime run {run_id} exceeded one hour")
        time.sleep(0.1)
        record = runtime.status(run_id)
    if record.status != RunStatus.COMPLETE:
        raise RuntimeError(
            f"ReviewRuntime run {run_id} ended {record.status.value}: {record.error}"
        )
    saved = runtime.result(run_id)
    if not isinstance(saved, Mapping):
        raise TypeError(f"ReviewRuntime run {run_id} has no result object")
    return _safe_result(saved)


def _safe_legacy_result(result: ReviewResult) -> dict[str, Any]:
    return _safe_review_result(result)


def _run_legacy(
    records: Mapping[str, Sequence[Mapping[str, Any]]], env: str
) -> tuple[str, dict[str, Any]]:
    from portal.modules.security.core.review_eval.legacy_arm import run_legacy_funnel

    result = run_legacy_funnel(records, environment_id=env)
    return result.run_id, _safe_legacy_result(result)


def _digest_batch(batch: WindowBatch, proof_slice: ProofSlice, manifest_digest: str) -> str:
    return window_digest(
        window_id=proof_slice.window_id,
        environment=proof_slice.environment,
        sources=[proof_slice.source.source_id],
        start=proof_slice.start,
        end=proof_slice.end,
        event_ids=_event_ids(batch),
        corpus_stamp=f"real:{proof_slice.index}:{manifest_digest}",
        arm="review_d0",
    )


def _control_digest(window_hash: str) -> str:
    return hashlib.sha256(f"{window_hash}|legacy_funnel".encode()).hexdigest()


def _run_slice(
    *,
    proof_slice: ProofSlice,
    batch: WindowBatch,
    reference: Reference,
    embedder: Embedder,
    index: AnchorIndex | None,
    runtime_root: Path,
    receipts: ProofRunStore,
    manifest_digest: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    digest = _digest_batch(batch, proof_slice, manifest_digest)
    saved_review = receipts.completed(proof_slice.window_id, digest, "review_d0")
    if saved_review is None:
        run_id, review_summary, elapsed = _run_review_runtime(
            batch=batch,
            sources=[proof_slice.source],
            start=proof_slice.start,
            end=proof_slice.end,
            environment=proof_slice.environment,
            reference=reference,
            embedder=embedder,
            index=index,
            runtime_dir=runtime_root / proof_slice.window_id / "review_d0",
        )
        review_summary["duration_seconds"] = elapsed
        saved_review = receipts.record_complete(
            window_id=proof_slice.window_id,
            window_hash=digest,
            arm="review_d0",
            runtime_run_id=run_id,
            summary=review_summary,
        )
    review_summary = dict(saved_review.summary)

    control_hash = _control_digest(digest)
    saved_control = receipts.completed(proof_slice.window_id, control_hash, "legacy_funnel")
    if saved_control is None:
        run_id, control_summary = _run_legacy(batch.records_by_source, proof_slice.environment)
        saved_control = receipts.record_complete(
            window_id=proof_slice.window_id,
            window_hash=control_hash,
            arm="legacy_funnel",
            runtime_run_id=run_id,
            summary=control_summary,
        )
    control_summary = dict(saved_control.summary)
    metadata = {
        "window_id": proof_slice.window_id,
        "window_hash": digest,
        "control_hash": control_hash,
        "review_runtime_run_id": saved_review.runtime_run_id,
        "legacy_run_id": saved_control.runtime_run_id,
        "expected_events": batch.expected,
        "fetched_events": batch.fetched,
        "corpus_snapshot": f"real:{proof_slice.index}:{manifest_digest}",
        "degraded": list(batch.degraded),
    }
    return review_summary, control_summary, metadata


def _recovery_drill(  # noqa: PLR0915 -- one durable restart drill boundary.
    *,
    test_batches: Mapping[str, WindowBatch],
    reference: Reference,
    embedder: Embedder,
    index: AnchorIndex | None,
    runtime_root: Path,
    receipts: ProofRunStore,
    manifest_digest: str,
) -> dict[str, Any]:
    proof_slice = next(item for item in PLAN if item.window_id == "botsv2_selected_dns")
    batch, start, end = _small_window_batch(
        test_batches[proof_slice.window_id], proof_slice.source.source_id
    )
    window_id = "t6_recovery_botsv2_dns_first_20"
    recovery_slice = ProofSlice(
        window_id,
        proof_slice.environment,
        proof_slice.index,
        proof_slice.sourcetype,
        start,
        end,
        start,
        end,
    )
    window_hash = _digest_batch(batch, recovery_slice, manifest_digest)
    recovery_runtime_dir = runtime_root / window_id / "review_d0"
    context = mp.get_context("fork")
    entered = context.Event()
    release = context.Event()
    run_ids = context.Queue()
    process = context.Process(
        target=_recovery_worker,
        args=(
            batch,
            [proof_slice.source],
            start,
            end,
            proof_slice.environment,
            reference,
            embedder,
            index,
            recovery_runtime_dir,
            entered,
            release,
            run_ids,
        ),
    )
    process.start()
    try:
        interrupted_run_id = str(run_ids.get(timeout=60.0))
        if not entered.wait(timeout=60.0):
            raise TimeoutError("recovery worker never entered the live ReviewRuntime fetch")
        if not process.is_alive() or process.pid is None:
            raise RuntimeError("recovery worker exited before the SIGKILL drill")
        os.kill(process.pid, signal.SIGKILL)
        process.join(timeout=30.0)
        if process.is_alive():
            raise TimeoutError("SIGKILL worker did not exit within 30 seconds")
        if process.exitcode != -signal.SIGKILL:
            raise RuntimeError(f"worker exited with unexpected status {process.exitcode}")
    finally:
        if process.is_alive() and process.pid is not None:
            os.kill(process.pid, signal.SIGKILL)
            process.join(timeout=30.0)

    runtime = ReviewRuntime(
        source=FixedBatchSource(batch),
        embedder=embedder,
        index=index,
        reference=reference,
        config=DEFAULT_CONFIG,
        environment_id=proof_slice.environment,
        review_dir=recovery_runtime_dir,
    )
    request = ReviewRequest(
        [proof_slice.source], start, end, proof_slice.environment, DEFAULT_CONFIG
    )
    try:
        interrupted = runtime.status(interrupted_run_id)
        interrupted_ok = (
            runtime.interrupted_at_startup >= 1
            and interrupted is not None
            and interrupted.status == RunStatus.INTERRUPTED
        )
        if not interrupted_ok:
            raise RuntimeError("restart did not mark the SIGKILL run INTERRUPTED")
        recovered_run_id = runtime.start(request)
        recovered_summary = _wait_for_runtime(runtime, recovered_run_id)
    finally:
        runtime.close()

    receipts.record_complete(
        window_id=window_id,
        window_hash=window_hash,
        arm="review_d0",
        runtime_run_id=recovered_run_id,
        summary=recovered_summary,
    )
    legacy_run_id, legacy_summary = _run_legacy(batch.records_by_source, proof_slice.environment)
    receipts.record_complete(
        window_id=window_id,
        window_hash=_control_digest(window_hash),
        arm="legacy_funnel",
        runtime_run_id=legacy_run_id,
        summary=legacy_summary,
    )
    _, _, resubmitted = _run_slice(
        proof_slice=recovery_slice,
        batch=batch,
        reference=reference,
        embedder=embedder,
        index=index,
        runtime_root=runtime_root,
        receipts=receipts,
        manifest_digest=manifest_digest,
    )
    skipped_by_hash = resubmitted["review_runtime_run_id"] == recovered_run_id
    skipped_control_by_hash = resubmitted["legacy_run_id"] == legacy_run_id

    uninterrupted_run_id, uninterrupted_summary, _ = _run_review_runtime(
        batch=batch,
        sources=[proof_slice.source],
        start=start,
        end=end,
        environment=proof_slice.environment,
        reference=reference,
        embedder=embedder,
        index=index,
        runtime_dir=runtime_root / window_id / "uninterrupted_control",
    )
    recovered_metrics = _runtime_metrics(recovered_summary)
    uninterrupted_metrics = _runtime_metrics(uninterrupted_summary)
    metrics_equal = recovered_metrics == uninterrupted_metrics
    return {
        "status": "PASS"
        if skipped_by_hash and skipped_control_by_hash and metrics_equal
        else "FAIL",
        "window_id": window_id,
        "window_hash": window_hash,
        "window_event_count": batch.fetched,
        "sigkill_sent": True,
        "worker_exitcode": process.exitcode,
        "interrupted_run_id": interrupted_run_id,
        "interrupted_status": "INTERRUPTED" if interrupted_ok else "UNEXPECTED",
        "recovery_run_id": recovered_run_id,
        "recovery_status": "COMPLETE",
        "resubmission_skipped_review_by_hash": skipped_by_hash,
        "resubmission_skipped_control_by_hash": skipped_control_by_hash,
        "uninterrupted_control_run_id": uninterrupted_run_id,
        "recovered_metrics": recovered_metrics,
        "uninterrupted_metrics": uninterrupted_metrics,
        "metrics_equal": metrics_equal,
    }


def _embedder_change_drill(
    *,
    calibration_records: Mapping[str, Sequence[Mapping[str, Any]]],
    test_records: Mapping[str, Sequence[Mapping[str, Any]]],
    reference: Reference,
    embedder: Embedder,
    index: AnchorIndex | None,
    runtime_root: Path,
) -> dict[str, Any]:
    changed_embedder = _embedder(256)
    changed_index = _index(changed_embedder)
    batch = _batch_from_records(test_records)
    sources = [SourceSpec(*source_id.split(":", 1)) for source_id in sorted(test_records)]
    sample_rows = [row for records in test_records.values() for row in records]
    start = min(float(row["_time"]) for row in sample_rows)
    end = max(float(row["_time"]) for row in sample_rows) + 1.0
    sample_units = len(build_window_units(batch.records_by_source).units)
    request = ReviewRequest(sources, start, end, "portal5_lab", DEFAULT_CONFIG)
    changed_runtime = ReviewRuntime(
        source=FixedBatchSource(batch),
        embedder=changed_embedder,
        index=changed_index,
        reference=reference,
        config=DEFAULT_CONFIG,
        environment_id="portal5_lab",
        review_dir=runtime_root / "embedder_change_256",
        calibration_records_by_source=calibration_records,
    )
    try:
        stale_before = changed_runtime.doctor(fix=False)
        fix_result = changed_runtime.doctor(fix=True)
        stale_after_fix = changed_runtime.doctor(fix=False)
        changed_run_id = ""
        changed_result: dict[str, Any] = {"concerns": []}
        elapsed = 0.0
        if not stale_after_fix["embedder"]["stale"]:
            started = time.monotonic()
            changed_run_id = changed_runtime.start(request)
            changed_result = _wait_for_runtime(changed_runtime, changed_run_id)
            elapsed = time.monotonic() - started
        repaired_reference = changed_runtime.reference
    finally:
        changed_runtime.close()

    raised = len(_top_concerns(changed_result, PROOF_WORKLOAD_B))
    alpha = DEFAULT_CONFIG.policy.alpha_unusual
    rate = 1000.0 * raised / sample_units if sample_units else None
    proportion = raised / sample_units if sample_units else 0.0
    standard_error = (
        1000.0 * (proportion * (1.0 - proportion) / sample_units) ** 0.5 if sample_units else None
    )
    permitted = 1000.0 * alpha + 3.0 * float(standard_error or 0.0)
    false_raise_ok = rate is not None and standard_error is not None and rate <= permitted

    restore_runtime = ReviewRuntime(
        source=FixedBatchSource(batch),
        embedder=embedder,
        index=index,
        reference=repaired_reference,
        config=DEFAULT_CONFIG,
        environment_id="portal5_lab",
        review_dir=runtime_root / "embedder_restore_default",
        calibration_records_by_source=calibration_records,
    )
    try:
        stale_before_restore = restore_runtime.doctor(fix=False)
        restore_fix = restore_runtime.doctor(fix=True)
        stale_after_restore = restore_runtime.doctor(fix=False)
    finally:
        restore_runtime.close()

    repaired = (
        bool(stale_before["embedder"]["stale"])
        and bool(fix_result["fix"]["applied"])
        and not bool(stale_after_fix["embedder"]["stale"])
    )
    restored = (
        bool(stale_before_restore["embedder"]["stale"])
        and bool(restore_fix["fix"]["applied"])
        and not bool(stale_after_restore["embedder"]["stale"])
    )
    status = "PASS" if repaired and changed_run_id and false_raise_ok and restored else "FAIL"
    return {
        "status": status,
        "sample_window": "portal5_lab_20260616",
        "sample_event_count": batch.fetched,
        "sample_benign_unit_count": sample_units,
        "from_identity": embedder.identity,
        "temporary_identity": changed_embedder.identity,
        "stale_before_fix": stale_before["embedder"]["stale_calibrations"],
        "doctor_fix_applied": bool(fix_result["fix"]["applied"]),
        "stale_after_fix": stale_after_fix["embedder"]["stale_calibrations"],
        "changed_run_id": changed_run_id,
        "elapsed_seconds": elapsed,
        "false_raised_units": raised,
        "false_raise_per_1000": rate,
        "false_raise_alpha_plus_3se_per_1000": permitted,
        "false_raise_within_tolerance": false_raise_ok,
        "return_to_default_identity": embedder.identity,
        "return_to_default_fix_applied": bool(restore_fix["fix"]["applied"]),
        "final_stale_calibrations": stale_after_restore["embedder"]["stale_calibrations"],
    }


def _top_concerns(summary: Mapping[str, Any], workload_b: int) -> list[Mapping[str, Any]]:
    concerns = [
        row
        for row in summary.get("concerns", [])
        if isinstance(row, Mapping) and row.get("group") == "concerns"
    ]
    return sorted(
        concerns, key=lambda row: (float(row.get("priority_p") or 0.0), str(row.get("unit_id")))
    )[:workload_b]


def _grounded(summary: Mapping[str, Any], available_event_ids: set[str]) -> bool:
    return all(
        set(row.get("evidence_event_ids") or []) <= available_event_ids
        for row in summary.get("concerns", [])
        if isinstance(row, Mapping)
    )


def _truth_hit(summary: Mapping[str, Any], truth_event_ids: set[str], workload_b: int) -> bool:
    return any(
        truth_event_ids.intersection(set(row.get("evidence_event_ids") or []))
        for row in _top_concerns(summary, workload_b)
    )


def _answer_key_rows(
    proof_slice: ProofSlice,
    batch: WindowBatch,
    review_summary: Mapping[str, Any],
    control_summary: Mapping[str, Any],
    *,
    workload_b: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    source_id = proof_slice.source.source_id
    records = batch.records_by_source.get(source_id, [])
    for entry in BOTS_ANSWER_KEY:
        if entry.dataset != proof_slice.index or proof_slice.sourcetype not in entry.sourcetypes:
            continue
        matched = [row for row in records if _matching_entities(row, entry.entities)]
        located = {entity for row in matched for entity in _matching_entities(row, entry.entities)}
        if not matched or set(entry.entities) - located:
            excluded.append(
                {
                    "dataset": entry.dataset,
                    "technique": entry.technique,
                    "window_id": proof_slice.window_id,
                    "reason": "current window did not independently locate every answer-key entity",
                    "matched_event_count": len(matched),
                    "located_entity_count": len(located),
                    "expected_entity_count": len(entry.entities),
                }
            )
            continue
        event_ids = {event_id_for(source_id, row) for row in matched}
        available = set(_event_ids(batch))
        item_hash = hashlib.sha256(
            f"{entry.dataset}|{entry.technique}|{sorted(event_ids)}".encode()
        ).hexdigest()[:16]
        rows.append(
            {
                "claim": "C2",
                "row_id": item_hash,
                "class": "known",
                "workload_B": workload_b,
                "review_hit": _truth_hit(review_summary, event_ids, workload_b),
                "control_hit": _truth_hit(control_summary, event_ids, workload_b),
                "review_raised": False,
                "grounding_resolved": _grounded(review_summary, available),
                "absence_receipt_verified": False,
                "alpha": DEFAULT_CONFIG.policy.alpha_unusual,
                "truth_source": "independent BOTS answer-key entity join",
                "matched_event_count": len(event_ids),
            }
        )
    return rows, excluded


def _source_claim_row(
    proof_slice: ProofSlice,
    batch: WindowBatch,
    control_summary: Mapping[str, Any],
) -> dict[str, Any]:
    intake = build_window_units(batch.records_by_source)
    source_id = proof_slice.source.source_id
    has_unit = any(source_id in unit.source_ids for unit in intake.units)
    control_units = next(
        (
            row
            for row in control_summary.get("receipts", [])
            if isinstance(row, Mapping) and row.get("name") == "legacy.units"
        ),
        {},
    )
    legacy_has_unit = int(control_units.get("examined") or 0) > 0
    legacy_blind = any(source_id in str(note) for note in control_summary.get("degraded", []))
    return {
        "claim": "C1",
        "row_id": hashlib.sha256(source_id.encode()).hexdigest()[:16],
        "source": source_id,
        "review_valid_extraction": source_id not in intake.blind_sources,
        "review_has_unit": has_unit,
        "control_valid_extraction": not legacy_blind,
        "control_has_unit": legacy_has_unit,
        "window_id": proof_slice.window_id,
    }


def _processed_event_count(rows: Sequence[Mapping[str, Any]]) -> int:
    corpus_indexes = {"botsv1", "botsv2", "botsv3", "portal5_lab"}
    return sum(
        int(row.get("fetched") or 0)
        for row in rows
        if row.get("claim") == "C3_WINDOW" and row.get("index") in corpus_indexes
    )


def _processed_fraction(
    rows: Sequence[Mapping[str, Any]], index_counts: Mapping[str, int]
) -> float:
    return _processed_event_count(rows) / max(sum(index_counts.values()), 1)


def _receipt_stages(
    window_id: str, summary: Mapping[str, Any], elapsed: float
) -> list[dict[str, Any]]:
    receipts = [row for row in summary.get("receipts", []) if isinstance(row, Mapping)]
    per_stage = max(elapsed / max(len(receipts), 1), 0.001)
    out: list[dict[str, Any]] = []
    for row in receipts:
        examined = int(row.get("examined") or 0)
        resolved = int(row.get("resolved") or 0)
        out.append(
            {
                "claim": "C3_STAGE",
                "row_id": f"{window_id}:{row.get('name', 'stage')}",
                "stage": str(row.get("name") or "unnamed"),
                "examined": examined,
                "resolved": resolved,
                "duration_seconds": per_stage,
                "duration_method": "equal_share_of_end_to_end_runtime_estimate",
                "cause": str(row.get("note") or ""),
            }
        )
    return out


def _load_capture_evidence() -> tuple[Mapping[str, Any], Sequence[TruthItem], dict[str, Any]]:
    manifest = json.loads(CAPTURE_MANIFEST.read_text(encoding="utf-8"))
    population = derive_capture_truth(CAPTURE_DATA_DIR, manifest)
    reason_counts: Counter[str] = Counter()
    rule_reasons = {"CAPTURE_GROUND_TRUTH_INVALID", "NO_SIGNAL_RULE"}
    for path in CAPTURE_DATA_DIR.glob("*.json"):
        try:
            capture = json.loads(path.read_bytes())
        except (json.JSONDecodeError, UnicodeDecodeError):
            reason_counts["MALFORMED_CAPTURE_JSON"] += 1
            continue
        if isinstance(capture, Mapping):
            result = validate_capture(capture)
            if not result.valid:
                reason_counts.update(set(result.reasons))
    reason_rows = dict(sorted(reason_counts.items()))
    rule_histogram = {key: reason_counts[key] for key in sorted(rule_reasons) if reason_counts[key]}
    missing_histogram = {
        key: value for key, value in reason_rows.items() if key not in rule_reasons
    }
    aggregate = {
        "admitted_count": int(manifest["admitted_count"]),
        "total_count": int(manifest["capture_store_file_count"]),
        "rejection_reason_histogram": reason_rows,
        "validator_rule_histogram": rule_histogram,
        "missing_data_histogram": missing_histogram,
        "manifest_sha256": str(manifest["admission_manifest_sha256"]),
        "selftest_passed": bool(manifest.get("selftest", {}).get("passed")),
    }
    return manifest, list(population.items), aggregate


def _capture_window(
    *,
    item: Any,
    records_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    reference: Reference,
    embedder: Embedder,
    index: AnchorIndex | None,
    runtime_root: Path,
    workload_b: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], WindowBatch]:
    start = min(float(row["_time"]) for records in records_by_source.values() for row in records)
    end = (
        max(float(row["_time"]) for records in records_by_source.values() for row in records) + 1.0
    )
    batch = _batch_from_records(records_by_source)
    sources = [SourceSpec(*source_id.split(":", 1)) for source_id in records_by_source]
    run_id, candidate, elapsed = _run_review_runtime(
        batch=batch,
        sources=sources,
        start=start,
        end=end,
        environment="recorded_captures",
        reference=reference,
        embedder=embedder,
        index=index,
        runtime_dir=runtime_root / "recorded_capture" / "review_d0",
    )
    control_id, control = _run_legacy(batch.records_by_source, "recorded_captures")
    truth_event_ids = set(item.event_ids)
    available = set(_event_ids(batch))
    row_id = hashlib.sha256(item.item_id.encode()).hexdigest()[:16]
    row = {
        "claim": "C4",
        "row_id": row_id,
        "class": item.klass,
        "workload_B": workload_b,
        "review_hit": _truth_hit(candidate, truth_event_ids, workload_b),
        "control_hit": _truth_hit(control, truth_event_ids, workload_b),
        "review_raised": False,
        "grounding_resolved": _grounded(candidate, available),
        "absence_receipt_verified": False,
        "alpha": DEFAULT_CONFIG.policy.alpha_unusual,
        "capture_item_hash": row_id,
        "capture_event_count": len(truth_event_ids),
    }
    c2_row = {
        **row,
        "claim": "C2",
        "class": item.klass,
        "capture_item_hash": row_id,
    }
    metadata = {
        "window_id": "recorded_capture_admitted_sample",
        "window_hash": hashlib.sha256("|".join(sorted(available)).encode()).hexdigest(),
        "corpus_snapshot": f"real:recorded-captures:{hashlib.sha256('|'.join(sorted(available)).encode()).hexdigest()}",
        "review_runtime_run_id": run_id,
        "legacy_run_id": control_id,
        "expected_events": batch.expected,
        "fetched_events": batch.fetched,
        "elapsed_seconds": elapsed,
        "duration_seconds": elapsed,
    }
    c3_rows = [
        {
            "claim": "C3_WINDOW",
            "row_id": "recorded_capture_admitted_sample",
            "window_id": "recorded_capture_admitted_sample",
            "index": "recorded_captures",
            "sourcetype": ",".join(sorted(records_by_source)),
            "expected": batch.expected,
            "fetched": batch.fetched,
            "corpus_size": batch.expected,
        }
    ]
    c3_rows.extend(_receipt_stages("recorded_capture_admitted_sample", candidate, elapsed))
    return (
        row,
        metadata,
        {"candidate": candidate, "control": control, "c3_rows": c3_rows, "c2_row": c2_row},
        batch,
    )


def _run_main(args: argparse.Namespace) -> int:  # noqa: C901, PLR0912, PLR0915 -- fixed proof orchestration boundary.
    if not TRUTH_MANIFEST.is_file() or not CAPTURE_MANIFEST.is_file():
        raise FileNotFoundError("T1/T2 truth or certified capture manifest is unavailable")
    embedder = _embedder()
    index = _index(embedder)
    source = SplunkWindowSource()
    health = source.health()
    if health.get("reachable") is not True:
        raise RuntimeError("Splunk health did not confirm a reachable read-only source")
    index_counts = {
        name: int(value)
        for name, value in (health.get("indexes") or {}).items()
        if name in {"botsv1", "botsv2", "botsv3", "portal5_lab"} and value is not None
    }
    if set(index_counts) != {"botsv1", "botsv2", "botsv3", "portal5_lab"}:
        raise RuntimeError("one or more T6 corpus indexes did not return a count")

    lab_cal, lab_test = _load_lab_split()
    live_cal: dict[str, dict[str, list[dict[str, Any]]]] = {}
    test_batches: dict[str, WindowBatch] = {}
    calibration_metadata: dict[str, list[dict[str, Any]]] = {}
    all_batch_hashes: dict[str, str] = {}
    truth_manifest_sha = hashlib.sha256(TRUTH_MANIFEST.read_bytes()).hexdigest()
    for proof_slice in PLAN:
        calibration_batch = source.fetch(
            [proof_slice.source], proof_slice.calibration_start, proof_slice.calibration_end
        )
        live_cal.setdefault(proof_slice.environment, {}).update(calibration_batch.records_by_source)
        calibration_metadata.setdefault(proof_slice.environment, []).append(
            {
                "source": proof_slice.source.source_id,
                "start": proof_slice.calibration_start,
                "end": proof_slice.calibration_end,
                "different_utc_day": datetime.fromtimestamp(proof_slice.start, UTC)
                .date()
                .isoformat()
                != datetime.fromtimestamp(proof_slice.calibration_start, UTC).date().isoformat(),
                "expected": calibration_batch.expected,
                "fetched": calibration_batch.fetched,
            }
        )
        test_batch = source.fetch([proof_slice.source], proof_slice.start, proof_slice.end)
        test_batches[proof_slice.window_id] = test_batch
        all_batch_hashes[proof_slice.window_id] = hashlib.sha256(
            "|".join(_event_ids(test_batch)).encode()
        ).hexdigest()
    lab_test_batches: dict[str, WindowBatch] = {}
    for source_id, lab_records in lab_test.items():
        if not lab_records:
            continue
        first = min(float(row["_time"]) for row in lab_records)
        last = max(float(row["_time"]) for row in lab_records) + 1.0
        lab_test_batches[source_id] = InMemoryWindowSource(
            {source_id: lab_records}, partition_seconds=86_400
        ).fetch([SourceSpec(*source_id.split(":", 1))], first, last)
        all_batch_hashes[f"portal5_lab_{source_id.rsplit(':', 1)[-1]}_20260616"] = hashlib.sha256(
            "|".join(_event_ids(lab_test_batches[source_id])).encode()
        ).hexdigest()

    manifest_digest = hashlib.sha256(
        json.dumps(
            {
                "truth_manifest": truth_manifest_sha,
                "index_counts": index_counts,
                "test_batches": all_batch_hashes,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    snapshot = f"real:t6-proof:{manifest_digest}"
    config_payload = {
        "arm": "review_d0",
        "control": "legacy_funnel",
        "workload_B": PROOF_WORKLOAD_B,
        "plan": [proof_slice.__dict__ for proof_slice in PLAN],
        "portal5_lab_days": ["2026-06-11", "2026-06-16"],
    }
    run_stamp = stamp.build_stamp(
        repo=REPO,
        embedder_id=embedder.identity,
        model_digests={},
        config=config_payload,
        corpus_snapshot=snapshot,
        policy="D-T6-PROOF; review_d0/no_reader vs legacy_funnel",
    )
    known_answer = selftest.run_selftest(stamp_digest=run_stamp.digest)
    if not known_answer.passed:
        raise RuntimeError("known-answer self-test failed before proof scoring")

    references: dict[str, Reference] = {}
    lab_cal_window = build_window_units(lab_cal)
    references["portal5_lab"] = build_reference(
        lab_cal_window,
        policy=DEFAULT_CONFIG.policy,
        index=index,
        embedder=embedder,
        environment_id="portal5_lab",
        basis="T5-certified-independent-benign-day-split",
    )
    for environment, records in live_cal.items():
        benign = build_window_units(records)
        references[environment] = build_reference(
            benign,
            policy=DEFAULT_CONFIG.policy,
            index=index,
            embedder=embedder,
            environment_id=environment,
            basis="same-index-separated-UTC-day-window",
        )

    args.runtime_dir.mkdir(parents=True, exist_ok=True)
    proof_store = ProofRunStore(args.runtime_dir / "proof_windows.sqlite3")
    rows: list[dict[str, Any]] = []
    window_reports: list[dict[str, Any]] = []
    truth_exclusions: list[dict[str, Any]] = []
    candidate_summaries: dict[str, dict[str, Any]] = {}

    try:
        for proof_slice in PLAN:
            batch = test_batches[proof_slice.window_id]
            review_summary, control_summary, metadata = _run_slice(
                proof_slice=proof_slice,
                batch=batch,
                reference=references[proof_slice.environment],
                embedder=embedder,
                index=index,
                runtime_root=args.runtime_dir / "runtime",
                receipts=proof_store,
                manifest_digest=manifest_digest,
            )
            candidate_summaries[proof_slice.window_id] = review_summary
            metadata["count_method"] = "bounded raw-search stats count plus uncapped event export"
            intake = build_window_units(batch.records_by_source)
            elapsed = float(review_summary.get("duration_seconds") or 0.001)
            rows.append(_source_claim_row(proof_slice, batch, control_summary))
            rows.append(
                {
                    "claim": "C3_WINDOW",
                    "row_id": proof_slice.window_id,
                    "window_id": proof_slice.window_id,
                    "index": proof_slice.index,
                    "sourcetype": proof_slice.sourcetype,
                    "expected": batch.expected,
                    "fetched": batch.fetched,
                    "corpus_size": index_counts[proof_slice.index],
                }
            )
            rows.extend(_receipt_stages(proof_slice.window_id, review_summary, elapsed))
            window_reports.append(metadata)
            if proof_slice.environment == "portal5_lab":
                continue
            answer_rows, excluded = _answer_key_rows(
                proof_slice,
                batch,
                review_summary,
                control_summary,
                workload_b=PROOF_WORKLOAD_B,
            )
            rows.extend(answer_rows)
            truth_exclusions.extend(excluded)

        for source_id, batch in lab_test_batches.items():
            spec = SourceSpec(*source_id.split(":", 1))
            label = source_id.rsplit(":", 1)[-1]
            first = min(float(row["_time"]) for row in batch.records_by_source[source_id])
            end = max(float(row["_time"]) for row in batch.records_by_source[source_id]) + 1.0
            window_id = f"portal5_lab_{label}_20260616"
            source_hash = hashlib.sha256("|".join(_event_ids(batch)).encode()).hexdigest()
            digest = window_digest(
                window_id=window_id,
                environment="portal5_lab",
                sources=[source_id],
                start=first,
                end=end,
                event_ids=_event_ids(batch),
                corpus_stamp=f"real:portal5_lab:{manifest_digest}",
                arm="review_d0",
            )
            saved = proof_store.completed(window_id, digest, "review_d0")
            if saved is None:
                run_id, review_summary, elapsed = _run_review_runtime(
                    batch=batch,
                    sources=[spec],
                    start=first,
                    end=end,
                    environment="portal5_lab",
                    reference=references["portal5_lab"],
                    embedder=embedder,
                    index=index,
                    runtime_dir=args.runtime_dir / "runtime" / window_id / "review_d0",
                )
                review_summary["duration_seconds"] = elapsed
                saved = proof_store.record_complete(
                    window_id=window_id,
                    window_hash=digest,
                    arm="review_d0",
                    runtime_run_id=run_id,
                    summary=review_summary,
                )
            review_summary = dict(saved.summary)
            control_hash = _control_digest(digest)
            saved_control = proof_store.completed(window_id, control_hash, "legacy_funnel")
            if saved_control is None:
                control_id, control_summary = _run_legacy(batch.records_by_source, "portal5_lab")
                saved_control = proof_store.record_complete(
                    window_id=window_id,
                    window_hash=control_hash,
                    arm="legacy_funnel",
                    runtime_run_id=control_id,
                    summary=control_summary,
                )
            control_summary = dict(saved_control.summary)
            rows.append(
                {
                    "claim": "C1",
                    "row_id": hashlib.sha256(source_id.encode()).hexdigest()[:16],
                    "source": source_id,
                    "review_valid_extraction": source_id
                    not in build_window_units(batch.records_by_source).blind_sources,
                    "review_has_unit": any(
                        source_id in unit.source_ids
                        for unit in build_window_units(batch.records_by_source).units
                    ),
                    "control_valid_extraction": True,
                    "control_has_unit": any(
                        int(item.get("examined") or 0) > 0
                        for item in control_summary.get("receipts", [])
                        if isinstance(item, Mapping) and item.get("name") == "legacy.units"
                    ),
                    "window_id": window_id,
                }
            )
            window_reports.append(
                {
                    "window_id": window_id,
                    "window_hash": digest,
                    "control_hash": control_hash,
                    "count_method": "bounded raw-search stats count plus uncapped event export",
                    "review_runtime_run_id": saved.runtime_run_id,
                    "legacy_run_id": saved_control.runtime_run_id,
                    "expected_events": batch.expected,
                    "fetched_events": batch.fetched,
                    "corpus_snapshot": f"real:portal5_lab:{manifest_digest}",
                    "event_ids_hash": source_hash,
                    "test_day": "2026-06-16",
                    "calibration_day": "2026-06-11",
                    "different_utc_day": True,
                }
            )
            rows.append(
                {
                    "claim": "C3_WINDOW",
                    "row_id": window_id,
                    "window_id": window_id,
                    "index": "portal5_lab",
                    "sourcetype": label,
                    "expected": batch.expected,
                    "fetched": batch.fetched,
                    "corpus_size": index_counts["portal5_lab"],
                }
            )
            rows.extend(
                _receipt_stages(
                    window_id,
                    review_summary,
                    float(review_summary.get("duration_seconds") or 0.001),
                )
            )
            # The two-day split comes from T5's 36/36 exact raw-text source check; cells are
            # independently labelled benign in the T1 corpus manifest. Keep each held-out unit.
            test_intake = build_window_units(batch.records_by_source)
            raised_ids = {
                str(concern.get("unit_id"))
                for concern in _top_concerns(review_summary, 1)
                if concern.get("unit_id")
            }
            for unit in test_intake.units:
                rows.append(
                    {
                        "claim": "C2",
                        "row_id": hashlib.sha256(unit.unit.unit_id.encode()).hexdigest()[:16],
                        "class": "benign",
                        "workload_B": PROOF_WORKLOAD_B,
                        "review_hit": False,
                        "control_hit": False,
                        "review_raised": unit.unit.unit_id in raised_ids,
                        "grounding_resolved": _grounded(review_summary, set(_event_ids(batch))),
                        "absence_receipt_verified": False,
                        "alpha": DEFAULT_CONFIG.policy.alpha_unusual,
                    }
                )
                rows.append(
                    {
                        "claim": "C4",
                        "row_id": hashlib.sha256(unit.unit.unit_id.encode()).hexdigest()[:16],
                        "class": "benign",
                        "workload_B": PROOF_WORKLOAD_B,
                        "review_hit": unit.unit.unit_id in raised_ids,
                        "control_hit": False,
                        "review_raised": unit.unit.unit_id in raised_ids,
                        "grounding_resolved": _grounded(review_summary, set(_event_ids(batch))),
                        "absence_receipt_verified": False,
                        "alpha": DEFAULT_CONFIG.policy.alpha_unusual,
                    }
                )

        calibration_metadata["portal5_lab"] = [
            {
                "source": source_id,
                "test_day": "2026-06-16",
                "calibration_day": "2026-06-11",
                "different_utc_day": True,
                "expected": len(records),
                "fetched": len(records),
                "provenance": "T5 36/36 exact raw-text match held out by UTC day",
            }
            for source_id, records in sorted(lab_cal.items())
        ]
        capture_manifest, capture_items, capture_summary = _load_capture_evidence()
        if capture_items:
            capture_row, capture_meta, capture_run, capture_batch = _capture_window(
                item=capture_items[0],
                records_by_source=derive_capture_truth(
                    CAPTURE_DATA_DIR, capture_manifest
                ).records_by_source,
                reference=references["portal5_lab"],
                embedder=embedder,
                index=index,
                runtime_root=args.runtime_dir / "runtime",
                workload_b=PROOF_WORKLOAD_B,
            )
            rows.append(capture_row)
            rows.append(capture_run["c2_row"])
            window_reports.append(capture_meta)
        evidence_twin_pairs: list[dict[str, Any]] = []
        truth_doc = json.loads(TRUTH_MANIFEST.read_text(encoding="utf-8"))
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for item in truth_doc.get("items", []):
            key = hashlib.sha256("|".join(sorted(item.get("event_ids", []))).encode()).hexdigest()
            grouped.setdefault(key, []).append(item)
        for digest, group in grouped.items():
            if len(group) > 1 and len({row.get("technique") for row in group}) > 1:
                evidence_twin_pairs.append(
                    {
                        "event_set_hash": digest,
                        "techniques": sorted(str(row.get("technique")) for row in group),
                        "truth_item_count": len(group),
                        "status": "identified_in_manifest_not_in_processed_windows",
                    }
                )
        claims_doc = claims.evaluate_claims(
            rows,
            corpus_snapshots=[
                f"real:{index_name}:{manifest_digest}" for index_name in sorted(index_counts)
            ]
            + [f"real:recorded-captures:{capture_summary['manifest_sha256']}"],
            selftests_passed=known_answer.passed and capture_summary["selftest_passed"],
            captures={
                "admitted_count": capture_summary["admitted_count"],
                "total_count": capture_summary["total_count"],
                "rejection_reason_histogram": capture_summary["rejection_reason_histogram"],
                "validator_rule_histogram": capture_summary["validator_rule_histogram"],
                "missing_data_histogram": capture_summary["missing_data_histogram"],
            },
            processed_fraction=_processed_fraction(rows, index_counts),
            stop_rule=(
                "stopped at the certified truth-yield ceiling: T2 admitted one cousin capture, "
                "and the T1/T2 evidence manifests contain no additional independent cousin items; "
                "the last-20-percent bootstrap-SE plateau cannot be estimated at n=1, so no "
                "synthetic substitute or repeated truth item was added"
            ),
        )
        if claims.validate_claims_document(claims_doc):
            raise ValueError(
                f"claim output failed validation: {claims.validate_claims_document(claims_doc)}"
            )

        try:
            recovery_drill = _recovery_drill(
                test_batches=test_batches,
                reference=references["botsv2"],
                embedder=embedder,
                index=index,
                runtime_root=args.runtime_dir / "runtime",
                receipts=proof_store,
                manifest_digest=manifest_digest,
            )
        except Exception as exc:  # noqa: BLE001 -- keep the failed drill visible in the report
            recovery_drill = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc)[:240],
            }

        try:
            embedder_drill = _embedder_change_drill(
                calibration_records=lab_cal,
                test_records=lab_test,
                reference=references["portal5_lab"],
                embedder=embedder,
                index=index,
                runtime_root=args.runtime_dir / "runtime",
            )
        except Exception as exc:  # noqa: BLE001 -- keep the failed drill visible in the report
            embedder_drill = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc)[:240],
            }

        # A real connection refusal exercises the grounded-reader fallback without an answer source.
        from portal.modules.security.core.review.model_client import PortalModelClient
        from portal.modules.security.core.review.reader import build_judge_fn

        unavailable_client = PortalModelClient(base_url="http://127.0.0.1:9", api_key="")
        unavailable_client.mark_reasoning_probe(
            "auto-security::security-expert-foundation-sec-8b", True
        )
        unavailable_judge = build_judge_fn(
            unavailable_client,
            "auto-security::security-expert-foundation-sec-8b",
        )
        reader_slice = next(
            (
                item
                for item in PLAN
                if _top_concerns(candidate_summaries[item.window_id], PROOF_WORKLOAD_B)
            ),
            None,
        )
        reader_drill: dict[str, Any]
        if reader_slice is None:
            reader_drill = {
                "status": "FAIL",
                "reason": "no proof window produced a deterministic concern to exercise fallback",
                "model_transport": "local connection refused before any model response",
            }
        else:
            reader_candidate = candidate_summaries[reader_slice.window_id]
            base_concern_ids = {
                str(row.get("unit_id"))
                for row in reader_candidate.get("concerns", [])
                if isinstance(row, Mapping) and row.get("group") == "concerns"
            }
            reader_batch = test_batches[reader_slice.window_id]
            try:
                fallback_run_id, fallback_result, fallback_elapsed = _run_review_runtime(
                    batch=reader_batch,
                    sources=[reader_slice.source],
                    start=reader_slice.start,
                    end=reader_slice.end,
                    environment=reader_slice.environment,
                    reference=references[reader_slice.environment],
                    embedder=embedder,
                    index=index,
                    runtime_dir=args.runtime_dir / "runtime" / "reader_unavailable",
                    judge=unavailable_judge,
                )
                unavailable_concerns = [
                    row for row in fallback_result["concerns"] if row.get("group") == "concerns"
                ]
                fallback_concern_ids = {str(row.get("unit_id")) for row in unavailable_concerns}
                no_invented_verdicts = bool(unavailable_concerns) and all(
                    row.get("judge_verdict") == "unsure"
                    and bool(row.get("judge_degraded"))
                    and int(row.get("judge_claim_count") or 0) == 0
                    for row in unavailable_concerns
                )
                deterministic_preserved = fallback_concern_ids == base_concern_ids
                reader_drill = {
                    "status": "PASS"
                    if no_invented_verdicts and deterministic_preserved
                    else "FAIL",
                    "run_id": fallback_run_id,
                    "sample_window": reader_slice.window_id,
                    "elapsed_seconds": fallback_elapsed,
                    "concern_count": len(unavailable_concerns),
                    "all_judged_unsure_and_degraded": no_invented_verdicts,
                    "no_invented_claims": sum(
                        int(row.get("judge_claim_count") or 0) for row in unavailable_concerns
                    )
                    == 0,
                    "deterministic_concerns_preserved": deterministic_preserved,
                    "model_transport": "local connection refused before any model response",
                }
            except Exception as exc:  # noqa: BLE001 -- keep the failed drill visible in the report
                reader_drill = {
                    "status": "FAIL",
                    "sample_window": reader_slice.window_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                    "model_transport": "local connection refused before any model response",
                }

        drill_results = {
            "recovery": recovery_drill,
            "embedder_change": embedder_drill,
            "reader_unreachable": reader_drill,
            "all_passed": all(
                item["status"] == "PASS" for item in (recovery_drill, embedder_drill, reader_drill)
            ),
        }
        c3_total_fetched = _processed_event_count(rows)
        corpus_total = sum(index_counts.values())
        metrics = [
            report.MetricRow(
                name="claim_proven_fraction",
                value=sum(item["status"] == "PROVEN" for item in claims_doc["claims"]) / 4.0,
                n=4,
                denominator=4,
                can_fail="fails when any standing claim is not PROVEN under the task rule",
            ),
            report.MetricRow(
                name="processed_corpus_fraction",
                value=c3_total_fetched / max(corpus_total, 1),
                n=sum(row.get("claim") == "C3_WINDOW" for row in rows),
                denominator=sum(row.get("claim") == "C3_WINDOW" for row in rows),
                can_fail="fails when the processed real-event fraction is omitted or recomputes differently",
            ),
            report.MetricRow(
                name="drill_pass_fraction",
                value=sum(
                    item["status"] == "PASS"
                    for item in (recovery_drill, embedder_drill, reader_drill)
                )
                / 3.0,
                n=3,
                denominator=3,
                can_fail="fails when any required phase-C drill does not pass",
            ),
        ]
        proof_rows = [*rows]
        proof_rows.append(
            {
                "claim": "META",
                "row_id": "summary",
                "claim_proven_count": sum(
                    item["status"] == "PROVEN" for item in claims_doc["claims"]
                ),
                "drill_pass_count": sum(
                    item["status"] == "PASS"
                    for item in (recovery_drill, embedder_drill, reader_drill)
                ),
                "processed_fraction": c3_total_fetched / max(corpus_total, 1),
            }
        )
        document = report.build_report(
            stamp=run_stamp,
            selftest=known_answer,
            metrics=metrics,
            rows=proof_rows,
            recompute={
                "claim_proven_fraction": lambda raw: (
                    float(
                        next(row for row in raw if row.get("claim") == "META")["claim_proven_count"]
                    )
                    / 4.0
                ),
                "processed_corpus_fraction": lambda raw: float(
                    next(row for row in raw if row.get("claim") == "META")["processed_fraction"]
                ),
                "drill_pass_fraction": lambda raw: (
                    float(
                        next(row for row in raw if row.get("claim") == "META")["drill_pass_count"]
                    )
                    / 3.0
                ),
            },
            extra={
                "arm": "T6-real-corpus-proof",
                "control": "legacy_funnel",
                "candidate": "review_d0/no_reader",
                "claims": claims_doc,
                "proof_rows": proof_rows,
                "windows": window_reports,
                "calibration_windows": calibration_metadata,
                "index_event_counts": index_counts,
                "processed_event_count": c3_total_fetched,
                "corpus_fraction": c3_total_fetched / max(corpus_total, 1),
                "stop_rule": claims_doc["stop_rule"],
                "capture_admission": capture_summary,
                "truth_exclusions": truth_exclusions,
                "evidence_twin_candidates": evidence_twin_pairs,
                "drills": drill_results,
                "raw_telemetry_persisted": False,
                "report_status": "INCONCLUSIVE"
                if claims_doc["status"] != "PROVEN" or not drill_results["all_passed"]
                else "PROVEN",
            },
        )
        output_json, output_md = report.write_report(document, args.out, "t6_proof")
        print(
            json.dumps(
                {
                    "json": str(output_json),
                    "markdown": str(output_md),
                    "stamp": run_stamp.digest,
                    "status": document["extra"]["report_status"],
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        proof_store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--runtime-dir", type=Path, default=PRIVATE_OUTPUT)
    args = parser.parse_args()
    return _run_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
