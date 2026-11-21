"""Reindex one training corpus into ``<index>_v2`` with an explicit sourcetype per input.

Byte-faithful by construction: the same record splitter, timestamp parser and event envelope as
``scripts/hunt_bed/ingest_native.py`` (the tool that produced the receipts this plan is built
from), so ``digests.jsonl`` and therefore ``keys.jsonl`` still join. Only the sourcetype label
changes — which is the whole point of the stage.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts.hunt_bed.ingest_native import _post, _records, parse_time

from . import plan


def load_receipt(spec: plan.IndexSpec) -> dict:
    return json.loads(spec.receipt.read_text())


def make_plan(spec: plan.IndexSpec, *, keep_metrics: bool = False) -> plan.ReindexPlan:
    receipt = load_receipt(spec)
    return plan.build_reindex_plan(
        spec,
        receipt["files"],
        keep_metrics=keep_metrics,
        root=Path(receipt["root"]),
    )


@dataclass
class ShippedFile:
    host: str
    source: str
    sourcetype: str
    index: str
    sent: int = 0
    time_carried: int = 0
    time_none: int = 0
    seconds: float = 0.0


@dataclass
class ShipReceipt:
    index: str
    root: str
    files: list[ShippedFile] = field(default_factory=list)

    @property
    def sent_total(self) -> int:
        return sum(item.sent for item in self.files)


def resolve_path(plan_root: Path, host: str, source: str) -> Path:
    """The receipt's source is the path below the host's ``logs/`` dir (ingest_native)."""
    for candidate in (
        plan_root / host / "logs" / source.lstrip("/"),
        plan_root / host / source.lstrip("/"),
    ):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"receipt names {host}{source} but neither logs{source} nor {source} exists"
    )


def _ship_file(
    row: plan.PlanRow,
    plan_root: Path,
    index: str,
    year: int,
    *,
    batch_size: int,
    dry_run: bool,
    token: str,
    hec: str,
) -> ShippedFile:
    """Ship one input with an explicit sourcetype; identical event bytes and timestamps."""
    path = resolve_path(plan_root, row.host, row.source)
    out = ShippedFile(row.host, row.source, str(row.sourcetype_out), index)
    batch: list[bytes] = []
    size = 0
    last_t: float | None = None
    for _lineno, raw_bytes in _records(path):
        raw = raw_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
        if not raw.strip():
            continue
        t = parse_time(raw, year)
        if t is None:
            if last_t is None:
                out.time_none += 1
            else:
                out.time_carried += 1
            t = last_t
        last_t = t
        event: dict[str, object] = {
            "host": row.host,
            "source": row.source,
            "sourcetype": out.sourcetype,
            "index": index,
            "event": raw,
        }
        if t is not None:
            event["time"] = f"{t:.6f}"
        batch.append(json.dumps(event).encode())
        size += len(batch[-1])
        out.sent += 1
        if len(batch) >= batch_size or size > 512_000:
            if not dry_run:
                _post(hec, token, b"\n".join(batch))
            batch, size = [], 0
    if batch and not dry_run:
        _post(hec, token, b"\n".join(batch))
    return out


def ship(
    reindex: plan.ReindexPlan,
    *,
    state_dir: Path,
    resume: bool = False,
    dry_run: bool = False,
    batch: int = 5000,
    on_file=None,
) -> ShipReceipt:
    """Ship every kept file into the target index; resumable through state_dir/receipt.json."""
    state_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = state_dir / f"{reindex.spec.target_index}.receipt.json"
    receipt = ShipReceipt(reindex.spec.target_index, str(reindex.root))
    if resume and receipt_path.exists():
        prior = json.loads(receipt_path.read_text())
        receipt.files = [ShippedFile(**item) for item in prior.get("files", [])]
    done = {(item.host, item.source) for item in receipt.files}
    hec = token = ""
    if not dry_run:
        hec = os.environ["LAB_SPLUNK_HEC_URL"].rstrip("/") + "/services/collector/event"
        token = os.environ["LAB_SPLUNK_HEC_TOKEN"]
    for row in reindex.rows:
        if row.sourcetype_out is None or (resume and (row.host, row.source) in done):
            continue
        shipped = _ship_file(
            row,
            reindex.root,
            reindex.spec.target_index,
            reindex.spec.default_year,
            batch_size=batch,
            dry_run=dry_run,
            token=token,
            hec=hec,
        )
        receipt.files.append(shipped)
        receipt_path.write_text(json.dumps(asdict(receipt), indent=1))
        if on_file:
            on_file(shipped)
    return receipt
