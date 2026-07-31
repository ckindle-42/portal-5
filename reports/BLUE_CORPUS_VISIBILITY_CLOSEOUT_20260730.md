# Blue Corpus Visibility Close-out — 2026-07-30

## Outcome

`P5-SEC-CORPUS-VISIBLE-001` is resolved. The audit compared the V5B
strong-arm checkpoint's exact model-visible Retriever trace with a fresh,
read-only query of each cell's production-SPL-selected corpus episode.

Before the fix, 11 of the 12 affected techniques had their declared
discriminator in the raw episode but not in model-visible retrieval. The
remaining technique, `T1110.003`, derives `distinct_accounts` through its SPL
`stats dc(Account)` pipeline, so the discriminator was present only in the
aggregate query result and absent from individual raw events.

## Root causes and fixes

1. Broad Retriever calls returned count/facet summaries only.
2. Targeted misses returned a non-empty `No matching ... Try a broader query`
   notice, which incorrectly prevented the existing broad fallback.
3. Corpus episode construction discarded label-blind aggregate fields produced
   by correlation SPL pipelines.
4. The corpus episode's scenario string contained the expected technique ID,
   which was unnecessary answer-key leakage into production orchestration.

The Retriever now returns a bounded summary plus at most four representative,
unlabeled raw records. Targeted miss notices are treated as misses and broaden.
Corpus episodes preserve deduplicated aggregate fields alongside raw events,
and their model-visible scenario is the opaque `corpus_replay`.

## Live evidence

All probes used `granite4.1:8b`, the production corpus Retriever model, against
the live Splunk corpus.

| Technique | Raw before | Model-visible before | Model-visible after |
|---|---|---|---|
| `T1611` | PRESENT | ABSENT | PRESENT |
| `T1558.003` | PRESENT | ABSENT | PRESENT |
| `T1053.005` | PRESENT | ABSENT | PRESENT |
| `T1550.002` | PRESENT | ABSENT | PRESENT |
| `T1047` | PRESENT | ABSENT | PRESENT |
| `T1189` | PRESENT | ABSENT | PRESENT |
| `T1190` | PRESENT | ABSENT | PRESENT |
| `T1552.005` | PRESENT | ABSENT | PRESENT |
| `T1558.004` | PRESENT | ABSENT | PRESENT |
| `T1110.003` | ABSENT (aggregate discarded) | ABSENT | PRESENT (`distinct_accounts`) |
| `T1078` | PRESENT | ABSENT | PRESENT |
| `T1557.001` | PRESENT | ABSENT | PRESENT |

After preserving the correlation aggregate, raw and model-visible coverage are
both 12/12. Broad previews remain bounded to four records and 4,000 characters.
They contain source-tagged telemetry only; no expected technique ID is injected.

## Validation

- 48 focused corpus, Retriever, and attribution tests pass.
- Tests cover semantic targeted misses, bounded label-blind previews,
  correlation-aggregate preservation, and opaque corpus scenario names.
- Production verdict behavior and routing are unchanged; this fix changes only
  which already-captured evidence survives the retrieval boundary.
