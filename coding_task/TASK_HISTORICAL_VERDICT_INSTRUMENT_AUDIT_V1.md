# TASK: Historical DELETE/DROPPED Verdict Instrument Audit (HIST-VERDICT-AUDIT-V1)

**Task ID:** TASK-HIST-VERDICT-AUDIT-V1
**Priority:** Medium-High — some number of already-deleted models may have been wrongly
discarded, and re-acquiring them costs real disk/bandwidth, so this should be scoped and
prioritized deliberately, not done ad hoc.
**Category:** Bench methodology / historical-decision audit
**Protected files:** None directly, but any re-promotion this task produces touches
`config/portal.yaml` workspace conversions — **every reversal is a `[GATE]` operator confirm**,
same discipline as TASK-LANE-CLOSEOUT-001.

---

## The finding that opened this (2026-08-14, TASK-LANE-CLOSEOUT-001)

`bench_capability.py`'s V11 suite (C1-C5: `agentic_debug`, `codegen_executable`,
`env_simulation`, `swe_diagnosis`, `long_context`) is entirely SWE/agentic/coding-flavored.
It was used indiscriminately to judge candidates for `auto-daily` and
`auto-general-uncensored` — lanes whose actual stated job is "chat, writing, editing,
summarization, planning, light technical help," nothing coding-related.

Two new lane-appropriate probes (D1: writing/editing/tone, D2: summarization/status/planning —
`tests/benchmarks/bench_capability.py`, sourced from `bench_daily_soak.py`'s realistic
daily-task bank) were built and used to re-test the 3 candidates that had "won" or looked
close under C1-C5. Result:

| Candidate | Lane | C1-C5 verdict | D1/D2 verdict |
|---|---|---|---|
| `gemma4:31b-it-qat` | auto-daily | WIN +33.4pts | **LOSS -12.5pts** |
| `Huihui-Qwen3.6-35B-A3B-abliterated` | auto-general-uncensored | WIN +19.8pts (mixed) | **exact tie** (delete) |
| `gemma-4-26B-uncensored-heretic` | auto-general-uncensored | WIN +58.2pts (dominant) | **exact tie** (delete) |
| `unsloth Qwen3.6-35B-A3B` | auto-daily | WIN +18.8pts | WIN +12pts (confirmed) |

**3 of 4 flipped or reversed under the correct instrument.** These 3 hadn't been executed yet
(caught before the `ollama rm`), so no damage there — but the same C1-C5 suite has been the
project's only general-capability probe since V11 landed (`TASK_BENCH_METHODOLOGY_V11`), and
it has been run against non-coding-lane candidates before, in sessions prior to this finding.
Any of those historical DELETE verdicts could rest on the same mismatch.

## Scope — what to audit

`config/MODEL_CATALOG.md` has 17 `DROPPED` entries as of 2026-08-14. Triage by mismatch risk
before spending any re-pull budget:

**Lower risk (spot-check only) — evaluated via a lane-matched instrument already:**
- Security-flavored (`RedTeamLab` blueteam/redteam variants, `ravenx-cyberagent-35b`,
  `baronllm-abliterated`, `CyberSecQwen-4B`, `qwen36-27b-fable-fusion-heretic`) — this project
  has a bespoke security-bench framework (`bench_security.py`, RBP corpus, MITRE probes);
  security-lane verdicts likely used it, not C1-C5. Confirm before excluding, don't assume.

**Lower risk — not bench losses at all:**
- The 2026-08-10 disk-cleanup batch (`gemma-4-e4b-it-4bit`, `supergemma4-26b-abliterated...`,
  `Qwen3-VL-32B-Instruct-4bit`, `Qwen3.6-27B-oQ8-mtp`, `Llama-3.2-3B-Instruct-8bit`,
  `Phi-4-reasoning-plus-MLX-4bit`) — dropped for "no production route" / disk reclaim, not a
  bench-off loss. No instrument to have gotten wrong.

**Higher risk — check first:**
- `Ornith-1.0-9B` (2026-06-30), `Qwythos-9B-Claude-Mythos` (2026-06-30) — verify what instrument
  decided these and what lane they were contending for.
- Any DELETE verdict findable in `reports/PENDING_VERDICTS_ANALYSIS_*.md` history or
  `docs/reports/*.md` decision docs for a non-coding, non-security lane
  (auto-daily/auto-general/auto-general-uncensored/auto-creative/auto-compliance/auto-data/auto-spl)
  that cites `bench_capability.py` C1-C5 or a similarly coding-flavored instrument as the
  deciding evidence.

## Method

1. For each higher-risk candidate still findable in decision docs, confirm which instrument
   produced the DELETE verdict and whether it matches the target lane's actual job.
2. **D1/D2 only cover auto-daily/auto-general(-uncensored)-shaped lanes.** `auto-creative`,
   `auto-compliance`, `auto-data`, and `auto-spl` have no lane-appropriate probe yet — building
   those (same pattern: a `PROBES` entry + a small realistic task bank + marker-based grading,
   see `run_d1_writing`/`run_d2_summarize` for the template) is a prerequisite for auditing
   those lanes, not optional.
3. For any candidate whose original verdict instrument turns out mismatched: re-test with the
   correct instrument if the model is still on disk; if deleted, weigh re-pull cost (check size
   first) against how close/consequential the original call looked before spending bandwidth.
4. Apply the normal win rule (tiebreaker/margin, ties go to incumbent) to the corrected data.
   This is a re-test, not a thumb on the scale — a corrected instrument can still say DELETE.
5. Any resulting PROMOTE is a `[GATE]` operator confirm, same as every other lane conversion.

## Non-goals

- Do not re-promote anything based on the *old* C1-C5 numbers alone — the whole point is those
  numbers are untrustworthy for non-coding lanes.
- Do not blanket re-pull all 17 DROPPED entries speculatively — triage first per the risk tiers
  above; re-pulling is real bandwidth/disk cost (today's 4-model remediation alone was ~63GB).
- Do not touch the lower-risk tiers without first confirming (not assuming) they used a
  lane-matched instrument.
