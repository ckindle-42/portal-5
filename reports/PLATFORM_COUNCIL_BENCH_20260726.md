# Platform Council Earn-Your-Place Bench — 2026-07-26

## Verdict

Keep council platform-only: it did not beat solo enough to justify its cost.

Council caught 2/2 known flaws with cited evidence; solo caught 2/2 (delta +0).

## Live review matrix

| Task | Council | Council caught | Solo | Solo caught | Council / solo latency |
|---|---|---:|---|---:|---:|
| `model-cleanup-safety` | REVISE | yes | REVISE | yes | 408.01s / 40.52s |
| `council-quorum-safety` | REVISE | yes | REVISE | yes | 360.11s / 42.65s |
| `thin-change-request` | REJECT | no | REVISE | no | 397.64s / 41.79s |

## Participation, fidelity, and cost

- Honest abstention on thin material: council 0/1; solo 0/1.
- Code decision preserved: True; dissent preserved: True.
- Dead seats: none.
  - `challenger`: 3/3 (100.0%).
  - `evidence`: 3/3 (100.0%).
  - `operator`: 2/3 (66.7%).
- Latency: council 1165.76s vs solo 124.96s (9.33×).
- Estimated output tokens: council 6520 vs solo 1198 (5.44×). Token counts are explicit character/4 estimates; model-call counts are exact.

## Isolation

run_council_review fans out one immutable review_material string via asyncio.gather; reviewer calls receive no sibling records. tests/unit/test_council_review.py asserts this payload boundary.

## Scope

The set is intentionally small: two known-flaw closeout reviews and one thin-material case. It measures this task class honestly but is not a general benchmark of every decision or policy review.
