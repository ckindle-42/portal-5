"""bully.scoreboard_conformance -- runs must publish the instrument, not a proxy.

The corrected diagnosis. `scoreboard.py` is sound: three orthogonal axes
(catch / trust / discovery), where **trust is the correctness axis**, grounded
in real operator judgment via the BIN pipeline (`PROMOTED` ->
CONFIRMED_CORRECT, `KILLED`/`DISPROVED` -> CONFIRMED_WRONG), with a
`false_flag` mechanism keyed on live `known_state`, discovery zeroed on
`known_benign`, and I-10 failure semantics (absent data reports `None`, never
a faked zero). Discovery was never meant to encode correctness; trust already
does.

The failure was never in that design. It was in the REPORTING LAYER:

  - `scoreboard.update()` returns `catch_rate`, `trust_mean_rank`,
    `discovery_total`, `discovery_mean`, `false_flag_count`.
  - The R.6 run published a block *labelled* "scoreboard" containing
    `n_graded`, `n_anomalous_unclassified`, `n_similar`, `n_same`,
    `discovery_bubbled_rate`, `pyramid_level_distribution`.
  - **Overlap: zero fields.** `discovery_bubbled_rate` exists nowhere in
    `scoreboard.py`; it is `(n_anomalous + n_similar) / n_graded`, invented
    inline in the run script.

Worse, the run DID call `scoreboard.score_record()` per timeline -- receiving
`trust_class`, `trust_rank`, `false_flag`, `false_flag_kind`, `known_benign`,
`discovery_value`, `catch` -- and kept only `discovery_value` and `catch`,
discarding every field that could show the finding was wrong. It never called
`scoreboard.update()`, so `trust_mean_rank` and `false_flag_count` were never
computed. And it passed `candidate_state=None` / `known_benign=False`
hardcoded, feeding the correctness axis nulls by construction -- while
`store.scoreboard_records_for_hunt()` existed precisely to supply both from
the real BIN candidate rows and `known_state`.

So the pattern behind all five runs is not "a success function that cannot
fail". It is: **the instrumentation is sound and the reporting layer bypasses
it, publishing bespoke flattering ratios under the instrument's name.** Every
headline audited across this workstream (`anomalous_rate`,
`unknown_cousin_recall`, `discovery_bubbled_rate`) is an ad-hoc number from a
run script, not a module contract.

This module does one thing: make that structurally unrepeatable. It does NOT
add a fourth scoring path -- adding a parallel scorer beside the three-axis
one would repeat the "better organ beside the body" mistake this workstream
exists to end.

Pure compute over a run's published record (COLD). No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ALGORITHM_VERSION = "scoreboard-conformance-v1"

# The contract `scoreboard.update()` returns. A run publishing a block named
# "scoreboard" must publish THESE, not a proxy. Derived here as the literal
# contract; the CI check re-derives it from the module at reconcile time so
# it can never drift from the source.
SCOREBOARD_UPDATE_CONTRACT: tuple[str, ...] = (
    "hunt_id",
    "n_records",
    "catch_count",
    "catch_rate",
    "trust_mean_rank",
    "discovery_total",
    "discovery_mean",
    "false_flag_count",
)

# The per-record fields `scoreboard.score_record()` returns. A run that keeps
# only the flattering subset is how a failure becomes invisible.
SCORE_RECORD_CONTRACT: tuple[str, ...] = (
    "assessment_id",
    "relationship",
    "defense_response",
    "composite",
    "catch",
    "trust_class",
    "trust_rank",
    "discovery_value",
    "known_benign",
    "false_flag",
    "false_flag_kind",
)

# Fields whose absence means the correctness axis was never measured.
CORRECTNESS_FIELDS: tuple[str, ...] = ("trust_mean_rank", "false_flag_count")


@dataclass(frozen=True)
class ConformanceFinding:
    severity: str  # FAIL | WARN
    code: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "code": self.code, "detail": self.detail}


def _flatten(o: Any, path: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(o, dict):
        for k, v in o.items():
            p = f"{path}.{k}" if path else k
            out[p] = v
            out.update(_flatten(v, p))
    elif isinstance(o, list):
        for i, v in enumerate(o[:200]):
            out.update(_flatten(v, f"{path}[{i}]"))
    return out


def _leaf(flat: dict[str, Any], name: str) -> Any:
    """Match on LEAF key names -- run docs nest under `scoreboard.*` /
    `investigation.*`, and matching only top-level keys is precisely how an
    earlier draft of this guard missed R.6, the run it was written for."""
    for k, v in flat.items():
        if k.split(".")[-1] == name:
            return v
    return None


def _check_scoreboard_block(
    run_json: dict[str, Any], update_contract: tuple[str, ...]
) -> list[ConformanceFinding]:
    """1. A block named "scoreboard" must actually be the scoreboard contract."""
    findings: list[ConformanceFinding] = []
    sb = run_json.get("scoreboard")
    if not isinstance(sb, dict):
        return findings
    present = set(sb)
    required = set(update_contract)
    missing = required - present
    if len(present & required) == 0:
        findings.append(
            ConformanceFinding(
                "FAIL",
                "scoreboard_block_is_not_the_contract",
                f"block named 'scoreboard' shares ZERO fields with scoreboard.update(): "
                f"published={sorted(present)} contract={sorted(required)}",
            )
        )
    elif missing:
        findings.append(
            ConformanceFinding(
                "FAIL",
                "scoreboard_contract_incomplete",
                f"missing contract fields: {sorted(missing)}",
            )
        )
    return findings


def _check_correctness_axis_published(flat: dict[str, Any]) -> list[ConformanceFinding]:
    """2. The correctness axis must be present somewhere in the run."""
    findings: list[ConformanceFinding] = []
    for f in CORRECTNESS_FIELDS:
        if _leaf(flat, f) is None:
            findings.append(
                ConformanceFinding(
                    "FAIL",
                    "correctness_axis_not_published",
                    f"'{f}' absent: the run cannot report whether any finding was right",
                )
            )
    return findings


def _check_per_row_fields(rows: list[Any]) -> list[ConformanceFinding]:
    """3. Per-row records must retain the full score_record output, not a
    flattering subset (dropping trust_rank/false_flag hides failure)."""
    findings: list[ConformanceFinding] = []
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        got = set(rows[0])
        dropped = [
            f for f in ("trust_class", "trust_rank", "false_flag", "known_benign") if f not in got
        ]
        if dropped:
            findings.append(
                ConformanceFinding(
                    "FAIL",
                    "per_row_drops_correctness_fields",
                    f"per_row keeps {sorted(got)} but drops {dropped} from score_record()",
                )
            )
    return findings


def _check_trust_axis_not_nulled(rows: list[Any]) -> list[ConformanceFinding]:
    """4. The trust axis must be fed real inputs, not hardcoded nulls. If every
    record has candidate_state None AND known_benign False, the axis was
    wired to report nothing (store.scoreboard_records_for_hunt exists to
    supply both from BIN candidates and known_state)."""
    findings: list[ConformanceFinding] = []
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        states = [r.get("candidate_state") for r in rows if isinstance(r, dict)]
        benign = [r.get("known_benign") for r in rows if isinstance(r, dict)]
        if states and all(s is None for s in states) and benign and not any(benign):
            findings.append(
                ConformanceFinding(
                    "WARN",
                    "trust_axis_fed_nulls",
                    "every record has candidate_state=None and known_benign=False: "
                    "the correctness axis was fed nulls by construction",
                )
            )
    return findings


def _check_invented_headline(
    flat: dict[str, Any], update_contract: tuple[str, ...]
) -> list[ConformanceFinding]:
    """5. An invented headline ratio that is not a module contract field."""
    findings: list[ConformanceFinding] = []
    for k in flat:
        leafname = k.split(".")[-1]
        if leafname.endswith("_rate") and leafname not in update_contract and "scoreboard" in k:
            findings.append(
                ConformanceFinding(
                    "FAIL",
                    "invented_headline_metric",
                    f"'{k}' is published under scoreboard but is not a scoreboard contract field",
                )
            )
    return findings


def _check_ceiling_exceeded(flat: dict[str, Any]) -> list[ConformanceFinding]:
    """6. A declared ceiling that was exceeded, published anyway."""
    findings: list[ConformanceFinding] = []
    for k, v in flat.items():
        if k.endswith("_exceeded") and v is True:
            findings.append(
                ConformanceFinding(
                    "FAIL",
                    "ceiling_exceeded_not_failed",
                    f"{k} is True: a declared ceiling was exceeded and the run still published",
                )
            )
    return findings


def _check_perfect_precision(flat: dict[str, Any]) -> list[ConformanceFinding]:
    """7. Perfect precision is unfalsifiable unless negatives are proven present."""
    findings: list[ConformanceFinding] = []
    for k, v in flat.items():
        if (
            k.split(".")[-1].endswith("precision")
            and isinstance(v, (int, float))
            and not isinstance(v, bool)
            and float(v) >= 0.999
        ):
            findings.append(
                ConformanceFinding(
                    "FAIL",
                    "perfect_precision",
                    f"{k}={v}: precision 1.0 requires proven negatives in the population",
                )
            )
    return findings


def _check_recall_contradiction(flat: dict[str, Any]) -> list[ConformanceFinding]:
    """8. recall 1.0 beside recall ~0 in one file."""
    recalls = [
        (k, float(v))
        for k, v in flat.items()
        if "recall" in k.split(".")[-1] and isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    hi = [k for k, v in recalls if v >= 0.999]
    lo = [k for k, v in recalls if v <= 0.001]
    if hi and lo:
        return [
            ConformanceFinding(
                "FAIL",
                "recall_contradiction",
                f"recall 1.0 at {hi[:2]} beside recall 0.0 at {lo[:2]} in one run",
            )
        ]
    return []


def check_run(
    run_json: dict[str, Any],
    *,
    update_contract: tuple[str, ...] = SCOREBOARD_UPDATE_CONTRACT,
    record_contract: tuple[str, ...] = SCORE_RECORD_CONTRACT,
) -> list[ConformanceFinding]:
    """FAIL a run whose published metrics bypass the scoreboard contract, or
    whose headline contradicts the evidence in its own file."""
    del record_contract  # documents the contract this guard enforces (item 3); not parameterized
    flat = _flatten(run_json)
    rows = run_json.get("per_row") or run_json.get("rows") or []

    findings: list[ConformanceFinding] = []
    # A BLOCKED/INVALID run (TASK_BULLY_CORPUS_BED_V1 C.1: a run below the
    # haystack floor publishes INVALID and stops there) never graded
    # anything -- it has no scoreboard block, no per-row data, and no
    # correctness axis to publish, by construction, not by omission.
    # Requiring those fields anyway would make "refuse to score a sample
    # that isn't a real corpus" itself a conformance FAIL, which is exactly
    # backwards. The headline/ceiling/precision/recall checks still run:
    # they are naturally vacuous on an empty `flat`, and a BLOCKED run that
    # somehow DID publish a fabricated headline must still be caught.
    if str(run_json.get("plane") or "") in ("BLOCKED", "INVALID"):
        findings += _check_invented_headline(flat, update_contract)
        findings += _check_ceiling_exceeded(flat)
        findings += _check_perfect_precision(flat)
        findings += _check_recall_contradiction(flat)
        return findings
    findings += _check_scoreboard_block(run_json, update_contract)
    findings += _check_correctness_axis_published(flat)
    findings += _check_per_row_fields(rows)
    findings += _check_trust_axis_not_nulled(rows)
    findings += _check_invented_headline(flat, update_contract)
    findings += _check_ceiling_exceeded(flat)
    findings += _check_perfect_precision(flat)
    findings += _check_recall_contradiction(flat)
    return findings


def conformance_report(run_json: dict[str, Any]) -> dict[str, Any]:
    f = check_run(run_json)
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "verdict": "FAIL" if any(x.severity == "FAIL" for x in f) else "PASS",
        "n_findings": len(f),
        "findings": [x.to_dict() for x in f],
    }
