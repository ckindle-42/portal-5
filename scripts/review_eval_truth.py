#!/usr/bin/env python3
"""Derive BOTS answer-key truth and select a benign comparator -- reproducibly, as code.

T1 reported `7 of 27 answer-key entries derived` and `0 of 3 indexes yielded a benign interval`,
and every record from T2 to T6 cites that result as the reason no product arm ran. The producer of
that report was never committed: nothing in the tree writes `truth_derivation.json`, and
`review_eval.truth.benign_interval_candidates` has no caller outside its unit test. So the premise
the program rests on could not be re-run or re-checked. This script is that producer, committed.

It also makes the benign-pairing rule an **arm** rather than an axiom, because the rule as T1
applied it cannot be satisfied by a curated attack corpus: the `hull` arm needs a benign window as
long as the whole span of an index's answer-key entries, which for botsv1 is 27.9 days inside an
index that holds roughly that much telemetry in total. See `docs/review_decisions/D-T8-PAIRING.md`;
`hull` is the control and reproduces T1 exactly.

Read-only: the only traffic is a Splunk search. Nothing is executed against any target.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY  # noqa: E402
from portal.modules.security.core.bully.corpus_bed import BOTS_INDEXES  # noqa: E402
from portal.modules.security.core.review.embedding import PlatformEmbedder  # noqa: E402
from portal.modules.security.core.review.wall import assert_label_free  # noqa: E402
from portal.modules.security.core.review.window import (  # noqa: E402
    SourceSpec,
    SplunkWindowSource,
    WindowFetchError,
    normalize_splunk_record,
)
from portal.modules.security.core.review_eval import report as report_mod  # noqa: E402
from portal.modules.security.core.review_eval import selftest as selftest_mod  # noqa: E402
from portal.modules.security.core.review_eval import stamp as stamp_mod  # noqa: E402
from portal.modules.security.core.review_eval.truth import (  # noqa: E402
    EntitySearchStat,
    EntryReceipt,
    TruthDerivation,
    benign_interval_candidates,
    derive_bots_truth,
)
from portal.platform.embedding.contract import Role, Task  # noqa: E402


class ExtentSource(Protocol):
    """What pairing needs from a source: how much indexed time the index actually holds."""

    def index_extent(self, index: str) -> tuple[float | None, float | None]: ...


PAIRINGS = ("hull", "per_entry", "matched_set", "cross_index", "cross_index_benign")
DEFAULT_MARGIN_SECONDS = 86_400.0
SECONDS_PER_DAY = 86_400.0

#: T1's verbatim exclusion reason, kept so the control arm's receipts compare word for word.
HULL_NO_CANDIDATE = (
    "no_same_size_utc_day_aligned_background_window_outside_answer_key_spans_plus_margin"
)
HULL_CANDIDATE = "same_size_window_outside_the_answer_key_hull_plus_margin"
PER_ENTRY_CANDIDATE = "per_entry_windows_outside_every_entry_span_plus_margin"
PER_ENTRY_NO_CANDIDATE = "no_entry_sized_window_outside_the_entry_spans_plus_margin"
MATCHED_CANDIDATE = "day_slices_in_the_complement_reach_the_attack_duration"
MATCHED_NO_CANDIDATE = "the_complement_cannot_reach_the_attack_duration"
NO_DERIVED_INTERVAL = "no_fully_derived_answer_key_interval"

#: D-T9: sources that cannot count as benign. Everything Portal writes into the lab index carries a
#: ``portal5:`` source -- the published attack corpora (``portal5:corpus:mordor:*``,
#: ``portal5:corpus:attack_data:*``) and Bully's emulation-run evidence origins
#: (``portal5:observed_packet``, ``portal5:imported_observed``, ...) -- and the Bully HEC shipper
#: writes ``http:portal5_hec``. None of it is a benign population. Any other source is unlabeled
#: background: eligible, and reported by name as a covariate.
BENIGN_DENIED_SOURCE_PREFIXES = ("portal5:",)
BENIGN_DENIED_SOURCES = frozenset({"http:portal5_hec"})


def benign_source_eligible(source: str) -> bool:
    return source not in BENIGN_DENIED_SOURCES and not source.startswith(
        BENIGN_DENIED_SOURCE_PREFIXES
    )


def occupied_window(
    daily_eligible: Mapping[float, int], duration_seconds: float
) -> tuple[float, float] | None:
    """The earliest UTC-day-aligned window of ``duration_seconds`` with eligible events every day.

    D-T8's ``cross_index`` arm placed its window from the benign index's min/max extent alone and
    landed on two empty 2010 days. A comparator must hold a population, so every UTC day the
    window touches needs at least one eligible event. Earliest-first is the only selection: no
    window is preferred for its content.
    """
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    for start in sorted(day for day, count in daily_eligible.items() if count > 0):
        day = start
        while day < start + duration_seconds:
            if daily_eligible.get(day, 0) <= 0:
                break
            day += SECONDS_PER_DAY
        else:
            return start, start + duration_seconds
    return None


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _entity_clause(entities: Sequence[str]) -> str:
    if not entities:
        return ""
    return " (" + " OR ".join(_quote(entity) for entity in entities) + ")"


def _as_float(value: Any) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


@dataclass
class FetchCensus:
    """Why a fetched row set may not reconcile: recorded, never silently absorbed."""

    rows: int = 0
    rows_without_cd: int = 0
    distinct_ids: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "rows_without_cd": self.rows_without_cd,
            "distinct_ids": self.distinct_ids,
            "id_collisions": self.rows - self.distinct_ids,
        }


class SplunkTruthSource:
    """Entity-scoped stats and partitioned raw reads over a read-only Splunk index.

    Both callables filter identically, so ``derive_bots_truth``'s expected-vs-fetched
    reconciliation compares like with like. Raw reads are partitioned because a single
    whole-span export exceeds the read timeout on a large window (T2 lost a 616k-event
    window that way), and a timeout there is indistinguishable from absent truth.
    """

    def __init__(self, source: SplunkWindowSource, *, partition_seconds: float) -> None:
        if partition_seconds <= 0:
            raise ValueError("partition_seconds must be positive")
        self.source = source
        self.partition_seconds = partition_seconds
        self.census = FetchCensus()
        self._seen_ids: set[str] = set()

    def query_stats(self, index: str, sourcetype: str, entities: Sequence[str]) -> EntitySearchStat:
        search = (
            f"search index={_quote(index)} sourcetype={_quote(sourcetype)}"
            f"{_entity_clause(entities)}"
            " | stats count as count, min(_time) as first, max(_time) as last"
        )
        rows = list(self.source.iter_post(search, 0.0, time.time() + 1.0))
        if not rows:
            return EntitySearchStat(0, None, None)
        if len(rows) != 1:
            raise WindowFetchError(f"stats returned {len(rows)} rows for {index}:{sourcetype}")
        row = rows[0]
        count = int(_as_float(row.get("count")) or 0)
        return EntitySearchStat(count, _as_float(row.get("first")), _as_float(row.get("last")))

    def fetch_records(
        self,
        index: str,
        sourcetype: str,
        entities: Sequence[str],
        start: float,
        end: float,
    ) -> Iterator[Mapping[str, Any]]:
        if end <= start:
            return
        spec = SourceSpec(index, sourcetype)
        search = (
            f"search index={_quote(index)} sourcetype={_quote(sourcetype)}"
            f"{_entity_clause(entities)}"
        )
        cursor = start
        while cursor < end:
            boundary = min(cursor + self.partition_seconds, end)
            for row in self.source.iter_post(search, cursor, boundary):
                record = normalize_splunk_record(spec, row)
                assert_label_free(record, where=f"splunk:{spec.source_id}")
                self.census.rows += 1
                if "_cd" not in record:
                    self.census.rows_without_cd += 1
                yield record
            cursor = boundary

    def index_extent(self, index: str) -> tuple[float | None, float | None]:
        # tsidx metadata, not a raw scan: `search index=X | stats min(_time), max(_time)` over
        # botsv1's 33.4M events dispatched for 45+ minutes without answering, which would make
        # every arm a multi-day run. tstats answers the same extent in seconds; its botsv1
        # count (33,413,837) matches the index probe exactly and its extent is the dataset's
        # documented coverage. tstats streams partial preview rows before the final one, so
        # the extent is read from the last row.
        search = (
            f"| tstats count as count, min(_time) as first, max(_time) as last"
            f" where index={_quote(index)}"
        )
        rows = list(self.source.iter_post(search, 0.0, time.time() + 1.0))
        if not rows:
            return None, None
        row = rows[-1]
        first = _as_float(row.get("first"))
        last = _as_float(row.get("last"))
        return first, (last + 0.000001 if last is not None else None)

    def daily_source_counts(self, index: str) -> dict[float, dict[str, int]]:
        """Event counts per UTC day and source, from tsidx metadata (aggregates only).

        Hourly buckets floored to the UTC day keep the result independent of the search head's
        timezone. Preview rows stream before the final ones, so a later row for the same
        (day, source) replaces an earlier one.
        """
        search = (
            f"| tstats count as count where index={_quote(index)} by source _time span=1h"
            " | eval day=floor(_time/86400)*86400"
            " | stats sum(count) as count by day source"
        )
        out: dict[float, dict[str, int]] = {}
        for row in self.source.iter_post(search, 0.0, time.time() + 1.0):
            day = _as_float(row.get("day"))
            count = _as_float(row.get("count"))
            if day is None or count is None:
                continue
            out.setdefault(day, {})[str(row.get("source", ""))] = int(count)
        return out


def matched_set_candidates(
    corpus_start: float,
    corpus_end: float,
    excluded_spans: Sequence[tuple[float, float]],
    *,
    margin_seconds: float,
    target_duration_seconds: float,
    slice_seconds: float = SECONDS_PER_DAY,
) -> tuple[tuple[float, float], ...]:
    """Day-aligned slices in the complement whose total reaches ``target_duration_seconds``.

    One contiguous same-length window is a stricter requirement than the comparison needs: the
    product reads a set of windows either way. Returns ``()`` when the complement cannot reach
    the target, so a short corpus still fails loudly instead of yielding a short comparator.
    """
    if corpus_end <= corpus_start:
        raise ValueError("corpus_end must be greater than corpus_start")
    expanded = sorted(
        (start - margin_seconds, end + margin_seconds) for start, end in excluded_spans
    )
    picked: list[tuple[float, float]] = []
    total = 0.0
    cursor = corpus_start
    gaps: list[tuple[float, float]] = []
    for span_start, span_end in expanded:
        if span_start > cursor:
            gaps.append((cursor, min(span_start, corpus_end)))
        cursor = max(cursor, span_end)
    if cursor < corpus_end:
        gaps.append((cursor, corpus_end))
    for gap_start, gap_end in gaps:
        aligned = (int(gap_start // SECONDS_PER_DAY) + 1) * SECONDS_PER_DAY
        if gap_start % SECONDS_PER_DAY == 0:
            aligned = gap_start
        while aligned + slice_seconds <= gap_end and total < target_duration_seconds:
            picked.append((aligned, aligned + slice_seconds))
            total += slice_seconds
            aligned += slice_seconds
    return tuple(picked) if total >= target_duration_seconds else ()


@dataclass
class IndexPairing:
    index: str
    arm: str
    derived_entry_count: int
    attack_spans: tuple[tuple[float, float], ...]
    target_duration_seconds: float | None
    corpus_first: float | None
    corpus_end_exclusive: float | None
    candidates: tuple[tuple[float, float], ...]
    reason: str
    covariates: Mapping[str, Any] | None = None

    @property
    def paired(self) -> bool:
        return bool(self.candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "arm": self.arm,
            "derived_entry_count": self.derived_entry_count,
            "attack_span_count": len(self.attack_spans),
            "attack_spans": [
                {"start_epoch": start, "end_exclusive_epoch": end}
                for start, end in self.attack_spans
            ],
            "target_duration_seconds": self.target_duration_seconds,
            "corpus_interval": (
                {"first_epoch": self.corpus_first, "end_exclusive_epoch": self.corpus_end_exclusive}
                if self.corpus_first is not None and self.corpus_end_exclusive is not None
                else None
            ),
            "benign_candidate_count": len(self.candidates),
            "benign_candidates": [
                {"start_epoch": start, "end_exclusive_epoch": end}
                for start, end in self.candidates[:8]
            ],
            "paired": self.paired,
            "reason": self.reason,
            "covariates": dict(self.covariates) if self.covariates is not None else None,
        }


def _derived_spans(receipts: Sequence[EntryReceipt], index: str) -> list[tuple[float, float]]:
    spans: list[tuple[float, float]] = []
    for receipt in receipts:
        if receipt.index != index or receipt.status != "derived":
            continue
        start, end = receipt.start_epoch, receipt.end_exclusive_epoch
        if start is None or end is None:
            continue
        spans.append((start, end))
    return spans


def pair_index(
    index: str,
    derivation: TruthDerivation,
    source: ExtentSource,
    *,
    arm: str,
    margin_seconds: float,
    benign_index: str,
    benign_daily: Mapping[float, Mapping[str, int]] | None = None,
) -> IndexPairing:
    spans = _derived_spans(derivation.receipts, index)
    if not spans:
        return IndexPairing(index, arm, 0, (), None, None, None, (), NO_DERIVED_INTERVAL)
    hull = (min(start for start, _ in spans), max(end for _, end in spans))
    hull_duration = hull[1] - hull[0]
    extent_index = benign_index if arm.startswith("cross_index") else index
    corpus_first, corpus_end = source.index_extent(extent_index)

    def pairing(
        reported_spans: Sequence[tuple[float, float]],
        duration: float | None,
        candidates: Sequence[tuple[float, float]],
        reason: str,
        covariates: Mapping[str, Any] | None = None,
    ) -> IndexPairing:
        return IndexPairing(
            index=index,
            arm=arm,
            derived_entry_count=len(spans),
            attack_spans=tuple(reported_spans),
            target_duration_seconds=duration,
            corpus_first=corpus_first,
            corpus_end_exclusive=corpus_end,
            candidates=tuple(candidates),
            reason=reason,
            covariates=covariates,
        )

    if corpus_first is None or corpus_end is None:
        return pairing(spans, hull_duration, (), f"index_{extent_index}_has_no_indexed_time")
    if arm == "hull":
        found = benign_interval_candidates(
            corpus_first,
            corpus_end,
            [hull],
            margin_seconds=margin_seconds,
            duration_seconds=hull_duration,
        )
        return pairing([hull], hull_duration, found, HULL_CANDIDATE if found else HULL_NO_CANDIDATE)
    if arm == "per_entry":
        per_entry: list[tuple[float, float]] = []
        for start, end in spans:
            per_entry.extend(
                benign_interval_candidates(
                    corpus_first,
                    corpus_end,
                    spans,
                    margin_seconds=margin_seconds,
                    duration_seconds=end - start,
                )
            )
        unique = sorted(set(per_entry))
        return pairing(
            spans, None, unique, PER_ENTRY_CANDIDATE if unique else PER_ENTRY_NO_CANDIDATE
        )
    if arm == "matched_set":
        matched = matched_set_candidates(
            corpus_first,
            corpus_end,
            spans,
            margin_seconds=margin_seconds,
            target_duration_seconds=hull_duration,
        )
        return pairing(
            spans,
            hull_duration,
            matched,
            MATCHED_CANDIDATE if matched else MATCHED_NO_CANDIDATE,
        )
    if arm == "cross_index_benign":
        if benign_daily is None:
            raise ValueError("cross_index_benign needs the benign index's daily source counts")
        window, reason, covariates = benign_window(benign_index, hull_duration, benign_daily)
        return pairing([hull], hull_duration, [window] if window else [], reason, covariates)
    cross = benign_interval_candidates(
        corpus_first,
        corpus_end,
        [],
        margin_seconds=margin_seconds,
        duration_seconds=hull_duration,
    )
    return pairing(
        [hull],
        hull_duration,
        cross,
        f"same_size_window_in_{benign_index}_is_a_declared_covariate"
        if cross
        else f"benign_index_{benign_index}_is_shorter_than_the_attack_duration",
    )


def benign_window(
    benign_index: str,
    duration_seconds: float,
    benign_daily: Mapping[float, Mapping[str, int]],
) -> tuple[tuple[float, float] | None, str, dict[str, Any]]:
    """D-T9's ``cross_index_benign`` arm: an occupied window of eligible-source events only."""
    eligible = {
        day: sum(n for source, n in sources.items() if benign_source_eligible(source))
        for day, sources in benign_daily.items()
    }
    total = sum(n for sources in benign_daily.values() for n in sources.values())
    denied = total - sum(eligible.values())
    window = occupied_window(eligible, duration_seconds)
    covariates: dict[str, Any] = {
        "benign_index": benign_index,
        "benign_index_event_count": total,
        "denied_source_event_count": denied,
        "eligible_event_count": total - denied,
        "eligible_day_count": sum(1 for n in eligible.values() if n > 0),
        "denied_source_rule": {
            "prefixes": list(BENIGN_DENIED_SOURCE_PREFIXES),
            "sources": sorted(BENIGN_DENIED_SOURCES),
        },
    }
    if window is None:
        return (
            None,
            f"no_window_in_{benign_index}_with_eligible_events_on_every_utc_day",
            covariates,
        )
    days = [d for d in sorted(eligible) if window[0] <= d < window[1]]
    by_source: dict[str, int] = {}
    for day in days:
        for source, n in benign_daily[day].items():
            if benign_source_eligible(source):
                by_source[source] = by_source.get(source, 0) + n
    covariates.update(
        {
            "window_day_count": len(days),
            "window_eligible_event_count": sum(eligible[d] for d in days),
            "window_min_daily_eligible_count": min(eligible[d] for d in days),
            "window_eligible_sources": dict(sorted(by_source.items())),
        }
    )
    return window, f"occupied_eligible_window_in_{benign_index}_is_a_declared_covariate", covariates


def build_rows(
    derivation: TruthDerivation, pairings: Sequence[IndexPairing]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {
            "kind": "answer_key_entry",
            "item_id": receipt.item_id,
            "index": receipt.index,
            "technique": receipt.technique,
            "status": receipt.status,
            "reason": receipt.reason,
            "event_count": receipt.event_count,
            "expected_entity_count": receipt.expected_entity_count,
            "located_entity_count": receipt.located_entity_count,
        }
        for receipt in derivation.receipts
    ]
    rows.extend(
        {
            "kind": "index_slice",
            "index": pairing.index,
            "arm": pairing.arm,
            "paired": pairing.paired,
            "benign_candidate_count": len(pairing.candidates),
            "reason": pairing.reason,
        }
        for pairing in pairings
    )
    return rows


def _entry_yield(rows: Sequence[Mapping[str, Any]]) -> float:
    entries = [row for row in rows if row.get("kind") == "answer_key_entry"]
    if not entries:
        return 0.0
    return sum(bool(row.get("status") == "derived") for row in entries) / len(entries)


def _slice_yield(rows: Sequence[Mapping[str, Any]]) -> float:
    slices = [row for row in rows if row.get("kind") == "index_slice"]
    if not slices:
        return 0.0
    return sum(bool(row.get("paired")) for row in slices) / len(slices)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairing", choices=PAIRINGS, default="hull")
    parser.add_argument("--benign-index", default="portal5_lab")
    parser.add_argument("--margin-seconds", type=float, default=DEFAULT_MARGIN_SECONDS)
    parser.add_argument("--partition-seconds", type=float, default=600.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--embed-dim", type=int, default=768)
    parser.add_argument("--out", type=Path, default=REPO / "reports" / "review_eval")
    parser.add_argument("--name", default="truth_derivation")
    parser.add_argument("--record", default="D-T8-PAIRING")
    args = parser.parse_args(argv)

    window_source = SplunkWindowSource(timeout_seconds=args.timeout_seconds)
    health = window_source.health()
    if not health.get("reachable"):
        raise RuntimeError("Splunk health did not confirm a reachable read-only source")
    source = SplunkTruthSource(window_source, partition_seconds=args.partition_seconds)

    derivation = derive_bots_truth(
        source.fetch_records, source.query_stats, entries=BOTS_ANSWER_KEY
    )
    source.census.distinct_ids = len(
        {event_id for item in derivation.items for event_id in item.event_ids}
    )
    benign_daily = (
        source.daily_source_counts(args.benign_index)
        if args.pairing == "cross_index_benign"
        else None
    )
    pairings = [
        pair_index(
            index,
            derivation,
            source,
            arm=args.pairing,
            margin_seconds=args.margin_seconds,
            benign_index=args.benign_index,
            benign_daily=benign_daily,
        )
        for index in BOTS_INDEXES
    ]

    manifest = derivation.to_dict()
    manifest_sha256 = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    embedder = PlatformEmbedder(task=Task.SENTENCE_SIMILARITY, dim=args.embed_dim, role=Role.QUERY)
    config_payload: dict[str, Any] = {
        "pairing_arm": args.pairing,
        "benign_index": args.benign_index,
        "margin_seconds": args.margin_seconds,
        "partition_seconds": args.partition_seconds,
        "timeout_seconds": args.timeout_seconds,
        "indexes": list(BOTS_INDEXES),
        "answer_key_entry_count": len(BOTS_ANSWER_KEY),
    }
    run_stamp = stamp_mod.build_stamp(
        repo=REPO,
        embedder_id=embedder.identity,
        model_digests={},
        config=config_payload,
        corpus_snapshot=f"real:bots-answer-key:{manifest_sha256}",
        policy=f"{args.record}; truth derivation with the {args.pairing} benign-pairing arm",
    )
    known_answer = selftest_mod.run_selftest(stamp_digest=run_stamp.digest)
    if not known_answer.passed:
        raise RuntimeError("known-answer self-test failed before any truth was reported")

    rows = build_rows(derivation, pairings)
    metrics = [
        report_mod.MetricRow(
            name="answer_key_entry_yield",
            value=_entry_yield(rows),
            n=len(derivation.receipts),
            denominator=len(derivation.receipts),
            can_fail="fails when declared entities cannot be independently located and reconciled",
        ),
        report_mod.MetricRow(
            name="usable_index_slice_yield",
            value=_slice_yield(rows),
            n=len(pairings),
            denominator=len(pairings),
            can_fail=(
                "fails when no pre-registered index yields a benign comparator under this arm"
            ),
        ),
    ]
    doc = report_mod.build_report(
        stamp=run_stamp,
        selftest=known_answer,
        metrics=metrics,
        rows=rows,
        recompute={
            "answer_key_entry_yield": _entry_yield,
            "usable_index_slice_yield": _slice_yield,
        },
        extra={
            "pairing_arm": args.pairing,
            "answer_key_entry_count": len(derivation.receipts),
            "derived_item_count": len(derivation.items),
            "dropped_entry_count": sum(r.status == "dropped" for r in derivation.receipts),
            "index_pairings": [pairing.to_dict() for pairing in pairings],
            "fetch_census": source.census.to_dict(),
            "truth_manifest_sha256": manifest_sha256,
            "raw_telemetry_persisted": False,
        },
    )
    # Into the run's own stamp directory, the review_eval_run.py convention. Writing straight
    # into reports/review_eval/ put the first hull run's manifest exactly over the committed
    # reports/review_eval/bots_truth_manifest.json; a stamp-named directory cannot.
    output_directory = (
        args.out if args.out.name == run_stamp.digest else args.out / run_stamp.digest
    )
    json_path, md_path = report_mod.write_report(doc, output_directory, args.name)
    # Beside its own report: a derivation is evidence for the run that produced it, and the
    # stamp in the report is what says which run that was.
    manifest_path = json_path.parent / "bots_truth_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            {
                "pairing_arm": args.pairing,
                "derived": len(derivation.items),
                "of": len(derivation.receipts),
                "paired_indexes": sum(pairing.paired for pairing in pairings),
                "of_indexes": len(pairings),
                "fetch_census": source.census.to_dict(),
                "report": str(json_path),
                "markdown": str(md_path),
                "manifest": str(manifest_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
