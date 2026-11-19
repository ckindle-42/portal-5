# Open problem: behaviour bursts as first-class deviation evidence

## Finding

The stored parsing+sampling run already contains a strong, event-level botsv2
signal, but the generators do not measure it. `45.77.65.211 did TRAFFIC to ssl`
has 2,452 sampled events in one four-hour bucket. It is absent from the ranked
head because `peer_rare` measures entity share (and has merge weight zero), while
`deviation` measures source bursts and first-seen behaviours, not concentration
within a behaviour. This is a behaviour-notable gap, not a request for another
rare-identity generator.

Offline replay over the four stored runs added four-hour behaviour-bucket peaks
without reading any keys during candidate generation. Keys were used only by the
existing scoreboard afterwards. A robust within-source z-score of `log1p(peak)`
puts that behaviour first on botsv2. Source-normalized share instead promotes
tiny, uninformative behaviours, so absolute within-source temporal outliers are
the useful general measure.

## Replay results

Rows are steps located at rank 50 / 100 / all; botsv2 also shows scenarios at
50 / all. `unified2` admits at most the two strongest behaviour bursts that are
more anomalous than the strongest source burst, then competes with source bursts
inside the existing deviation allocation. The two-slot allowance was selected
by LOFO on kyoushi/santos/russell, not on botsv2.

| replay | botsv2 steps | botsv2 scenarios | kyoushi | santos | russell |
|---|---|---|---|---|---|
| stored parsing+sampling | 0 / 0 / 1 | 0 / 1 | 12 / 12 / 12 | 13 / 16 / 17 | 15 / 15 / 16 |
| unified2 | 2 / 2 / 3 | 2 / 2 | 12 / 12 / 12 | 14 / 16 / 17 | 15 / 15 / 16 |

The two botsv2 top-50 steps are `brewertalk_web/web_scan` and
`taedonggang_phish/c2_ssl`, both carried by the same behaviour notable at rank 1.
This improves event-level ranking but does not yet recover the many artefacts
absent from the sample.

Other rejected replays, all on the same stored runs:

- A separate behaviour-burst generator displaced useful results (santos fell to
  12 at 50); sharing the existing deviation budget avoids that regression.
- More admitted bursts were harmful: unified10 produced 12 santos and 11 russell
  at 50, versus 14 and 15 for unified2.
- Replacing the source misfit-share gate with a per-source shape cap recovered
  botsv2's `.crypt` artefact only beyond rank 100 and reduced kyoushi from 12 to
  11 at 50; it is not part of the fix.
- Content filtering removed no existing notables and did not change baseline
  recall, so it explains none of the family difference.
- Replaying unified2 on the rarity-seed run leaves botsv2 at 2 at 50 but retains
  that experiment's kyoushi/russell regressions. Rarity-directed reads are not
  required for the behaviour-burst fix.

## Allowance selection without botsv2

The candidate allowance was replayed on the three build families only. Values
below are steps at rank 50:

| allowance | kyoushi | santos | russell |
|---:|---:|---:|---:|
| 1 | 12 | 13 | 15 |
| **2** | **12** | **14** | **15** |
| 5 | 12 | 14 | 13 |
| 10 | 12 | 12 | 11 |
| 100 | 12 | 12 | 11 |

Allowance 2 gives the best other-family training total in the kyoushi fold
(29), ties for best in the santos fold (27), and ties for best in the russell
fold (26); the smaller allowance breaks the ties. botsv2 did not participate.

## Code change

The implementation is limited to the existing deviation generator and the
stored behaviour read slice:

1. A DuckDB query joins `events` to `behaviours` on all ten identity columns and
   finds each behaviour's largest four-hour event bucket. It makes no Splunk
   request and reads no additional events.
2. Within each source, `log1p(peak)` is scored by median/MAD across behaviours.
   The best 100 candidates retain the behaviour's actor/action/object and raw
   evidence as `deviation` / `behaviour_burst` notables.
3. Only candidates stronger than the strongest source burst are eligible. At
   most two enter the existing source-burst allocation, which is then merged
   with source-first-seen and behaviour-first-seen as before. This is not a new
   generator and does not change the measured generator weights.

Replaying these production helpers (not the experimental duplicate) over the
stored runs gives the unified2 row above. Admission explains the family
difference: botsv2 has 19,022 behaviours, source baseline 7.409, two admitted,
and a winning behaviour z-score of 14.224; kyoushi has 19,265 behaviours,
source baseline 12.095, and zero admitted; santos and russell each admit two,
with baselines 6.606 and 5.051. The same-input build-family result therefore
does not regress: kyoushi stays 12, santos rises 13 to 14, and russell stays 15
at rank 50.

The unit tests use the stored traffic identity and peak shape, exercise the
full DuckDB identity join and four-hour bucketing, and prove the generator path
and two-candidate cap without network access.

## Limits and live proof still required

The replay recovers event-level botsv2 evidence already present in the sample;
it does not solve the dominant sampling floor for artefacts never read. It also
does not reproduce the separate rarity-seed run's santos 17 at 50 or the
rarity-generator run's russell 16 at 50, and those rejected experimental
branches are not included. The claim is therefore deliberately narrow: a
general behaviour-notable fix with a measured offline improvement, not a claim
that every historical best is already met.

Offline replay cannot establish the live pass bar, fresh-sampling effects,
knowledge-store effects, or case quality. The orchestrator must run all four
families and score them with the normal commands before accepting the change.
