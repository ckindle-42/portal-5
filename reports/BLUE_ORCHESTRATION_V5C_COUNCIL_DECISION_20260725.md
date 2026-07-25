# Blue Orchestration V5C Council Decision — 2026-07-25

## Decision

Council mode is **retained but experimental** and is not a supported
production path with the current roster. The V4 quorum/participation-floor
fixes make it safe—non-voters can no longer turn one vote into apparent
unanimity—but the available second-seat candidates are not useful enough to
justify production routing.

## Re-derived evidence

Source:
`portal/modules/security/core/results/checkpoints/corpus_replay_bench_v4_closeout.json`
(SHA-256
`8bfb406544a903f11def43ecb3c65e4ac66149671ef032e6b8fb507eb1bcbad0`).

- `cogito:32b` rendered a conclusive council vote in **1/17 cells (5.9%)** and
  failed to vote in 16/17. The one vote was RULED_OUT on `T1189`.
- The 16 non-voting traces show the same operational failure class as the
  existing tracked model: long self-questioning reconstructions of ATT&CK
  names/IDs from training memory, repeated acknowledgement that the supplied
  retrieval was incomplete, and no terminal verdict before the output ended.
  This is not a tool-format incompatibility or timeout record.
- The previously tracked
  `hf.co/HeYujie/Qwen3.5-27B-abliterated-GGUF:Q4_K_M` has one preserved,
  documented evidence-grounded trial: **0/1 conclusive votes**, on real
  Kerberoasting telemetry, ending in an approximately 8,000-token
  evidence-abandonment spiral. No corpus-matched 17-cell checkpoint for that
  model exists, so a 0/17-style rate would be fabricated and is not reported.
- Confirm-only recall on the same 17 techniques was **council 1/17 (5.9%)**
  versus **strong solo 3/17 (17.6%)**, a -11.7 percentage-point gap.

The participation counts above were recomputed from each persisted
`council_member` trace entry, not copied from the V4 prose close-out.

## Tracking and visibility

`cogito:32b` now joins `_COUNCIL_UNFIT_MODELS` with its measured rate and
failure characterization. The structure remains advisory: an explicitly
supplied roster is warned about and still runs. The corpus bench's existing
candidate filter excludes tracked entries from its default experimental
roster.

The corpus bench now prints a per-model participation summary from completed
council traces. This exposes the next non-voter after a sweep without requiring
an operator to inspect every cell.

## Revisit criteria

Council can be reconsidered when a second-seat candidate:

1. renders a conclusive, grounded vote in at least **90% of the same 17-cell
   corpus replay** (at least 16/17);
2. is evaluated on actual shared evidence, not only a format/tool-capability
   probe;
3. introduces no unsafe one-voter confirmations under the existing 0.67
   participation floor; and
4. produces confirm-only recall no worse than the matched solo arm before any
   production promotion is proposed.

Until then, the code path remains available for experiments and its safety
checks stay enforced, but production routing remains solo.

