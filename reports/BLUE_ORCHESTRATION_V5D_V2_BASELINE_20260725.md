# Blue Orchestration V5D V2 Baseline — 2026-07-25

## Outcome

The corpus-matched pre-V3 baseline is **4/17 (23.5%) confirm-only recall** on
the strong solo arm. The three-way result is:

| Arm | V2 exact pre-V3 | V3 | V4 |
|---|---:|---:|---:|
| Strong solo | **4/17 (23.5%)** | **3/17 (17.6%)** | **3/17 (17.6%)** |

On this matched run, the reasoning-first V3+V4 program **reduced** strong-arm
confirm-only recall by 1/17, or 5.9 percentage points, versus the code it
replaced. V4 fixed correctness and completion defects—most visibly reducing
UNRESOLVED from 2/17 in the stored V3 strong arm to 0/17—but did not recover
the lost confirmation.

## Baseline identity

The true V2 baseline used here is commit
`c7c6df8799635149856332a9dff0c26e6b83bca9`, the direct parent of V3A commit
`1eced069078db397ab5b30a1e4b33a142c5065fe`. It is the mature three-section
Retriever → Hunter → Expert implementation immediately before Mentor,
per-role budgets, and barrier tools were added.

The run imported code from a detached checkout of `c7c6df8` and enforced that
SHA before starting. It supplied only V2 `SectionSpec` fields:

- tool: `granite4.1:8b`
- reasoning: `granite4.1:30b`
- expert: `granite4.1:8b`
- `max_rounds=6`
- no Mentor section
- no `budgets=`
- no barrier tools

Current-code “knobs off” was rejected as a baseline because V4’s
discriminator and budget-starvation handoff changes are unconditional. A
current knobs-off run would therefore be an approximation, not V2.

## Corpus and ruler controls

- The baseline used the identical ordered 17-technique set and sourcetype map
  from `corpus_replay_bench.py`.
- Every cell queried the same lab source,
  `evidence_origin=corpus:*`, through the technique's pre-pipe SPL and
  completed with corpus data present.
- All 17 relevant SPL strings are byte-identical between `c7c6df8` and V5
  HEAD; V5's discriminator additions did not alter a search.
- `agentic_blue_eval.py`, including `score_findings_tiered`, is unchanged
  between `c7c6df8` and HEAD.
- All V2/V3/V4 columns were recomputed with the same confirm-only rule:
  technique IDs score only when `verdict == "CONFIRMED"`.

The V2 checkpoint SHA-256 is
`6fc90f95e694b162b00d20aa06a27bc35d8b81c4e9f76b47ef1c381705a7ab89`.
It contains 17/17 completed records, all stamped with the exact V2 commit.
The raw checkpoint remains gitignored; the reproducible runner is
`scripts/v2_corpus_baseline.py`.

The stored V3 checkpoint SHA-256 is
`8be8468867a64c1643d5181fa1d6e3cc238392d52b3d10755e50329772dc6265`;
the V4 checkpoint SHA-256 is
`8bfb406544a903f11def43ecb3c65e4ac66149671ef032e6b8fb507eb1bcbad0`.
Recomputation reproduced the V4 close-out columns exactly: V3 3/17 and V4
3/17 for the strong arm.

## V2 cell results

V2 verdicts were 4 CONFIRMED, 1 ANOMALOUS_UNCLASSIFIED, and 12 RULED_OUT.
The exact confirmed techniques were:

- `T1595`
- `T1550.002`
- `T1003.003`
- `T1189`

RULED_OUT payloads that retained a technique ID received zero credit, as they
do in the V3/V4 recomputation.

## Earlier single-model candidate

An older single-model blue chain exists in `blue.py` before the section
pipeline was introduced (`a53b88b9` began the reasoning section;
`2459cb97` landed the deterministic pipeline). It is not the V2 predecessor
replaced by V3 and was not labeled as V2 here. Measuring it would answer the
broader “did the whole section pipeline help?” question, but would require a
separate adapter to the 17-cell corpus and is outside this V3-contribution
baseline.

## Interpretation

The result does not say V3/V4 had no value: V4 eliminated unresolved cells and
fixed unsafe misattribution/quorum behavior. It does say the program did not
improve the promotion metric it was later evaluated on. Future architecture
work should treat “reasoning-first improves recall” as disproven for this
corpus/model roster unless a new controlled run reverses the 4→3 regression.

