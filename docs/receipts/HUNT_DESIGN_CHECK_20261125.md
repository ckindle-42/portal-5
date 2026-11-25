# HUNT DESIGN CHECK — 2026-11-25

Design-level review of the hunt program for the week 2026-11-18 → 2026-11-25. Facts only, no
fixes, no code changes. Written on `lane/hunt-design-check` at `5d2b44447`.

**Method.** Read from this checkout only: the plan (`docs/hunt/ORCACYBER_HUNT_PLAN.md`), the
Round-2 root-cause replan (`docs/hunt/ORCACYBER_DEEP_DIVE_3.md`), the four R3 verdicts and the
R2/R1 verdicts (`coding_task/REPORT_HUNT_VERDICT_*.md`), the S-wave proof report
(`coding_task/REPORT_HUNT_PROOF_20261121.md`), the week's finding docs
(`FINDING_HUNT_TEMPLATE_PARSE.md`, `FINDING_HUNT_WIDE_ESTATE_CLOCK.md`,
`FINDING_HUNT_UNIVERSAL_WAVE3_FIXES.md`, `OPEN_PROBLEM_INDEX.md`, `BOTSV2_DIAGNOSIS.md`), and
the commit log (`git log --since=2026-11-18`). No live system was run; every number below is
quoted from a committed verdict/finding or a commit message. Claims are labelled **[doc]**
(quoted from a dated committed receipt) or **[log]** (git history).

Commit volume this week (subject-matched, `hunt|notables|scoreboard|relate|zeek|vulhub|corpus|splunk|wave N`):
218 non-merge commits — 103 docs, 50 fix, 39 feat, plus test/chore/perf/refactor **[log]**.
Consistent with the brief's ~180 (different match rule).

---

## 1. The week in waves

| wave | landed | live grade | outcome |
|---|---|---|---|
| pre-fix baseline | `snap_neon_02cc2e3` (11-19, stored) | — | the numbers every later wave must beat |
| open-problem lanes (kimi/astra/neon) | 11-19 | live 4-family | botsv2 1→3 of 15 steps @50 **[doc: OPEN_PROBLEM_INDEX]** |
| S-wave rebuild (S0–S7, the plan) | by 11-20 | R1 proof run 11-20/21 | all four families **fall short**; family reachable *below* neon **[doc: REPORT_HUNT_PROOF_20261121]** |
| D-wave (D0–D10, Deep Dive 2) | 11-21 | R2 verdicts 11-21 | all four **fall short**; botsv2 literal `--stage all` dies with zero behaviour reads **[doc: R2 verdicts]** |
| E-wave (E0–E7, Deep Dive 3) | 11-21 | R3 verdicts 11-21 | all four **fall short**; botsv2 `--stage all` exits 1 at relate **[doc: R3 verdicts]** |
| post-R3 fixes (template parse, wide-estate clock) | 11-21 | **never graded live in a committed verdict** | both findings say "live run pending (orchestrator)" **[doc]** |
| universal corpora waves 3–7 (Zeek/Sysmon/OT/Vulhub ingest + fix clusters) | 11-22 → 11-24 | blind-proof receipts not committed in this tree (`results/` absent) | fixes verified offline only **[doc: FINDING_HUNT_UNIVERSAL_WAVE3_FIXES]** |

Three live grading rounds in seven days, three unanimous "falls short" verdicts, and the two
fixes that most directly target the R3 root causes were merged *after* R3 and never re-graded
before the program pivoted to new corpora. No R4 verdict document exists at this HEAD.

## 2. Outcome metrics across the waves (the convergence question, answered with numbers)

Family outcome numbers, all from the committed verdicts/proof reports **[doc]**:

| family | neon baseline (stored, pre-rebuild) | R1 (S-wave) | R2 (D-wave) | R3 (E-wave) |
|---|---|---|---|---|
| kyoushi reachable | **11/12** | 7/12 | 7/12 | 7/12 |
| kyoushi labelled lines read | 1,964 (rescored) | — | 287 | **287** (identical to R2) |
| russell reachable | **15/22** | 11/22 | 11/22 | 11/21 (denominator −1 after E6) |
| russell labelled lines read | 873 | — | 3,010 | **936** (fell) |
| santos reachable | **12/21** | 11/21 | 11/21 | **9/20** (fell) |
| santos labelled lines read | — | — | 3,353 | **1,004** (fell) |
| botsv2 literal `--stage all` | n/a (old code) | crashes at relate (`HuntDeadlineExceededError`) | dies with zero behaviour reads | exits 1 at relate (`HuntDeadlineExceededError`) |
| botsv2 keys/steps (best available run) | 5/20, 5/14 | 7/20, 6/14 (stage-split) | 7/20 (stage-split C) | 7/20, 7/14 (truncated run) |

The same graded steps are lost in every round: `attacker_http, dirb, webshell_cmd,
webshell_upload` on kyoushi (R1, R2, R3 — identical), the same five web steps on russell
(R2, R3), `attacker_http, dirb, wpscan` on santos (R2, R3). The rebuild has **never**
reproduced the pre-rebuild neon baseline on any line-mode family, and labelled-line credit
*fell* from R2 to R3 on russell and santos while the read volume rose (santos read fraction
10.7 % → 24.0 %, labelled lines 3,353 → 1,004).

### (a) Verdict: converging instrument, cycling product

- **Converging:** the measurement layer. E0's receipt honesty holds on all four R3 runs
  (0 silent zero-row reads anywhere), per-file estate time matches live `tstats` to the
  second (E1), per-source localisation and coverage labels exist (E3), the judge metric was
  de-composed into honest strata (E7), and the failures are now small, precise and
  mechanism-level instead of "1 of 15 steps, dominated by causes upstream of ranking"
  (the 11-18 diagnosis). The program can now *see* exactly where evidence dies.
- **Cycling:** the product. Outcome metrics are flat-to-worse across three rounds (§2).
  Each wave fixes the layer the previous verdict named, its receipt line passes, and the
  failure reappears one layer downstream in the same causal chain: placement fixed (E2) →
  parse/keying drops the placed rows (R3's core failure) → credit rule can't see the drop.
  On botsv2 the *same exception at the same raise site* (`HuntDeadlineExceededError` at
  relate) survives R1, R2 and R3 through three successive clock fixes. And the loop never
  closes: post-R3 fixes ship ungraded while new corpora arrive — fix-then-move-on, the
  cycling signature.

## 3. The week's fixes, grouped by targeted failure — root cause or symptom?

| # | failure targeted | fixes (commits) | root or symptom? |
|---|---|---|---|
| F1 | graded evidence never read: windows/hosts/heads borrowed from source level (R1/R2 core) | E1 `649843aa5`; E2 `e59ab452a`, `369b87883`, `8fa618638`; earlier astra crossover `080f89314` | **Root** of the named defect — the estate map genuinely had no per-file time. R3 proves the mechanism (tail slices, 0 off-host reads). But it was a root fix to a **non-binding constraint**: outcomes didn't move because F2 sat behind it. |
| F2 | rows that reads return are dropped at keying: template model from a 120-line pre-read sample misses attack shapes (R3 core, all 3 families) | `701559450` (quoted-payload tokenization + sample spread across files) | **Half-root.** Two measured defects fixed at mechanism level (offline replay: 2,002/2,002 WPScan lines dropped → 0). But the design premise survives — structure is still induced once, from a sample, *before* the evidence reads — and the finding's own residual admits a quiet-hour sample still drops novel-404 lines (2,463/2,499 in one replay). Never live-proven. |
| F3 | wide-estate budget: serial discovery burns the job clock; exhaustion is sticky and raises | E4 `2038e23e0`; `aec16e81f` (price probes, restart relate clock); `36744e084` (cache localise scans, cap probes); `3c041c4fa` (inventory sub-budget); `d9dcbe61f` (checkpoint/resume); `c389b9b5f`/`0e5100708` (paginate/bisect past Splunk 10k cap) | **Symptom series.** Each fix is correct accounting for the *then-dominant* cost item, and the next one appears: probes priced → localise scans dominate (420 s) → scans cached → inventory+reads still 733 s > 720 s (R3 measured). Four clock fixes in three days and botsv2 still exits 1. Nothing plans in wall seconds, nothing prioritises graded/wide sources (small sources are read first; graded evidence is planned last), and a budget condition still becomes a process crash. |
| F4 | dishonest/incoherent receipts: silent zero-row reads, per-index localisation, judge metric composition, estate-map reader | `fd781600c`, `92f78fa6e`, `957d09490`, `7abd6a72f`, `478b557ac`, `11b725d06` (E0/E3/E6/E7 + D10) | **Root, and it worked.** This is the one cluster that delivered: R3's diagnosis power (parse replay, burst-hour store counts, probe shares) exists because the receipts are honest. |
| F5 | corpora beyond the IT-family shape: TA sourcetype renames, Zeek TSV-as-JSON, sentinel/placeholder identities, OT/PLC entities, flow roles | `188f80fa6`, `49f452050`, `aa7d6faa7`, `9f04f4397` (renames); `6f2706b96`, `37ba18ca8` (Zeek/CSV, multicast); `95d4677a7` (sentinels, flow roles, sampling floor); `c389b9b5f` (cross-source flows); `37cf2f953` (OT fallback) | **Individually root, collectively symptom** of undeclared assumptions: names are static (the live estate renames via props.conf), values are real entities (`auid=4294967295` anchored cases), telemetry is IT-shaped, budgets are family-sized. Each new corpus wave re-discovered one instance. |
| F6 | credit rule: per-line reachability reads only `events.raw`; ledger `values_extracted` and misfit examples never credit a line (russell R3 §3.3: 2,499 burst lines read, 0 credited) | **no committed fix** | Open design defect. The instrument cannot distinguish "read reached the evidence" from "parser keyed the evidence", which is exactly the distinction the F2 fixes need to be graded on. |
| F7 | unowned outcome regression: relate cases 272 vs 1,879 (russell R2→R3), case members @50 19/22 → 10/22 | none; noted in docs only (`e389066a9`) | Open. No E slice owns the case builder and no acceptance line covers case count — the slice structure has a blind spot for cross-layer regressions. |

### (b) Design assumptions the recurring failures contradict

1. **"A pre-read sample defines the source's structure."** Cards/templates are induced once
   from ~120 lines before the evidence reads. Attack traffic differs from baseline
   *structurally* (different UA token counts, different status codes, different shapes), not
   just in rarity — so the needle is out-of-structure by construction and gets dropped at
   keying. Contradicted on three families in R3 (`events_out_of_structure` 24–51 %; burst
   rows read then 0 in store) and visible as early as the R1 kyoushi verdict (23.7 %).
2. **"Wall time is a safety cap; requests/rows are the budget."** The plan (§3.1) keeps
   `job_seconds: 720` as a cap and plans against the request ceiling. On a wide estate the
   binding constraint is serial discovery wall time — R3 botsv2 spent 339 of 2,000 requests
   while the clock expired (733 s > 720 s), with 41 % of the behaviours ledger being
   `tstats` probes.
3. **"Budget exhaustion may be a sticky global that raises."** A cost condition propagates
   across stage boundaries and ends the process (`relate` catches only
   `FileNotFoundError`/`ValueError`), so the run loses its judge, cases and receipts — and
   `promoted_unjudged == 0` "passes" vacuously.
4. **"The evidence boundary is the keyed store."** Reachability credits only `events.raw`;
   read-but-unparsed lines are invisible. The instrument therefore *conflates* the two
   failure layers the program keeps trying to separate.
5. **"Orthogonal mechanism slices compose into a working product."** R3: 15/17 checks
   (russell), 7/8 slices (kyoushi), all receipts honest — four unanimous "falls short".
   Deep Dive 3 itself diagnosed R2 as "contract mismatches between two layers that each
   behave as written", yet the E plan was still sliced by layer, and R3 hit the *next*
   contract mismatch (read↔parse, parse↔credit). Nothing owns composition; F7 is the proof.
6. **"The read model scales from families to corpora by patching transport limits."** Splunk
   10k `maxresultrows`, inventory starvation, resume/checkpoints, clock-sync preflight —
   each discovered per corpus rather than designed from the measured rate table the plan
   already had.
7. **"Values are entities."** Sentinel/placeholder values (`4294967295`, multicast IPs,
   `-`/`none`) became case anchors; entity recognition is IT-shaped and needed an OT
   fallback per corpus family.

### (c) Smallest design change for the next R-wave, and its live proof

**One contract change: the parser must explain what the reads actually returned.** Move
structure induction from a one-shot pre-read sample to a bounded in-run loop:

1. During behaviours, re-mine templates from the accumulated misfit clusters per source
   (top-k shapes by line count; k an effort budget, LOFO-selected), and re-key the buffered
   out-of-structure lines with the new model.
2. Lines that still fail parse land in the store under a generic keying (raw + whatever
   fields exist) with a receipt counter, instead of surviving only as one misfit example
   per shape.
3. Split the scoreboard's credit into `reached` (ledger `values_extracted`) vs `keyed`
   (store rows), so placement success and parse success are separately visible.

This is the smallest change that converts *already-proven* R3 read placement into reachable
steps: russell's 2,499 read burst lines, santos's 2,500-row WPScan window and kyoushi's
408k-line graded tail were all demonstrably read and then dropped — recall-of-reachable is
already 7/7 (kyoushi), 9/11 (russell), 9/9-all (santos), so crediting these lines moves
`reachable`, which moves the verdict. It requires no new budget, no Splunk setup and no
per-corpus constant.

**Companion (required only for the botsv2 pass bar): price the plan in wall seconds.**
Estimate per-item cost from the plan's own measured rate table (§3.1), trim lowest-value
sources first (never graded-evidence-last-by-accident), and make exhaustion per-stage,
non-sticky and non-fatal: `relate`/`judge` catch `HuntDeadlineExceededError`, emit receipts
on what was read, and judge runs on the notables that exist. A partial run with honest
receipts beats an exit 1 with none.

**Live proof (orchestrator).** Same commands as the R3 verdicts, same four families, code
containing both changes, no tuning, no held-out set touched:

```bash
# per family, as in REPORT_HUNT_VERDICT_R3_* receipts, e.g. santos:
uv run python -m portal.modules.security.core.hunt.notables \
  --index hb_ait_santos_v2 --out /Volumes/data01/portal5_hunt/hunt_r4/santos \
  --stage all --family santos \
  --knowledge-store /Volumes/data01/portal5_hunt/knowledge/knowledge_v2_20261116.duckdb \
  --knowledge-families kyoushi,russell
uv run python -m portal.modules.security.core.hunt.notables.scoreboard \
  --out /Volumes/data01/portal5_hunt/hunt_r4/santos --weights \
  --keys santos=/Volumes/data01/portal5_hunt/corpora/ait_lds_v21/santos_ingest/keys.jsonl \
  --baseline /Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/santos
# and the botsv2 literal: --index botsv2 --stage all  (the command that exits 1 today)
```

Worked when (all from the run's own receipts): `events_out_of_structure` share on
`access_combined` < 0.05 (was 0.31–0.51); burst-hour rows > 0 in `behaviours.duckdb`
(russell hour-03, santos 11:00Z, kyoushi 20:00–22:00 window); the recurring lost steps
(`attacker_http, dirb, wpscan/webshell_*`) flip to reachable; family reachable ≥ neon
(kyoushi ≥ 11/12, russell ≥ 15/21, santos ≥ 12/20); botsv2 `--stage all` exits 0 with a
non-null judge block and coverage no worse than R2-C. Not worked when: out-of-structure
share stays high (re-mining not firing), reachable is flat while `reached` rises (the credit
split shows the loss moved to ranking, a different design defect), or botsv2 still raises
(wall-time pricing not binding). Unlearned-data proof stays gated as the plan requires
(§5 Step 4: held-out sets only after these four pass and constants are frozen); the wave 3–7
corpora get the same blind-proof run (`scripts/hunt_bed/prove_universal_blind.py --all-proof`)
as a generality check, not as the pass bar.

## 4. Caveats

- This is a documents-and-history review. No receipt was re-measured against the live
  system; where two committed docs disagreed, both figures are shown with sources.
- The R3 verdicts were graded on base `a62f9bc45`, which predates the template-parse and
  clock fixes; those two fixes are therefore *unproven*, not *proven insufficient*. The
  cycling verdict rests on the pattern (three graded rounds, flat outcomes, ungraded fix
  tail), not on a claim that `701559450`/`36744e084` fail.
- `REPORT_HUNT_VERDICT_R3_botsv2.md` grades a run whose notables were built on 10,434
  events (deadline-truncated); its coverage numbers are floors, as the verdict itself says.
- Wave 3–7 blind-proof receipts (`results/hunt_proofs/…`) are not committed in this tree;
  their live status is unknown from here.
