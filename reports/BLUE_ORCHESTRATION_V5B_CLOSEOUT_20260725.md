# Blue Orchestration V5B Close-out — 2026-07-25

## Outcome

V5B completed as a measured **R1 → R3** route with no verdict-behavior
change.

The initial V5A strong-arm branch inputs were A=0, B=4, I=6, M=0. Because
INDETERMINATE was dominant, R1 copied only machine-checkable literals already
present in the six affected SPL detections into their
`discriminator_tokens`. None of those entries has `sibling_ids`, so the
production sibling-contradiction gate remains unchanged.

Re-running the same checkpoint through V5A reduced I from 6 to 0 and produced
the final strong-arm inputs **A=2, B=6, I=0, M=0**. Clause 3 of the
deterministic branch rule therefore selected R3: B>A and B≥I. The correct
blue-lane action is a documented non-build.

## Validation

- Source checkpoint:
  `portal/modules/security/core/results/checkpoints/corpus_replay_bench_v4_closeout.json`
- Checkpoint SHA-256:
  `8bfb406544a903f11def43ecb3c65e4ac66149671ef032e6b8fb507eb1bcbad0`
- Completed cells: 51/51
- Initial strong-arm attribution: A=0, B=4, I=6, M=0
- Post-R1 strong-arm attribution: A=2, B=6, I=0, M=0
- Post-R1 machine-readable detail:
  `reports/BLUE_ORCHESTRATION_V5B_R1_ATTRIBUTION_20260725.json`
- Oracle and sub-technique-gate focused tests: 24 passed
- Production verdict/routing changes: none

## Strong-arm disposition by technique

| Disposition | Techniques | Reading |
|---|---|---|
| Evidence-present miss (A) | `T1083`, `T1552` | The model received an SPL-derived discriminator but emitted ANOMALOUS_UNCLASSIFIED. These are the only reasoning/retrieval follow-up candidates from this checkpoint. |
| Honest negative (B) | `T1611`, `T1558.003`, `T1053.005`, `T1550.002`, `T1047`, `T1189` | The model-visible retriever text lacked the expected discriminator and the Expert ruled the technique out. |
| Honest anomaly, evidence absent (I8-preserving) | `T1190`, `T1552.005`, `T1558.004`, `T1110.003`, `T1078`, `T1557.001` | The expected discriminator was absent, but the system surfaced an anomaly rather than manufacturing a confirmation. These are not counted in B by V5B's branch formula. |
| True positive | `T1595`, `T1557`, `T1003.003` | Exact confirmed technique ID. |

Thus 12 of the 14 strong-arm non-confirms lacked the expected discriminator in
the telemetry actually shown to the model; two contained it.

## Coverage hand-off

The absent evidence is a **model-visible corpus coverage** gap. It must not be
misread as proof that the underlying Splunk corpus lacks the events:
`_corpus_episode` selected each episode through that technique's own SPL, while
the persisted retrieval trace often contains only count summaries such as
`8 events: windows:security 8` or targeted-query misses. The checkpoint proves
what reached the model, not whether a fresh corpus query could recover more.

Before authoring new injections, a follow-on corpus/retrieval effort should:

1. Preserve the existing Lane A/B raw corpus, then measure whether every
   technique-selected episode contains its discriminator before tool
   summarization.
2. For `T1611`, `T1558.003`, `T1053.005`, `T1550.002`, `T1047`, and `T1189`,
   make the relevant raw field/value or literal survive the retriever response
   shown to the Hunter. Do not count an event total as equivalent evidence.
3. Apply the same check to the six honest-anomaly cells (`T1190`,
   `T1552.005`, `T1558.004`, `T1110.003`, `T1078`, `T1557.001`) without
   reclassifying their discovery outcome as failure.
4. Cross-reference `P5-SEC-META3-001`: its missing scenario/SPL variants are
   content-authoring gaps of the same family, but the V5 cells first need a
   raw-event-versus-retriever-loss audit so new injections are not created for
   evidence already present underneath a lossy summary.

## Production decision

Production routing remains unchanged. A prompt or model intervention against
this distribution would pressure the system to confirm techniques whose
discriminators were absent from its visible evidence. That would violate I8
and manufacture recall. The two evidence-present misses are retained as
measured follow-up candidates, but they do not dominate this run and no R2
lever is promoted.

