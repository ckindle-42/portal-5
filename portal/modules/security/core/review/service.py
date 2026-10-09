"""review.service -- the only harness entry point into the synchronous product path."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import defense, verdicts
from .contracts import ReviewResult, StageReceipt, Verdict, to_plain
from .intake import IntakeResult, build_window_units
from .knowledge import AnchorCard, AnchorIndex, Embedder
from .pipeline import (
    JudgeFn,
    Reference,
    ReviewConfig,
    build_reference,
    review_window,
)
from .reference import load_reference, recalibrate, reference_path, save_reference, stale
from .runs import RunContext, RunRecord, RunStore, RunWorker
from .store import ReviewStore, StoredConcern
from .wall import assert_label_free
from .window import SourceSpec, WindowSource

DEFAULT_READER: JudgeFn | None = None
DEFAULT_STORE = ReviewStore()


def _configured_embedding_dim() -> int:
    """Return the configured EG2 Matryoshka dimension for the review identity."""
    from portal.platform.embedding.contract import MRL_DIMS, NATIVE_DIM

    raw = os.environ.get("PORTAL5_REVIEW_EMBEDDING_DIM")
    if raw is None:
        return NATIVE_DIM
    try:
        dimension = int(raw)
    except ValueError:
        raise ValueError(
            f"PORTAL5_REVIEW_EMBEDDING_DIM must be one of {MRL_DIMS}, got {raw!r}"
        ) from None
    if dimension not in MRL_DIMS:
        raise ValueError(f"PORTAL5_REVIEW_EMBEDDING_DIM must be one of {MRL_DIMS}, got {dimension}")
    return dimension


@dataclass(frozen=True)
class ReviewRequest:
    sources: Sequence[SourceSpec]
    start: float
    end: float
    environment_id: str
    config: ReviewConfig


def disjoint_calibration_slice(
    benign: IntakeResult, excluded_event_ids: set[str] | frozenset[str]
) -> IntakeResult:
    """Remove every calibration unit that contains an event used by a verdict anchor."""
    excluded = set(excluded_event_ids)
    units = [unit for unit in benign.units if not excluded.intersection(unit.event_ids)]
    event_ids = {event_id for unit in units for event_id in unit.event_ids}
    removed = len(benign.units) - len(units)
    receipts = list(benign.receipts)
    receipts.append(
        StageReceipt(
            name="knowledge.calibration_null",
            examined=len(benign.units),
            resolved=len(units),
            note=f"excluded {removed} units overlapping verdict-derived benign anchor events",
        )
    )
    return IntakeResult(
        units=units,
        events={key: value for key, value in benign.events.items() if key in event_ids},
        receipts=receipts,
        blind_sources=list(benign.blind_sources),
    )


def _combined_index(
    static_index: AnchorIndex | None,
    learned_cards: Sequence[AnchorCard],
    embedder: Embedder | None,
) -> AnchorIndex | None:
    if not learned_cards:
        return static_index
    if embedder is None:
        raise ValueError("stored verdict anchors require their configured embedder")
    cards: list[AnchorCard] = []
    seen: set[str] = set()
    for card in [*(static_index.cards if static_index is not None else []), *learned_cards]:
        if card.anchor_id not in seen:
            cards.append(card)
            seen.add(card.anchor_id)
    return AnchorIndex.build(cards, embedder)


def run_review(  # noqa: PLR0912 -- this is the sole path orchestration boundary.
    request: ReviewRequest,
    *,
    source: WindowSource,
    embedder: Embedder | None,
    index: AnchorIndex | None,
    reference: Reference,
    config: ReviewConfig | None = None,
    judge: JudgeFn | None = DEFAULT_READER,
    store: ReviewStore | None = None,
    as_of: float | None = None,
    calibration_window: IntakeResult | None = None,
    defense_search: defense.ReadOnlySearcher | None = None,
    run_id: str | None = None,
    cancel: Callable[[], None] | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> ReviewResult:
    """Run the deterministic default path, with replayable verdict knowledge and write-back."""
    if request.end <= request.start:
        raise ValueError("request.end must be greater than request.start")
    chosen_config = config or request.config
    active_store = store if store is not None else DEFAULT_STORE

    if index is not None:
        if embedder is None:
            raise ValueError("an anchor index requires its embedder")
        if index.embedder_id != embedder.identity:
            raise ValueError("anchor index and embedder identities disagree")

    learned_rows = active_store.anchors(as_of=as_of)
    learned_cards = verdicts.cards_from_store(active_store, as_of=as_of)
    combined_index = _combined_index(index, learned_cards, embedder)
    chosen_reference = reference
    calibration_source = calibration_window or reference.calibration_window
    calibration_slice: IntakeResult | None = None

    if learned_cards:
        if calibration_source is None:
            raise ValueError(
                "stored verdict anchors require the recorded benign calibration window"
            )
        if embedder is None or combined_index is None:
            raise ValueError("stored verdict anchors require an embedder for recalibration")
        benign_event_ids = {
            str(event_id)
            for anchor in learned_rows
            if anchor.malice == "benign"
            for event_id in anchor.record.get("event_ids", [])
        }
        calibration_slice = disjoint_calibration_slice(calibration_source, benign_event_ids)
        chosen_reference = build_reference(
            calibration_slice,
            policy=chosen_config.policy,
            index=combined_index,
            embedder=embedder,
            environment_id=request.environment_id,
            basis=reference.basis,
        )

    if combined_index is not None:
        if embedder is None:
            raise ValueError("an anchor index requires its embedder")
        stale_keys = stale(chosen_reference, embedder.identity)
        if stale_keys:
            raise ValueError(f"reference has stale embedder calibrations: {stale_keys}")

    batch = source.fetch(request.sources, request.start, request.end)
    for source_id, records in batch.records_by_source.items():
        for ordinal, record in enumerate(records):
            assert_label_free(record, where=f"review-service:{source_id}:{ordinal}")

    intake = build_window_units(batch.records_by_source)
    notes = list(batch.degraded)
    intake.receipts.append(
        StageReceipt(
            name="window.fetch",
            examined=batch.expected,
            resolved=batch.fetched,
            note="; ".join(notes),
        )
    )
    result = review_window(
        intake,
        reference=chosen_reference,
        index=combined_index,
        embedder=embedder,
        config=chosen_config,
        judge=judge,
        run_id=run_id,
        cancel=cancel,
        progress=progress,
    )
    searcher = defense_search or defense.source_searcher(source)
    defense_receipt, defense_errors = defense.apply_to_result(
        result,
        intake,
        request_start=request.start,
        request_end=request.end,
        searcher=searcher,
    )
    result.receipts.append(defense_receipt)
    if defense_errors:
        result.degraded.append(
            f"defense searches had {defense_errors} error(s); affected responses are INDETERMINATE"
        )
    result.degraded.extend(notes)
    if calibration_slice is not None and calibration_source is not None:
        null_receipt = calibration_slice.receipts[-1]
        result.receipts.append(null_receipt)

    source_digest = hashlib.sha256(
        json.dumps(sorted(spec.source_id for spec in request.sources)).encode("utf-8")
    ).hexdigest()[:16]
    result.fingerprint.update(
        {
            "environment": request.environment_id,
            "window": f"{request.start:.6f}:{request.end:.6f}",
            "sources": source_digest,
            "expected_events": str(batch.expected),
            "fetched_events": str(batch.fetched),
            "knowledge_as_of": "current" if as_of is None else f"{as_of:.6f}",
            "knowledge_anchors": str(len(learned_cards)),
        }
    )
    verdicts.persist_run(active_store, result, intake)
    return result


def record_verdict(
    concern_id: str,
    verdict: Verdict,
    *,
    actor: str,
    store: ReviewStore = DEFAULT_STORE,
    note: str = "",
    scripted: bool = False,
    at: float | None = None,
) -> verdicts.WriteBack:
    """Record an analyst verdict and write the resulting knowledge anchor back to the store."""
    return verdicts.record_verdict(
        store,
        concern_id,
        verdict,
        actor=actor,
        note=note,
        scripted=scripted,
        at=at,
    )


def queue(*, store: ReviewStore = DEFAULT_STORE, limit: int | None = None) -> list[StoredConcern]:
    """Return concerns awaiting an analyst verdict."""
    return store.queue() if limit is None else store.queue(limit=limit)


def contradictions(*, store: ReviewStore = DEFAULT_STORE) -> list[dict[str, object]]:
    """Return reversals and disagreements in the recorded review knowledge."""
    return verdicts.contradictions(store)


STALE_CALIBRATION_INSTRUCTION = (
    "Run `python -m portal.modules.security.core review doctor --fix` before starting a review."
)


def _runtime_root(review_dir: str | Path | None) -> Path:
    if review_dir is not None:
        return Path(review_dir).expanduser()
    configured = os.environ.get("PORTAL5_REVIEW_DIR")
    return Path(configured).expanduser() if configured else Path.home() / "AI_Output" / "review"


def _encode_request(request: ReviewRequest) -> dict[str, Any]:
    return {
        "sources": [
            {"index": item.index, "sourcetype": item.sourcetype} for item in request.sources
        ],
        "start": request.start,
        "end": request.end,
        "environment_id": request.environment_id,
        "config": {
            "policy": {
                "alpha_unusual": request.config.policy.alpha_unusual,
                "alpha_similar": request.config.policy.alpha_similar,
                "levels": list(request.config.policy.levels),
            },
            "suppress_benign": request.config.suppress_benign,
            "top_k_anchors": request.config.top_k_anchors,
            "judge_max": request.config.judge_max,
        },
    }


def _decode_request(payload: Mapping[str, Any]) -> ReviewRequest:
    from .funnel import FunnelPolicy

    raw_sources = payload.get("sources")
    raw_config = payload.get("config")
    if not isinstance(raw_sources, list) or not isinstance(raw_config, Mapping):
        raise ValueError("stored review request is malformed")
    raw_policy = raw_config.get("policy")
    if not isinstance(raw_policy, Mapping):
        raise ValueError("stored review request has no funnel policy")
    sources = [
        SourceSpec(str(row["index"]), str(row["sourcetype"]))
        for row in raw_sources
        if isinstance(row, Mapping) and "index" in row and "sourcetype" in row
    ]
    if len(sources) != len(raw_sources):
        raise ValueError("stored review request contains an invalid source")
    policy = FunnelPolicy(
        alpha_unusual=float(raw_policy["alpha_unusual"]),
        alpha_similar=float(raw_policy["alpha_similar"]),
        levels=tuple(str(level) for level in raw_policy["levels"]),
    )
    config = ReviewConfig(
        policy=policy,
        suppress_benign=str(raw_config.get("suppress_benign", "exact_only")),
        top_k_anchors=int(raw_config.get("top_k_anchors", 3)),
        judge_max=(
            int(raw_config["judge_max"]) if raw_config.get("judge_max") is not None else None
        ),
    )
    return ReviewRequest(
        sources=sources,
        start=float(payload["start"]),
        end=float(payload["end"]),
        environment_id=str(payload["environment_id"]),
        config=config,
    )


class ReviewRuntime:
    """Durable analyst-facing lifecycle around the sole ``run_review`` product path."""

    def __init__(
        self,
        *,
        source: WindowSource,
        embedder: Embedder | None,
        index: AnchorIndex | None,
        reference: Reference,
        config: ReviewConfig,
        environment_id: str,
        review_dir: str | Path | None = None,
        judge: JudgeFn | None = DEFAULT_READER,
        calibration_records_by_source: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
        splunk_health: Callable[[], Mapping[str, Any]] | None = None,
        reasoning_model_probe: Callable[[], Sequence[str]] | None = None,
    ) -> None:
        self.review_dir = _runtime_root(review_dir)
        self.review_dir.mkdir(parents=True, exist_ok=True)
        self.source = source
        self.embedder = embedder
        self.index = index
        self.reference = reference
        self.config = config
        self.environment_id = environment_id
        self.judge = judge
        self.splunk_health_probe = splunk_health
        self.reasoning_model_probe = reasoning_model_probe
        self._calibration_refresh_error: str | None = None
        self._calibration_path = self.review_dir / "calibration_slice.json"
        self.calibration_window = reference.calibration_window
        if calibration_records_by_source is not None:
            self._write_calibration_records(calibration_records_by_source)
            self.calibration_window = build_window_units(calibration_records_by_source)
        elif self._calibration_path.exists():
            raw = json.loads(self._calibration_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("recorded calibration slice must be a JSON object")
            self.calibration_window = build_window_units(raw)

        self.run_store = RunStore(self.review_dir / "runs.sqlite3")
        self.review_store = ReviewStore(self.review_dir / "review.sqlite3")
        self.interrupted_at_startup = self.run_store.mark_interrupted()
        self.worker = RunWorker(self.run_store, self._run_request)

    def _write_calibration_records(
        self, records: Mapping[str, Sequence[Mapping[str, Any]]]
    ) -> None:
        self._calibration_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._calibration_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(records, sort_keys=True, default=str), encoding="utf-8")
        temporary.replace(self._calibration_path)

    def close(self) -> None:
        self.run_store.close()
        self.review_store.close()

    def _stale_calibrations(self) -> list[str]:
        if self.embedder is None:
            return []
        return self.reference.calibrations.stale_for(self.embedder.identity)

    def start(self, request: ReviewRequest) -> str:
        stale_keys = self._stale_calibrations()
        stale_index = (
            self.index is not None
            and self.embedder is not None
            and self.index.embedder_id != self.embedder.identity
        )
        if stale_keys or stale_index:
            details = ", ".join(stale_keys) if stale_keys else "anchor index identity"
            raise ValueError(
                f"review refused: stale embedder calibration/index ({details}). "
                f"{STALE_CALIBRATION_INSTRUCTION}"
            )
        return self.worker.start(_encode_request(request))

    def status(self, run_id: str) -> RunRecord | None:
        return self.run_store.get(run_id)

    def result(self, run_id: str) -> dict[str, Any] | None:
        record = self.run_store.get(run_id)
        return record.result if record is not None else None

    def cancel(self, run_id: str) -> bool:
        return self.run_store.request_cancel(run_id)

    def verdict(
        self,
        concern_id: str,
        verdict: Verdict,
        *,
        actor: str,
        note: str = "",
    ) -> verdicts.WriteBack:
        writeback = record_verdict(
            concern_id,
            verdict,
            actor=actor,
            store=self.review_store,
            note=note,
        )
        self._refresh_reference_after_verdict()
        return writeback

    def queue(self, *, limit: int | None = None) -> list[StoredConcern]:
        return self.review_store.queue() if limit is None else self.review_store.queue(limit=limit)

    def explain(self, concern_id: str) -> dict[str, Any]:
        concern = self.review_store.get_concern(concern_id)
        if concern is None:
            raise ValueError(f"unknown concern {concern_id!r}")
        judge = concern.payload.get("judge") or {}
        claims = judge.get("claims") or [] if isinstance(judge, Mapping) else []
        cited_ids = {
            str(event_id)
            for claim in claims
            if isinstance(claim, Mapping)
            for event_id in claim.get("evidence_ids", [])
        }
        evidence = concern.payload.get("evidence") or []
        cited_ids.update(
            str(item["event_id"])
            for item in evidence
            if isinstance(item, Mapping) and item.get("event_id")
        )
        event_ids = sorted(cited_ids)
        stored_events = concern.record.get("evidence_events") or {}
        missing = [event_id for event_id in event_ids if event_id not in stored_events]
        if missing:
            raise ValueError(f"verbatim evidence text is unavailable for cited events: {missing}")
        return {
            "concern_id": concern_id,
            "claims": claims,
            "events": {event_id: stored_events[event_id] for event_id in event_ids},
        }

    def doctor(self, *, fix: bool = False) -> dict[str, Any]:
        fix_result: dict[str, Any] = {"attempted": fix, "applied": False}
        stale_before = self._stale_calibrations()
        index_stale = (
            self.index is not None
            and self.embedder is not None
            and self.index.embedder_id != self.embedder.identity
        )
        if fix and (stale_before or index_stale):
            try:
                if self.embedder is None:
                    raise ValueError("no configured embedder is available for re-projection")
                if self.calibration_window is None:
                    raise ValueError("recorded benign calibration slice is unavailable")
                cards: list[AnchorCard] = []
                seen: set[str] = set()
                source_cards = [
                    *(self.index.cards if self.index is not None else []),
                    *verdicts.cards_from_store(self.review_store),
                ]
                for card in source_cards:
                    if card.anchor_id not in seen:
                        cards.append(card)
                        seen.add(card.anchor_id)
                rebuilt_index = AnchorIndex.build(cards, self.embedder)
                if stale_before:
                    if not rebuilt_index.population:
                        raise ValueError("no stored anchor text is available to re-project")
                    self.reference = recalibrate(
                        self.reference,
                        benign=self.calibration_window,
                        policy=self.config.policy,
                        index=rebuilt_index,
                        embedder=self.embedder,
                        environment_id=self.environment_id,
                    )
                    save_reference(self.reference, review_dir=self.review_dir)
                self.index = rebuilt_index
                fix_result["applied"] = True
            except Exception as exc:  # noqa: BLE001 -- returned as explicit health evidence
                fix_result["error"] = f"{type(exc).__name__}: {exc}"

        after_stale = self._stale_calibrations()
        source_health = self._source_health()
        models, model_error = self._reasoning_models()
        latest = self.run_store.list(limit=1)
        calibrations = [
            {
                "key": key,
                "embedder_id": calibration.embedder_id,
                "stale": bool(
                    self.embedder is not None
                    and calibration.embedder_id
                    and calibration.embedder_id != self.embedder.identity
                ),
                "calibration_id": calibration.calibration_id,
            }
            for key, calibration in sorted(self.reference.calibrations.items.items())
        ]
        last_run = latest[0] if latest else None
        return {
            "embedder": {
                "identity": self.embedder.identity if self.embedder is not None else None,
                "calibrations": calibrations,
                "stale_calibrations": after_stale,
                "anchor_index_stale": index_stale and not bool(fix_result.get("applied")),
                "stale": bool(after_stale) or (index_stale and not bool(fix_result.get("applied"))),
            },
            "splunk": source_health,
            "reasoning_models": {"models": models, "error": model_error},
            "databases": {
                "runs": self.run_store.health(),
                "verdicts": self.review_store.health(),
            },
            "calibration_refresh_error": self._calibration_refresh_error,
            "last_run": (
                {
                    "run_id": last_run.run_id,
                    "status": last_run.status.value,
                    "progress": last_run.progress,
                    "updated_at": last_run.updated_at,
                }
                if last_run is not None
                else None
            ),
            "fix": fix_result,
        }

    def _refresh_reference_after_verdict(self) -> None:
        """Persist current-identity calibrations after new analyst knowledge arrives."""
        cards = verdicts.cards_from_store(self.review_store)
        if not cards or self.calibration_window is None or self.embedder is None:
            return
        try:
            index = _combined_index(self.index, cards, self.embedder)
            if index is None or not index.population:
                return
            benign_event_ids = {
                str(event_id)
                for anchor in self.review_store.anchors()
                if anchor.malice == "benign"
                for event_id in anchor.record.get("event_ids", [])
            }
            calibration_slice = disjoint_calibration_slice(
                self.calibration_window, benign_event_ids
            )
            self.reference = build_reference(
                calibration_slice,
                policy=self.config.policy,
                index=index,
                embedder=self.embedder,
                environment_id=self.environment_id,
                basis=self.reference.basis,
            )
            self.index = index
            save_reference(self.reference, review_dir=self.review_dir)
            self._calibration_refresh_error = None
        except Exception as exc:  # noqa: BLE001 -- verdict remains durable; doctor shows repair error
            self._calibration_refresh_error = f"{type(exc).__name__}: {exc}"

    def _source_health(self) -> dict[str, Any]:
        probe = self.splunk_health_probe or getattr(self.source, "health", None)
        if not callable(probe):
            return {"reachable": None, "indexes": {}, "error": "no Splunk health probe configured"}
        try:
            return dict(probe())
        except Exception as exc:  # noqa: BLE001 -- health reports unavailable dependency
            return {"reachable": False, "indexes": {}, "error": f"{type(exc).__name__}: {exc}"}

    def _reasoning_models(self) -> tuple[list[str], str | None]:
        if self.reasoning_model_probe is None:
            return [], "reasoning model probe is not configured"
        try:
            return sorted({str(model) for model in self.reasoning_model_probe()}), None
        except Exception as exc:  # noqa: BLE001 -- health reports unavailable dependency
            return [], f"{type(exc).__name__}: {exc}"

    def _run_request(self, payload: Mapping[str, Any], ctx: RunContext) -> Mapping[str, Any]:
        ctx.check_cancel()
        request = _decode_request(payload)
        result = run_review(
            request,
            source=self.source,
            embedder=self.embedder,
            index=self.index,
            reference=self.reference,
            config=request.config,
            judge=self.judge,
            store=self.review_store,
            calibration_window=self.calibration_window,
            run_id=ctx.run_id,
            cancel=ctx.check_cancel,
            progress=ctx.report,
        )
        ctx.report("complete", 1, 1)
        plain = to_plain(result)
        if not isinstance(plain, Mapping):
            raise TypeError("review result did not serialize to an object")
        return plain


def build_default_runtime(*, review_dir: str | Path | None = None) -> ReviewRuntime:
    """Build the host-native product runtime from durable review state and Portal services."""
    from portal.platform.embedding.contract import Role, Task

    from .embedding import PlatformEmbedder
    from .funnel import FunnelPolicy
    from .window import SplunkWindowSource

    root = _runtime_root(review_dir)
    root.mkdir(parents=True, exist_ok=True)
    environment_id = os.environ.get("PORTAL5_REVIEW_ENVIRONMENT_ID", "portal5_lab")
    config = ReviewConfig(
        policy=FunnelPolicy(
            alpha_unusual=0.2,
            alpha_similar=0.2,
            levels=("L2_ENTITY", "L3_CHAIN"),
        )
    )
    embedder = PlatformEmbedder(
        task=Task.SENTENCE_SIMILARITY,
        dim=_configured_embedding_dim(),
        role=Role.QUERY,
    )
    temporary_store = ReviewStore(root / "review.sqlite3")
    try:
        cards = verdicts.cards_from_store(temporary_store)
    finally:
        temporary_store.close()
    index = AnchorIndex.build(cards, embedder) if cards else None
    reference_file = reference_path(review_dir=root)
    calibration_path = root / "calibration_slice.json"
    if reference_file.is_file():
        reference = load_reference(review_dir=root)
    else:
        if not calibration_path.is_file():
            raise FileNotFoundError(
                f"review reference and recorded benign slice are missing under {root}"
            )
        raw = json.loads(calibration_path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("recorded benign calibration slice must be an object") from None
        reference = build_reference(
            build_window_units(raw),
            policy=config.policy,
            index=index,
            embedder=embedder,
            environment_id=environment_id,
        )
        save_reference(reference, review_dir=root)
    return ReviewRuntime(
        source=SplunkWindowSource(),
        embedder=embedder,
        index=index,
        reference=reference,
        config=config,
        environment_id=environment_id,
        review_dir=root,
        reasoning_model_probe=lambda: _probe_reasoning_models(),
    )


def _probe_reasoning_models() -> Sequence[str]:
    """Intersect configured reasoning seats with models currently served by host Ollama."""
    import httpx
    import yaml

    repo_root = Path(__file__).resolve().parents[5]
    config_path = repo_root / "config" / "backends.yaml"
    configuration = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    configured = {
        str(model["id"])
        for backend in configuration.get("backends", [])
        if isinstance(backend, Mapping) and backend.get("group") == "reasoning"
        for model in backend.get("models", [])
        if isinstance(model, Mapping) and model.get("id")
    }
    base_url = (
        os.environ.get("PORTAL_REVIEW_OLLAMA_URL")
        or os.environ.get("OLLAMA_URL")
        or "http://127.0.0.1:11434"
    ).rstrip("/")
    if "host.docker.internal" in base_url:
        base_url = base_url.replace("host.docker.internal", "localhost")
    response = httpx.get(f"{base_url}/api/tags", timeout=10.0)
    response.raise_for_status()
    payload = response.json()
    models = payload.get("models", []) if isinstance(payload, Mapping) else []
    installed = {
        str(model.get("name"))
        for model in models
        if isinstance(model, Mapping) and model.get("name")
    }
    return sorted(configured & installed)
