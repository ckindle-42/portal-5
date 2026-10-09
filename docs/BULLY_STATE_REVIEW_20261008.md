# Bully — state review and redesign basis (2026-10-08)

Ground-up review requested after the EG2-followups work. Everything below is counted
from HEAD (`02c6a97d`) and the live machine, not from earlier docs. Supersedes the
"where things stand" sections of `docs/HANDOFF_BULLY_CROGL_STATE.md` (2026-08-21) and
`docs/BULLY_BUILD_PROGRESS.md`; their lessons sections remain valid and are folded in.

## 1. What actually exists

**Two programs share one package** (`portal/modules/security/core/bully/`, 90 modules,
35,318 lines, 185 test files, 26 run scripts):

| program | purpose | last real activity |
|---|---|---|
| Defensive Bully (P0–P7, SA1–SA7) | cousin engine, specimen corpus, discovery lane, hunt orchestrator + council + promotion | Aug 21 (orchestrator); Oct 8 (discovery bench only, via the EG2 cutover) |
| Hunt loop / "Crogl" (16 modules) | universal intake, entity pivot, analyst loop, corpus bed on BOTS | Aug 26 (H5 sweep) |

Commits touching the package: 166 in August, 3 in September, 7 in October — all seven
October commits were side-effects of the embedder cutover on one bench lane.

**Wiring (import census from production entrypoints):**

| reachability | modules | lines |
|---|---|---|
| production-reachable | 26 | 12,495 |
| script-only (run harnesses) | 51 | 20,381 |
| tests-only | 12 | 2,374 |

The only production entrypoint is the operator CLI
`python -m portal.modules.security.core hunt` (`commands/hunt_modes.py:62` →
`orchestrator`). **No MCP tool, pipeline route, workspace or service reaches Bully.**
The `security` MCP (:8919) exposes `classify_vulnerability` and `lab_perception` only.

## 2. What has actually been exercised

**The production loop has never completed a hunt.** `hunt_state.db` (last written
2026-08-21): 38 hunts, all `status=running` (33 stuck in DRAFT, 5 BLOCKED), 0 iterations,
0 council opinions, 0 promotions, 0 SOC deliveries. `hunt_memory` (LanceDB) is empty.
The council/handoff model routes in `config/portal.yaml` (granite4.1, mistral-small3.2,
qwen3.6, Foundation-Sec) resolve to current models, but none of them has ever produced
a Bully output.

**Every run report is self-qualified.** All 19 `docs/BULLY_*RUN*` /
calibration reports carry their own INVALID / PROXY_SCALE / DIAGNOSTIC / superseded /
errata marking. None records the commit or embedder it ran on. Best real-data result:
H5 (Aug 26) — `assembly_verdict PROXY_SCALE`, bed `INVALID`, 0.128% of the 281M-record
corpus, `floor_known_recall 0.63` (17/27) with cousins injected by the run itself.
The discovery-lane "precision 1.0" (DISCOVERY_BASELINE_V3) was produced while the engine
could read the truth labels (BULLY-DISCOVERY-TRUTH-LEAK-001); blind, it is ~15% related
and ~0 cross-source.

**The lab cannot be exercised right now.** The lab Splunk host (10.0.1.30) answers ping
but its Splunk ports (8089, 8000) are closed; the lab targets (10.10.11.21/.33) are up.
Every real-data path needs Splunk.

## 3. The finding that reframes this week's work

`cousin_engine.grade` — the function whose weights (cousin-v2/v3, B1/F1) and
`same_max_distance` (B1.4, F1, T1) were tuned on 2026-10-08 — is **deprecated and off
the product path**: its docstring says so (R.4, 2026-08-20), `orchestrator.py:50` imports
only `retrieve_candidate_axes` and `CoverageView` from it, and `orchestrator.py:710` grades
through `loop_grader.build_cousin_assessment` (pyramid level-first). The discovery bench
and the calibration bench still call `cousin_engine.grade`.

So this week's B1/F1/T1 numbers are valid statements about the **bench's** grader, and
say nothing about what the product would decide. This is lesson 7.3 of the August handoff
("verifying a component is correct is not evidence the system uses it") repeated — by the
EG2 task, its review, and the threshold-validation follow-up alike. What does carry over:
`retrieve_candidate_axes` (shared by both paths) and its 558/988 "no truth-related candidate
retrieved" coverage gap; the corpus defects (truth leak, value-less V2, twins/label noise —
43 of 45 unrelated SAME pairs are evidence twins).

## 4. Lessons (August handoff + this arc), as design rules

1. **Wire before measuring.** A bench must call the code the product calls. Every harness
   asserts, at startup, that its grader is the product's grader (import-identity check),
   or it refuses to run.
2. **Validate the instrument before the engine.** Each harness ships a known-answer
   self-test: oracle grader → must score ~1.0; shuffled/random grader → must score
   chance; planted positives → must be found. A harness that fails its own self-test
   produces no report. (Truth leak, inverted mover labels, pinned-weight drift, rows from
   the wrong τ — all would have been caught.)
3. **Truth is scorer-only, mechanically.** The engine view is built by one function; a
   test fails if any truth key reaches it (exists now for discovery; extend to all lanes).
4. **Metrics name their mechanism and can show failure.** Every headline has a
   negatives population, a paired test (exact McNemar) and a twin-separated count.
5. **No fixed constant decides the answer** (caps, row limits); scope by yield to plateau.
6. **The generator never makes both haystack and needles**; needles live in the corpus's
   time range and are not planted at the anchor.
7. **Every report stamps** commit, embedder identity, model routes, corpus hash, thresholds
   version — a report without them is not evidence after the next engine change.
8. **Thresholds are re-derived per scale and never reused across one** (embedder, weights,
   or grader).
9. **Assemble before building.** No new module until the assembled product path has run
   on the real corpus.

## 5. Recommended redesign path

**R0 — Decide what Bully is for, in Portal 5 terms (blocking).** Today it is an operator CLI
that no Portal surface calls. Choose: (a) an analyst-facing capability exposed through the
security MCP / a workspace (needs a product contract: input, output, latency), or
(b) a research program kept out of the product. Everything below assumes (a).

**R1 — Restore the ground.** Bring lab Splunk back (8089); confirm BOTS indexes and counts.
Resolve why 38 hunts never left DRAFT/BLOCKED (one live `hunt run` traced end to end).

**R2 — One harness, on the product path.** Retire the discovery/calibration benches' use of
`cousin_engine.grade`: either re-point them at `loop_grader` or delete `grade` (its
docstring already scheduled the deletion). Build the single acceptance harness to rules
1–7, with its self-test, before any engine measurement.

**R3 — Exercise the assembled product path on current models**, on BOTS at a stated
corpus fraction, with real negatives; report the four claims (floor, product cousin recall,
cross-source, cost) with stamps. Expect breakage; fix in place.

**R4 — Prune with data.** Of the 51 script-only modules, keep what R3 shows the product
needs; retire the rest (and their run scripts/docs) in one sweep. Collapse known overlaps
(`telemetry_behavior` vs `behavior_inference`, the two cousin graders).

**R5 — Only then tune** weights/thresholds — on `loop_grader`, with paired tests, under
rule 8.

## 6. Disposition of this week's open work

- `TASK_BULLY_V3_THRESHOLD_VALIDATION_V1` — **paused**; T1 v4 edits stashed
  (`stash@{0}`, not committed; `eca990fd` is the docs-only "0.055 kept" note). Evidence about
  the bench, kept uncommitted under `reports/bully_v3_threshold_validation/t1_same_band_v2/`
  and `reports/bully_calibration/`:
  - Identity over all 988 probes (970 retrieve their own record; 18 never do): symmetric max
    0.0283 / p95 0.0151; asymmetric max 0.0573 (the 100-probe sample's 0.0540 underestimated it).
  - SAME-band precision ~26% at every cut-off; 43 of 45 unrelated SAME pairs are evidence
    twins — the truth labels, not the grader, are the noise.
  - The blind identity control is a hard gate that measures the truth-strip asymmetry itself
    (68/100 self-pairs fail at 0.026) — a harness defect of the rule-2 kind.
  - T2 (frozen P6.8 calibration sweep, v3 thresholds): **FAIL** — band_crossing 5,
    mid-band graded NEW 6, variants graded SAME 8, false cousin 1; monotonicity, response axis
    and parent assignment clean. Structural cause: the behavior channel saturates at 1.0 on
    mid-band mutations, and d=1.0 negative controls compose to ~0.32 and grade SIMILAR —
    the flat distance grader cannot separate the calibration bands at any threshold. The
    0.375-weight candidate fails the same sweep (band_crossing 7). Bench grader only; says
    nothing about `loop_grader`.
- cousin-v3 / thresholds v3 (`fea93168`) — correct for what it is (unit mass on the bench
  grader); no product effect. Leave in place until R2 decides `grade`'s fate.
- R1 (RAG) and H1 items of the EG2 followups are unaffected — they are on live product paths.
