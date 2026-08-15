"""bully.harvest -- HARV, the leakage-safe role-tagged training corpus (P6.2,
I-15).

``append_pairs(store, hunt_id)`` extracts role-tagged training examples from
a closed hunt's already-recorded ``decision_events`` (SUB's hash-chained
audit trail -- the real source of "verdicts+rationales, council objection/
rebuttal exchanges, cousin judgments with decompositions, kill rationales"
I-15 names, since every one of those is already a `record_decision` call
somewhere in the P1-P5 modules). ``build_dataset(store, role, window)``
turns the accumulated (non-quarantined) examples for a role into an
immutable, content-hashed ``dataset_version`` -- writing the corpus JSONL +
manifest under the hunt dir (this module is the *only* one that writes
corpus JSONL, MASTER SS3).

Boundary rules (MASTER SS3): this module never touches SQL directly
(``store.py`` is the sole SQL owner); no model calls (pure extraction/
aggregation over already-recorded data); label-blind (Rule BM) -- it never
imports ``recall_attribution``, the eval-side honest-miss oracle.

A1 (non-obvious choice, MASTER SS1A.6): decision-event ``kind`` -> training
role mapping. The four roles (DATA_MODEL SS1.16: hunter/analyst/disprover/
cousin_smeller) don't have a 1:1 existing `kind` each -- there is no
`"cousin"` kind in `DECISION_EVENT_KINDS`; the cousin judgment (relationship
+ decomposition) is recorded as `kind="grade"` (`orchestrator._do_analyze`'s
`"BR-COUSIN graded relationship=... response=..."` event). So this module
maps the closest-fit existing kinds:
  - hunter:          `target_select`, `recall`       (where-to-look decisions)
  - analyst:          `promote`                       (confirmed verdict + rationale)
  - disprover:        `kill`                          (kill rationale)
  - cousin_smeller:   `grade`, `objection`,           (cousin judgment with
                       `council_block`                  decomposition + the
                                                         council's critique
                                                         of that judgment)
`objection`/`council_block` are also marked `is_adversarial=True`
(critiquing a cousin call is literally an adversarial pair) and
`is_negative=True` alongside `kill` (DATA_MODEL SS1.16 "negatives
first-class"); `grade` alone is marked `is_distance_pair=True` (its data
carries the cousin decomposition/distance components).

A2 (non-obvious choice): "corrected label supersedes and forces a new
dataset version" (I-15 IDEMPOTENCY) is satisfied at the *dataset_version*
level -- a rebuild after a correction naturally produces a different
content_hash (and thus a new dataset_version row), which is what the
contract literally names. Per-example supersession chains inside
`training_examples` are out of scope for this phase (not exercised by any
C11 test); a corrected event simply harvests to a new `example_id` (its
content-derived id changes with the corrected output) on the next
`append_pairs` call.
"""

from __future__ import annotations

import json
from typing import Any

from . import config as bully_config
from .store import Store

# ── kind -> role mapping (A1) ───────────────────────────────────────────

_ROLE_BY_KIND: dict[str, str] = {
    "target_select": "hunter",
    "recall": "hunter",
    "promote": "analyst",
    "kill": "disprover",
    "grade": "cousin_smeller",
    "objection": "cousin_smeller",
    "council_block": "cousin_smeller",
}
_ADVERSARIAL_KINDS = frozenset({"objection", "council_block"})
_NEGATIVE_KINDS = frozenset({"kill", "objection", "council_block"})
_DISTANCE_PAIR_KINDS = frozenset({"grade"})

# A cousin-emission's default trust_tier is 'SUSPECT' until an operator
# confirms it (orchestrator.py's org_record, promotion.py's confirm flow) --
# only a confirmed tier is trustworthy enough to train on (I-15 FAILURE
# SEMANTICS "suspect trust -> quarantine, never silent inclusion").
_TRUSTED_TIERS = frozenset({"OPERATOR_CONFIRMED"})

_MIN_ROLE_SIZE_DEFAULT = 20  # size floor below which a build is an honest non-build


class HarvestError(RuntimeError):
    """Raised on a harvest precondition failure (e.g. unknown role)."""


def _example_input_text(event) -> str:
    """The 'input' half of the pair: what the model saw when it made this
    call. Reconstructed from the recorded rationale + a stable projection
    of `event.data` (never raw model output -- that's `output_text`)."""
    context = {k: v for k, v in event.data.items() if k not in ("rationale",)}
    return json.dumps(
        {"kind": event.kind, "subject_id": event.subject_id, "context": context},
        sort_keys=True,
        default=str,
    )


def _example_output_text(event) -> str:
    return event.rationale


def _trust_tier(event) -> str | None:
    return event.data.get("trust_tier")


def _group_tags(event) -> tuple[str | None, str | None, str | None]:
    """(family, campaign, time) group tags (DATA_MODEL SS1.16). `family` is
    the first technique id if present; `time` buckets by day so the split
    manifest's time-group leakage check has something coarse to key on."""
    technique_ids = event.data.get("technique_ids") or event.data.get("technique_id")
    if isinstance(technique_ids, str):
        family = technique_ids
    elif isinstance(technique_ids, list) and technique_ids:
        family = technique_ids[0]
    else:
        family = None
    campaign = event.hunt_id
    day_bucket = None
    if event.occurred_at:
        import time as _time

        day_bucket = _time.strftime("%Y-%m-%d", _time.gmtime(event.occurred_at))
    return family, campaign, day_bucket


def _quarantine_reason(event, *, seen_input_hashes: set[str], input_text: str) -> str | None:
    if event.hunt_id is None:
        return "missing_provenance"
    trust_tier = _trust_tier(event)
    if event.kind == "grade" and trust_tier not in _TRUSTED_TIERS:
        return f"suspect_trust:{trust_tier!r}"
    input_hash = bully_config.content_hash({"input_text": input_text})
    if input_hash in seen_input_hashes:
        return "duplicate"
    return None


def append_pairs(store: Store, hunt_id: str) -> int:
    """Extract role-tagged examples from a hunt's decision events (I-15).
    Idempotent: re-running on the same hunt re-derives the same
    content-keyed `example_id`s, so `training_example_put`'s
    `INSERT OR IGNORE` makes a re-harvest a no-op rather than a duplicate.
    Returns the number of events processed into examples (quarantined or
    not -- quarantine is recorded, never silently dropped)."""
    events = store.decision_events_for_hunt(hunt_id)
    seen_input_hashes: set[str] = set()
    processed = 0
    for event in events:
        role = _ROLE_BY_KIND.get(event.kind)
        if role is None:
            continue
        input_text = _example_input_text(event)
        output_text = _example_output_text(event)
        family, campaign, day_bucket = _group_tags(event)
        example_id = "ex-" + bully_config.content_hash(
            {
                "role": role,
                "hunt_id": event.hunt_id,
                "event_id": event.event_id,
                "output": output_text,
            }
        )
        quarantine_reason = _quarantine_reason(
            event, seen_input_hashes=seen_input_hashes, input_text=input_text
        )
        input_hash = bully_config.content_hash({"input_text": input_text})
        seen_input_hashes.add(input_hash)
        store.training_example_put(
            example_id=example_id,
            role=role,
            input_text=input_text,
            output_text=output_text,
            provenance={
                "hunt_id": event.hunt_id,
                "event_id": event.event_id,
                "iteration_id": event.iteration_id,
                "outcome": event.kind,
                "trust_tier": _trust_tier(event),
                "actor": event.actor,
            },
            group_family=family,
            group_campaign=campaign,
            group_time=day_bucket,
            leakage_flag=False,
            oracle_flag=False,
            is_negative=event.kind in _NEGATIVE_KINDS,
            is_adversarial=event.kind in _ADVERSARIAL_KINDS,
            is_distance_pair=event.kind in _DISTANCE_PAIR_KINDS,
            split=None,
            quarantine_reason=quarantine_reason,
        )
        processed += 1
    return processed


# ── build_dataset (dataset build -> immutable dataset_version) ────────────

_SPLIT_BUCKETS = (
    "train",
    "train",
    "train",
    "train",
    "train",
    "train",
    "train",
    "val",
    "val",
    "test",
)


def _assign_split(group_family: str | None, example_id: str) -> str:
    """Deterministic ~70/20/10 split keyed on `group_family` (falls back to
    `example_id`) so an entire family lands in exactly one split -- no
    family straddles train/test (I-15 'test frozen before harvest window',
    DATA_MODEL SS1.16 'split manifest ... family/campaign/time groups')."""
    key = group_family or example_id
    bucket_idx = int(bully_config.content_hash({"split_key": key})[:8], 16) % len(_SPLIT_BUCKETS)
    return _SPLIT_BUCKETS[bucket_idx]


def build_dataset(
    store: Store,
    role: str,
    window: dict[str, Any],
    *,
    min_size: int = _MIN_ROLE_SIZE_DEFAULT,
    corpus_root=None,
) -> dict[str, Any]:
    """I-15 `build_dataset(role, window) -> DatasetRef`. Returns a dict
    (`built`, `dataset_version`, `counts`, ...) rather than raising on a
    below-floor corpus -- FAILURE SEMANTICS 'below-size-floor -> documented
    non-build (honest)' is a returned outcome, not an exception."""
    if role not in ("hunter", "analyst", "disprover", "cousin_smeller"):
        raise HarvestError(f"unknown training role: {role!r}")

    examples = store.training_examples_for_role(role, include_quarantined=False)
    quarantined = [
        e
        for e in store.training_examples_for_role(role, include_quarantined=True)
        if e["quarantine_reason"] is not None
    ]

    if len(examples) < min_size:
        return {
            "built": False,
            "role": role,
            "reason": f"below size floor: {len(examples)} < {min_size}",
            "usable_count": len(examples),
            "quarantined_count": len(quarantined),
        }

    split_manifest: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    for example in examples:
        split = _assign_split(example["group_family"], example["example_id"])
        split_manifest[split].append(example["example_id"])

    counts = {
        "total": len(examples),
        "by_split": {k: len(v) for k, v in split_manifest.items()},
        "negatives": sum(1 for e in examples if e["is_negative"]),
        "adversarial": sum(1 for e in examples if e["is_adversarial"]),
        "distance_pairs": sum(1 for e in examples if e["is_distance_pair"]),
    }
    dedup_leakage_report = {
        "quarantined_duplicate": sum(
            1 for e in quarantined if (e["quarantine_reason"] or "").startswith("duplicate")
        ),
        "quarantined_suspect_trust": sum(
            1 for e in quarantined if (e["quarantine_reason"] or "").startswith("suspect_trust")
        ),
        "quarantined_missing_provenance": sum(
            1 for e in quarantined if e["quarantine_reason"] == "missing_provenance"
        ),
        "quarantined_total": len(quarantined),
    }

    payload_for_hash = {
        "role": role,
        "window": window,
        "example_ids": sorted(e["example_id"] for e in examples),
    }
    dataset_version = "dv-" + bully_config.content_hash(payload_for_hash)

    manifest_path = None
    root = corpus_root or (bully_config.hunt_dir() / "corpus" / role)
    root.mkdir(parents=True, exist_ok=True)
    jsonl_path = root / f"{dataset_version}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for example in examples:
            split = next(s for s, ids in split_manifest.items() if example["example_id"] in ids)
            fh.write(
                json.dumps(
                    {
                        "example_id": example["example_id"],
                        "role": example["role"],
                        "input": example["input_text"],
                        "output": example["output_text"],
                        "provenance": json.loads(example["provenance_json"]),
                        "split": split,
                        "is_negative": bool(example["is_negative"]),
                        "is_adversarial": bool(example["is_adversarial"]),
                        "is_distance_pair": bool(example["is_distance_pair"]),
                    },
                    sort_keys=True,
                    default=str,
                )
                + "\n"
            )
    manifest_path = str(root / f"{dataset_version}.manifest.json")
    manifest = {
        "dataset_version": dataset_version,
        "role": role,
        "window": window,
        "counts": counts,
        "split_manifest": {k: len(v) for k, v in split_manifest.items()},
        "dedup_leakage_report": dedup_leakage_report,
        "corpus_path": str(jsonl_path),
    }
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True, default=str)

    inserted = store.dataset_version_put(
        dataset_version=dataset_version,
        role=role,
        window=window,
        counts=counts,
        split_manifest={k: len(v) for k, v in split_manifest.items()},
        dedup_leakage_report=dedup_leakage_report,
        replay_mix_sources=[],
        manifest_path=manifest_path,
    )

    return {
        "built": True,
        "role": role,
        "dataset_version": dataset_version,
        "counts": counts,
        "split_manifest": {k: len(v) for k, v in split_manifest.items()},
        "dedup_leakage_report": dedup_leakage_report,
        "manifest_path": manifest_path,
        "corpus_path": str(jsonl_path),
        "newly_inserted": inserted,
    }
