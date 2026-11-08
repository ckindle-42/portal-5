"""Score one held-out mixed-corpus review. Read-only Splunk, no anchor load, no review-store writes."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from portal.modules.security.core.review.funnel import (
    CHANNEL_SIMILAR,
    CHANNEL_UNUSUAL,
    FunnelPolicy,
)
from portal.modules.security.core.review.reference import load_reference
from portal.modules.security.core.review.service import (
    ReviewConfig,
    ReviewRequest,
    ReviewStore,
    run_review,
)
from portal.modules.security.core.review.window import (
    SourceSpec,
    SplunkWindowSource,
    WindowFetchError,
)
from portal.modules.security.core.review_eval.mixed import (
    PROOF,
    AttackLabel,
    HarnessResult,
    Provenance,
    WindowScore,
    WindowSpec,
    accept_window_count,
    bind_split,
    labels_from_attack_data,
    labels_from_episodes,
    observation_from_review,
    publish,
    score_window,
)

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HAYSTACK_NOTE = (
    "no reliable per-event label; concerns are false positives over activity treated as "
    "benign; not a source of true positives"
)


def _ident(value: str, what: str) -> str:
    if not _IDENT.fullmatch(value):
        raise ValueError(f"{what} must be a plain identifier, got {value!r}")
    return value


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor-corpus", required=True)
    parser.add_argument("--anchor-field", required=True)
    parser.add_argument("--anchor-key", action="append", default=[])
    parser.add_argument("--search-corpus", required=True)
    parser.add_argument("--search-field", required=True)
    parser.add_argument(
        "--label-source", choices=("data_yml", "orchestrator_episode"), required=True
    )
    parser.add_argument("--attack-data-root", type=Path)
    parser.add_argument("--publisher")
    parser.add_argument("--haystack-corpus")
    parser.add_argument("--haystack-sourcetype")
    parser.add_argument("--max-events", type=int, default=200)
    parser.add_argument("--min-events", type=int, default=1)
    parser.add_argument("--window-seconds", type=float, default=60.0)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--anchor-set-id", required=True)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--out", type=Path)
    return parser


class FieldWindow(SplunkWindowSource):
    """Product window export plus one indexed-field term. Still read-only."""

    def __init__(self, base: SplunkWindowSource, field: str, value: str, span: float) -> None:
        super().__init__(
            url=base.url,
            user=base.user,
            password=base.password,
            partition_seconds=max(int(span) + 1, 1),
            timeout_seconds=base.timeout_seconds,
            transport=base.transport,
        )
        self.item_field = field
        self.item_value = value

    def _base_search(self, source: SourceSpec) -> str:
        field = _ident(self.item_field, "field")
        return (
            f"search index={_quote(source.index)} sourcetype={_quote(source.sourcetype)} "
            f"{field}={_quote(self.item_value)}"
        )


def _rows(source: SplunkWindowSource, search: str) -> list[dict[str, Any]]:
    return [dict(row) for row in source.iter_post(search, 0.0, time.time() + 1.0)]


def _discover(
    source: SplunkWindowSource,
    index: str,
    field: str,
    max_events: int,
    min_events: int = 1,
) -> list[dict[str, Any]]:
    """Smallest indexed groups, from tsidx aggregates. No raw export."""
    index = _ident(index, "index")
    field = _ident(field, "field")
    search = (
        f"| tstats count min(_time) as earliest max(_time) as latest where index={index} "
        f"by {field} sourcetype | where count>={int(min_events)} AND count<={int(max_events)} "
        "| sort count | head 20"
    )
    found: list[dict[str, Any]] = []
    for row in _rows(source, search):
        key = str(row.get(field) or "")
        sourcetype = str(row.get("sourcetype") or "")
        if not key or not sourcetype:
            continue
        try:
            found.append(
                {
                    "key": key,
                    "sourcetype": sourcetype,
                    "count": int(str(row["count"])),
                    "earliest": float(row["earliest"]),
                    "latest": float(row["latest"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return found


def _count(
    source: SplunkWindowSource, index: str, sourcetype: str, start: float, end: float
) -> int:
    search = f"search index={_ident(index, 'index')} sourcetype={_quote(sourcetype)} | stats count"
    rows = list(source.iter_post(search, start, end))
    if len(rows) != 1 or "count" not in rows[0]:
        raise ValueError(f"stats count failed for {index} {sourcetype}")
    return int(str(rows[0]["count"]))


def _one_alpha(reference: Any, channel: str) -> float:
    values = {
        float(item.alpha)
        for item in reference.calibrations.items.values()
        if item.channel == channel
    }
    if len(values) != 1:
        raise ValueError(f"{channel} alpha is not a single fitted value: {sorted(values)}")
    return values.pop()


def _embedder_id(reference: Any) -> str:
    values = sorted(
        {
            str(item.embedder_id)
            for item in reference.calibrations.items.values()
            if item.embedder_id
        }
    )
    if not values:
        return "none"
    return values[0] if len(values) == 1 else ",".join(values)


def _policy(reference: Any) -> tuple[ReviewConfig, float, float]:
    unusual = _one_alpha(reference, CHANNEL_UNUSUAL)
    similar = _one_alpha(reference, CHANNEL_SIMILAR)
    levels = tuple(
        sorted(
            {
                str(item.level)
                for item in reference.calibrations.items.values()
                if item.channel == CHANNEL_UNUSUAL
            }
        )
    )
    if not levels:
        raise ValueError("reference has no unusual calibration")
    config = ReviewConfig(policy=FunnelPolicy(unusual, similar, levels))
    return config, unusual, similar


def _item_id(publisher: str, test_id: str) -> str:
    from scripts.corpus_reingest import p5_item_id

    return p5_item_id(publisher, test_id)


def _catalog(args: argparse.Namespace) -> tuple[AttackLabel, ...]:
    if args.label_source != "data_yml":
        return ()
    if args.attack_data_root is None or not args.publisher:
        raise ValueError("data_yml labels need --attack-data-root and --publisher")
    return labels_from_attack_data(
        args.attack_data_root,
        corpus=args.search_corpus,
        publisher=args.publisher,
        item_id=_item_id,
    )


def _attack_label(
    args: argparse.Namespace, row: dict[str, Any], catalog: Sequence[AttackLabel]
) -> AttackLabel:
    start = float(row["earliest"])
    end = float(row["latest"])
    if args.label_source == "orchestrator_episode":
        label = labels_from_episodes(
            args.search_corpus,
            ({"episode_id": row["key"], "start": start, "end": end},),
        )[0]
        return label
    key = f"{args.search_corpus}/{row['key']}"
    match = next((item for item in catalog if item.dataset_key == key), None)
    if match is None:
        raise ValueError(f"{key} has no data.yml technique")
    return AttackLabel(
        corpus=args.search_corpus,
        dataset_key=key,
        techniques=match.techniques,
        start=start,
        end=end,
        label_source="data_yml",
    )


def _window_for(
    row: dict[str, Any], corpus: str, role: str, max_events: int, note: str
) -> tuple[WindowSpec, float]:
    start = float(row["earliest"])
    end = float(row["latest"]) + 1.0
    if end <= start:
        end = start + 1.0
    spec = WindowSpec(
        corpus=corpus,
        dataset_key=f"{corpus}/{row['key']}",
        start=start,
        end=end,
        sourcetypes=(str(row["sourcetype"]),),
        role=role,
        max_events=max_events,
        note=note,
    )
    return spec, end - start


def _review(
    source: SplunkWindowSource,
    spec: WindowSpec,
    config: ReviewConfig,
    reference: Any,
    environment: str,
) -> Any:
    store = ReviewStore()
    try:
        request = ReviewRequest(
            sources=(SourceSpec(spec.corpus, spec.sourcetypes[0]),),
            start=spec.start,
            end=spec.end,
            environment_id=environment,
            config=config,
        )
        return run_review(
            request,
            source=source,
            embedder=None,
            index=None,
            reference=reference,
            config=config,
            judge=None,
            store=store,
        )
    finally:
        store.close()


def _score_attack(
    base: SplunkWindowSource,
    args: argparse.Namespace,
    config: ReviewConfig,
    reference: Any,
    catalog: Sequence[AttackLabel],
) -> tuple[WindowSpec, Any, AttackLabel, list[dict[str, str]]]:
    skipped: list[dict[str, str]] = []
    for row in _discover(
        base, args.search_corpus, args.search_field, args.max_events, args.min_events
    ):
        accept_window_count(int(row["count"]), args.max_events)
        try:
            label = _attack_label(args, row, catalog)
        except ValueError as exc:
            skipped.append({"key": str(row["key"]), "reason": str(exc)})
            continue
        note = f"label_source={label.label_source}; techniques={','.join(label.techniques) or 'episode'}"
        spec, span = _window_for(row, args.search_corpus, "attack", args.max_events, note)
        reader = FieldWindow(base, args.search_field, str(row["key"]), span)
        try:
            result = _review(reader, spec, config, reference, args.environment)
        except (ValueError, WindowFetchError) as exc:
            skipped.append({"key": str(row["key"]), "reason": str(exc)})
            continue
        return spec, result, label, skipped
    raise ValueError(f"no reviewable attack window at or under {args.max_events} events")


def _haystack_row(source: SplunkWindowSource, args: argparse.Namespace) -> dict[str, Any]:
    index = _ident(str(args.haystack_corpus), "index")
    sourcetype = str(args.haystack_sourcetype)
    rows = _rows(
        source,
        f"| tstats min(_time) as earliest where index={index} sourcetype={_quote(sourcetype)}",
    )
    if not rows or rows[0].get("earliest") in (None, ""):
        raise ValueError(f"no events in {index} {sourcetype}")
    start = float(rows[0]["earliest"])
    span = float(args.window_seconds)
    while span >= 1.0:
        end = start + span
        count = _count(source, index, sourcetype, start, end)
        if args.min_events <= count <= args.max_events:
            accept_window_count(count, args.max_events)
            return {
                "key": f"haystack-{int(start)}-{int(end)}",
                "sourcetype": sourcetype,
                "count": count,
                "earliest": start,
                "latest": end - 1.0,
            }
        span = span / 10.0 if span > 10.0 else span - 1.0
    raise ValueError(f"no haystack slice of {index} fits max_events {args.max_events}")


def _anchor_keys(
    args: argparse.Namespace,
    search_key: str,
    catalog: Sequence[AttackLabel],
    discovered: Sequence[dict[str, Any]],
) -> tuple[str, ...]:
    if args.anchor_key:
        return tuple(args.anchor_key)
    for label in catalog:
        if label.dataset_key != search_key:
            return (label.dataset_key,)
    for row in discovered:
        key = f"{args.anchor_corpus}/{row['key']}"
        if key != search_key:
            return (key,)
    raise ValueError("pass --anchor-key; this run has no disjoint anchor dataset to declare")


def _source(timeout: float) -> SplunkWindowSource:
    return SplunkWindowSource(timeout_seconds=timeout)


def execute(args: argparse.Namespace) -> dict[str, Any]:
    """One live scoring pass. The anchor index is not attached; the split is still enforced."""
    reference = load_reference()
    config, alpha_unusual, alpha_similar = _policy(reference)
    base = _source(args.timeout)
    catalog = _catalog(args)
    spec, result, label, skipped = _score_attack(base, args, config, reference, catalog)
    windows = [spec]
    labels = [label]
    results = [result]
    benign = [0]
    if args.haystack_corpus and args.haystack_sourcetype:
        row = _haystack_row(base, args)
        haystack, span = _window_for(
            row,
            str(args.haystack_corpus),
            "haystack",
            args.max_events,
            f"{args.haystack_corpus}: {_HAYSTACK_NOTE}",
        )
        reader = SplunkWindowSource(
            url=base.url,
            user=base.user,
            password=base.password,
            partition_seconds=max(int(span) + 1, 1),
            timeout_seconds=base.timeout_seconds,
        )
        results.append(_review(reader, haystack, config, reference, args.environment))
        windows.append(haystack)
        labels.append(None)
        benign.append(None)
    policy = str(results[0].fingerprint.get("policy") or "")
    if not policy:
        raise ValueError("review result has no policy stamp")
    anchor_rows = _discover(base, args.anchor_corpus, args.anchor_field, args.max_events)
    anchor_keys = _anchor_keys(args, spec.dataset_key, catalog, anchor_rows)
    scored = _scores(windows, results, labels, benign)
    document = publish(
        _provenance(
            args, windows, anchor_keys, scored, policy, alpha_unusual, alpha_similar, reference
        )
    )
    document["skipped"] = skipped
    document["review_fingerprints"] = [dict(item.fingerprint) for item in results]
    document["anchor_index_attached"] = False
    return document


def window_benign(window: WindowSpec, reviewed: Any, declared: int | None) -> int:
    if window.role == "haystack":
        return int(reviewed.fingerprint["fetched_events"])
    return 0 if declared is None else declared


def _scores(
    windows: Sequence[WindowSpec],
    results: Sequence[Any],
    labels: Sequence[AttackLabel | None],
    benign: Sequence[int | None],
) -> tuple[WindowScore, ...]:
    scores: list[WindowScore] = []
    for window, reviewed, attack, declared in zip(windows, results, labels, benign, strict=True):
        observed = observation_from_review(
            reviewed, benign_events=window_benign(window, reviewed, declared)
        )
        accept_window_count(observed.events_reviewed, window.max_events)
        scores.append(score_window(window, () if attack is None else (attack,), observed))
    return tuple(scores)


def _search_corpus(args: argparse.Namespace) -> str:
    names = [str(args.search_corpus)]
    if args.haystack_corpus and args.haystack_corpus not in names:
        names.append(str(args.haystack_corpus))
    return ",".join(names)


def _provenance(
    args: argparse.Namespace,
    windows: Sequence[WindowSpec],
    anchor_keys: Sequence[str],
    scores: tuple[WindowScore, ...],
    policy: str,
    alpha_unusual: float,
    alpha_similar: float,
    reference: Any,
) -> HarnessResult:
    eval_keys = tuple(window.dataset_key for window in windows)
    bind_split(anchor_keys, eval_keys)
    provenance = Provenance(
        anchor_corpus=str(args.anchor_corpus),
        search_corpus=_search_corpus(args),
        windows=tuple(windows),
        anchor_set_id=str(args.anchor_set_id),
        embedder_id=_embedder_id(reference),
        policy=policy,
        alpha_unusual=alpha_unusual,
        alpha_similar=alpha_similar,
        type_dataset_keys=tuple(sorted(set(anchor_keys))),
        eval_dataset_keys=tuple(sorted(set(eval_keys))),
        disjoint_proof=PROOF,
        anchor_index_attached=False,
    )
    return HarnessResult(provenance=provenance, scores=scores)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        document = execute(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
