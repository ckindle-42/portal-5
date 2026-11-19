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

## Code change

Implementation and focused regression tests follow this findings checkpoint.
The intended change is limited to the existing deviation generator: compute
four-hour peaks for already-sampled behaviour events, score their within-source
robust log z-score, and admit only the LOFO-selected allowance when stronger
than the source-burst baseline. No index, sourcetype, field, artefact, or attack
keyword is used.

## Live proof still required

Offline replay cannot establish the live pass bar, knowledge-store effects, or
case quality. The orchestrator must run all four families and score them with
the normal commands before accepting the change.
