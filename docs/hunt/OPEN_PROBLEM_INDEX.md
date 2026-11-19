# Hunt open problems — index

One entry per `OPEN_PROBLEM_*` lane: the solver approach, what it found, its live
result, and whether it is merged. Every figure is a dated measurement of its own run
or replay, never a current-state claim (`docs/wiki/WIKI_STRUCTURE.md`); the shared
pre-fix baseline is `docs/hunt/BOTSV2_DIAGNOSIS.md` (2026-11-18 run: 1 of 15 labelled
steps at top-100, dominated by causes upstream of ranking). The scoreboard, not the
ranked head alone, decides a step: steps at rank 50 / 100 / all, and scenario coverage.

| lane | solver | live result (receipt, date) | merged? |
|---|---|---|---|
| hunt-open-kimi | behaviour-burst deviation | botsv2 0→2 of 15 steps @50, 2 of 4 scenarios; kyoushi 12 of 12, santos 14, russell 15 @50 (`b947b840a`, 2026-11-19) | yes — main `b947b840a` |
| hunt-open-astra | sampler source-path crossover fix | botsv2 2→3 of 15 steps @50, 2 of 4 scenarios; kyoushi 12 of 12, santos 14 of 21, russell 15 of 22 @50 (`080f89314`, 2026-11-19) | yes — main `080f89314` |
| hunt-open-neon | burst-guided sampling + wide-telemetry fixes | replay only (2026-11-19, on the astra snapshot): botsv2 5 of 15 @50, 3 of 4 scenarios; no build-family regression. Live run pending | no — round 2 on `lane/hunt-open-neon` |

## hunt-open-kimi — behaviour bursts as first-class deviation evidence

Problem: `OPEN_PROBLEM_hunt-open-kimi.md`. The stored runs already held a strong
event-level botsv2 signal that no generator measured — one behaviour
(`45.77.65.211 did TRAFFIC to ssl`) carried 2,452 sampled events in a single
four-hour bucket, while `deviation` scored source bursts and first-seens and
`peer_rare` measured entity share with merge weight 0. The fix joins `events` to
`behaviours` on the identity columns, finds each behaviour's largest four-hour
bucket, z-scores `log1p(peak)` within its source, and admits at most two
behaviour bursts stronger than the strongest source burst into the existing
allocation — allowance 2 selected by LOFO on kyoushi/santos/russell, botsv2
excluded, measured generator weights unchanged (2026-11-19 replay:
kyoushi 12, santos 14, russell 15 @50; live receipt matched).

## hunt-open-astra — shared source names break sourcetype attribution

Problem: `OPEN_PROBLEM_hunt-open-astra.md`. Measured on the 2026-11-19 audit of the
stored burst runs: 19 of 104 botsv2 sourcetypes had first-eight sources overlapping
another type (16 shared source names; eleven types shared `gacrux`), so a raw read
selected by source alone could fill one card's budget with another type's rows. The
rank-one threat card held 4,530 distinct raw lines against a claimed 2 indexed
events — the provenance of the only notable carrying the top-50 steps was wrong.
The fix deduplicates cards by sourcetype, records inverted source ownership at
discovery, gives single-timestamp sources one window at their observed time, and
reads small sources whole within their existing allocation. Live four-family run
(`080f89314`): botsv2 3 of 15 @50 / 3 @100 / 4 @all, 2 of 4 scenarios; kyoushi
12/12/12 of 12, santos 14/16/17 of 21, russell 15/15/16 of 22. Live runner:
`coding_task/RUN_HUNT_OPEN_ASTRA.sh` (merged with the lane).

## hunt-open-neon — wide telemetry, fleet-wide burst masking, burst-guided sampling

Problem: `OPEN_PROBLEM_hunt-open-neon.md` (on the lane; lands with its merge). Six
structural bottlenecks measured 2026-11-19 on the astra snapshot and read-only
lab probes, all general: template mining baked sample-specific PIDs/dates into
constants (inflating `osquery_warning`'s misfit share 0.29% → 13.2%, which dropped
the whole source and its `.crypt` artefact); fleet-wide common-mode surges filled 28
of the top-40 source-burst ranks; 400-character evidence truncation cut security
fields (measured offsets past 400 in `osquery_results`, `csp-violation`,
`xmlwineventlog:sysmon`, `stream:smtp`, `stream:http`); uniform-tail sampling missed
burst-localized episodes; wide-schema card discovery truncated at 24 fields and
partitioned on non-discriminating fields; single-source monopolies crowded
`similar_to_known`. Fixes: template generalization, common-mode median-z
subtraction, 2,400-char evidence, burst-guided windows inside the existing
24-request/source budget, schema-separation partitions, identity `from`/`to`
fallbacks, and pattern diversity. Round 2 (`308692931`) adds hourly burst slices,
duplicate-preserving window merge, concentration-weighted bursts, template
measurements and categorical transition order. Frozen-embedding replay on copies of
the astra runs (2026-11-19): botsv2 5/5/5 of 15 @50/@100/all, 3 of 4 scenarios;
kyoushi 12/12/12 of 12, santos 15/15/18 of 21, russell 15/15/16 of 22. Live runner:
`coding_task/RUN_HUNT_OPEN_NEON.sh` (rides the lane, not on main).

## Status rules

- A lane moves to "merged" when its merge commit lands on main; its problem doc and
  dated receipt are then authoritative on main.
- A replay number never substitutes for a live run; each row names which one it is.
- The next live run is always the measurement for further change; family baselines
  to hold: kyoushi 12 of 12, santos 14 of 21, russell 15 of 22 at 50 (2026-11-19,
  `080f89314`).
