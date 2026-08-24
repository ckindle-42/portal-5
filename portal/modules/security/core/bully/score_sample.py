"""bully.score_sample -- keep a representative sample for the analytical path.

The F.4 assembly run reached `integration_fraction 1.0` -- all sixteen modules
in one pipeline, zero degraded stages, the first assembled whole in the arc --
and its analytical stages still measured nothing. The cause is one line in the
streaming stage:

    ctx.put("records", last_batch)      # scripts/bully_full_assembly_run.py:357

`last_batch` is whatever the final loop iteration happened to hold. The stream
covered **325 sourcetypes and 359,757 records** and fitted the baseline on
**99,033 units**; the analytical path received **63 records of one sourcetype**
(`yum-too_small`). The consequences are visible right across the run's own
`stage_outputs`:

    classify_telemetry            63 records, coverage 0.0, degenerate: true
    infer_universal_behaviors     0 actions, 0 schemas, cross_schema_fraction: null
    resolve_entities_and_timelines 1 entity, 1 timeline
    raise_and_verdict_concerns    0 concerns

Every analytical stage completed in 0.0s while 370.9s of 386.8s went to
streaming. **Fit-wide/score-narrow was implemented as fit-wide/score-nothing.**

The fit itself is right and should not change: stratifying by sourcetype rather
than walking raw volume is what let a bounded behavioural vocabulary converge
across 325 sourcetypes in minutes, and it is why `discovery_rate` finally
discriminated (7 discovered, **63 of 70 units correctly rejected as
unremarkable**, against D.4's rate of 1.0 where nothing was rejected). What is
missing is that the same stratification never reached the scorer.

So this module keeps a **reservoir sample stratified by sourcetype** as the
stream passes, at a bounded memory cost, and hands that to the analytical
stages. It is deliberately tiny and has one job, because the F.4 lesson is that
a plumbing defect should be fixed in place rather than escalated into another
module with its own theory.

Two properties matter and are enforced here rather than left to the caller:

  * **Stratified, not sequential.** A flat tail or a flat head reproduces the
    bug in a different shape -- one sourcetype dominates. Every sourcetype the
    stream sees gets a slot.
  * **Bounded and reported.** `per_sourcetype` and total caps are explicit, and
    `sample_report` publishes what was kept against what was seen, so a starved
    analytical path can never again look like a healthy one.

Pure compute (COLD). No I/O.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

ALGORITHM_VERSION = "score-sample-v1"

# Records kept per sourcetype for the analytical path. The scorer needs enough
# per source to profile actions and resolve entities; it does not need the
# whole stream. 325 sourcetypes x 200 = 65k records, which every downstream
# stage handled comfortably at far smaller volumes.
PER_SOURCETYPE = 200

# Absolute ceiling, so a corpus with thousands of sourcetypes cannot exhaust
# memory. When hit, it is REPORTED -- a truncated sample must never be silent.
MAX_TOTAL = 200_000


@dataclass
class StratifiedSample:
    """A reservoir sample with one slot per sourcetype.

    Reservoir sampling is used per stratum so a sourcetype's representatives
    are drawn from across its whole appearance in the stream, not just its
    first N records -- a head-biased sample of a busy source shows only its
    earliest minutes, which is the same time-ordering bias that made
    `dedup n sourcetype` worth flagging.
    """

    per_sourcetype: int = PER_SOURCETYPE
    max_total: int = MAX_TOTAL
    seed: int = 1337
    _by_st: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    _seen_by_st: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _rng: random.Random = field(default_factory=lambda: random.Random(1337))
    truncated: bool = False

    def add(self, record: dict[str, Any], sourcetype: str) -> None:
        st = sourcetype or ""
        self._seen_by_st[st] += 1
        slot = self._by_st[st]
        if len(slot) < self.per_sourcetype:
            if self.total >= self.max_total:
                self.truncated = True
                return
            slot.append(record)
            return
        # reservoir: replace with decreasing probability so the sample stays
        # representative of the whole stream for this sourcetype
        n = self._seen_by_st[st]
        j = self._rng.randint(0, n - 1)
        if j < self.per_sourcetype:
            slot[j] = record

    def extend(
        self,
        records: list[dict[str, Any]],
        *,
        sourcetype_of: Callable[[dict[str, Any]], str],
    ) -> None:
        for r in records:
            self.add(r, sourcetype_of(r))

    @property
    def total(self) -> int:
        return sum(len(v) for v in self._by_st.values())

    @property
    def sourcetypes(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_st))

    def records(self) -> list[dict[str, Any]]:
        """The analytical path's input: every sourcetype represented."""
        out: list[dict[str, Any]] = []
        for st in sorted(self._by_st):
            out.extend(self._by_st[st])
        return out

    def report(self) -> dict[str, Any]:
        """What was kept against what was seen.

        Published so the F.4 failure mode -- a scorer fed one sourcetype while
        the stream saw 325 -- is visible in the run's own output instead of
        having to be inferred from a 0.0s stage timing.
        """
        seen_total = sum(self._seen_by_st.values())
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "sourcetypes_seen": len(self._seen_by_st),
            "sourcetypes_sampled": len(self._by_st),
            "records_seen": seen_total,
            "records_sampled": self.total,
            "per_sourcetype_cap": self.per_sourcetype,
            "sample_fraction": (round(self.total / seen_total, 6) if seen_total else None),
            "truncated_at_max_total": self.truncated,
            "largest_sourcetype_share": (
                round(
                    max((len(v) for v in self._by_st.values()), default=0) / max(1, self.total),
                    4,
                )
            ),
        }


# A scorer input dominated by one sourcetype is the F.4 defect in a new shape.
MAX_SINGLE_SOURCETYPE_SHARE = 0.5

# An analytical path that sees fewer sourcetypes than this fraction of what the
# stream covered has been starved, whatever its stage statuses say.
MIN_SCORER_SOURCETYPE_FRACTION = 0.5


def scorer_input_verdict(
    sample_report: dict[str, Any],
    sourcetypes_covered_by_stream: int,
    *,
    max_single_share: float = MAX_SINGLE_SOURCETYPE_SHARE,
    min_fraction: float = MIN_SCORER_SOURCETYPE_FRACTION,
) -> dict[str, Any]:
    """Did the analytical path actually receive the breadth the stream saw?

    F.4 published `integration_fraction 1.0` with every stage OK while the
    scorer saw one sourcetype of 325. Stage status cannot detect that; this
    can, and it is the check that makes the fix verifiable in future runs.
    """
    reasons: list[str] = []
    verdict = "OK"
    sampled = int(sample_report.get("sourcetypes_sampled") or 0)
    covered = max(0, int(sourcetypes_covered_by_stream))
    frac = (sampled / covered) if covered else None

    if frac is not None and frac < min_fraction:
        verdict = "STARVED"
        reasons.append(
            f"scorer_saw_{sampled}_of_{covered}_sourcetypes ({frac:.3f}<{min_fraction}): "
            "the analytical path did not receive the breadth the stream covered"
        )
    share = float(sample_report.get("largest_sourcetype_share") or 0.0)
    if share > max_single_share:
        verdict = "STARVED" if verdict == "OK" else verdict
        reasons.append(
            f"single_sourcetype_share_{share:.2f}>{max_single_share}: "
            "scorer input is dominated by one source"
        )
    if sample_report.get("truncated_at_max_total"):
        reasons.append("sample_truncated_at_max_total")

    return {
        "verdict": verdict,
        "reasons": reasons,
        "sourcetypes_in_scorer_input": sampled,
        "sourcetypes_covered_by_stream": covered,
        "scorer_sourcetype_fraction": round(frac, 4) if frac is not None else None,
        "largest_sourcetype_share": share,
    }
