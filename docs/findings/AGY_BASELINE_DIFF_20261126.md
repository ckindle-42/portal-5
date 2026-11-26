# AGY baseline vs 2026-11-26 QAT runs — whole-system diff

Written 2026-11-26 ~16:15Z by the `lane/agy-baseline-diff` worker (escalation brief
`coding_task/BRIEF_AGY_BASELINE_DIFF_ESCALATION_20261126.md`). All numbers below come from the
run artifacts, the OWUI database (read-only copy), host engine logs and git history named in each
row. The `52e1a5fc4` run was **still in progress** at writing time; its numbers are a snapshot.

## 0. Provenance

| Run | Artifact | SHA | Verdict |
|---|---|---|---|
| Baseline (agy) | `~/projects/portal-5/results/qat/release_1_0_final_clean/results.jsonl` | no lineage recorded; derived **`62db8816`** (live checkout `pull --ff-only` at 2026-11-22 23:07:36 CST per `git reflog` of `~/projects/portal-5`; first screenshot written 23:17:28 CST; report generated 2026-11-23 01:30:49 CST = 07:30Z) | 197 rows: 176 PASS / 16 FAIL / 5 SKIP |
| "Now" #1 | `~/projects/portal-5-wt/qat-cfe67a16e/results/qat/release_1_0_20261126T140220Z/` | `cfe67a16e` (run_meta.json) | 236 rows: 47 P / 3 W / 6 F / **180 BLOCKED** |
| "Now" #2 | `~/projects/portal-5-wt/qat-52e1a5fc4/results/qat/release_1_0_20261126T151624Z/` | `52e1a5fc4` (run_meta.json) | in progress; 57 rows at 16:12Z: 49 P / 3 W / 4 F |

Engines at baseline vs now (`~/.portal5/engine_update.json` history):

- Ollama **0.40.17 → 0.40.18** (updated 2026-11-24T17:00Z; baseline ran on 0.40.17, updated 2026-11-23T02:35Z — before the 05:17Z run start).
- oMLX **0.8.1 → 0.8.3** (updated 2026-11-24T17:07Z after one rolled-back attempt at 17:02Z; the 11-24 11:03 CST server.log shows `Settings file version 2 differs from current 3` — the upgrade **migrated `~/.omlx/model_settings.json`** (last written Nov 25 11:26). No repo commit covers that host-side settings migration → flagged as unjustified drift in §3.
- Open WebUI image **v0.13.0-hardened → v0.13.5-hardened** (compose diff `62db8816..origin/main`, recorded by `0fd65ddd3` 11-25).

290 commits landed between `62db8816` and `52e1a5fc4`.

## 1. Pace — the run is not slower per row; it is slower per wall-second, and it stopped finishing

**Per-row inference pace is at parity or faster than baseline.** Over the 36 rows present in both
baseline and the `cfe67a16e` run: baseline 1266 s vs 1233 s (**0.97×**). Over the 36 common rows
of the in-progress `52e1a5fc4` run: 1266 s vs 956 s (**0.76×**). Many seats got *faster*
(`auto-daily::inkling` 58.6→26.5 s, `auto-compliance` 80.7→14.4 s, `auto-coding::cad` 66.6→26.5 s).

**Wall-clock pace per row got ~44 % worse**: baseline ≈ 133 min / 197 rows = **40.6 s/row**;
`cfe67a16e` = 54.9 min / 56 executed rows = **58.8 s/row**; `52e1a5fc4` (snapshot) ≈ 55.6 min /
57 rows = **58.5 s/row**. The gap between "rows got faster" and "wall got slower" is harness and
deadline overhead, broken down:

1. **Suite growth with the slowest rows.** 197 → 236/240 rows. The new stage-5 human-grade suite
   (`ce98e8e69` 11-23, `d28eae3bf` 11-24) adds ~40 browser-GUI journeys at 30–630 s each
   (`s5-compliance-multiframework` 449–630 s, `s5-media-*` 60–130 s).
2. **Browser-GUI default for stage 5** (`df171d9fd` 11-24): drives OWUI through Playwright instead
   of the API — per-row overhead plus scenario-budget timeouts (`s5-route-kubernetes-rbac`
   FAIL 313 s `TimeoutError: Open WebUI assistant turn did not complete within the scenario budget`).
3. **Turn deadline truncation** (`7dbefe845` 11-26): the router now kills any stream at
   `request_timeout` = 300 s wall (`config/backends.yaml:1055`). `s2-p2-auto-research` pinned at
   302.2 s / 301.6 s in both runs; baseline completed naturally at 269.8 s.
4. **Model churn between phases** — pre-existing, not a regression: `_evict_on_primary_change`
   exists since `c2454a65d` (11-22 14:34, before baseline). oMLX log load counts: baseline window
   (Nov 22 23:00 → Nov 23 01:31) 38 loads; C-run window (08:02–08:57 CST 11-26) 18 loads in 55 min
   (higher per-minute rate, but the C run executed fewer, denser rows). Each oMLX load costs
   ~20–60 s (server.log timestamps 08:42:48 load → first completion).
5. **Gate waits**: `WAIT_BUDGET_S = 600` per blocked phase; the C run's final gate consumed its
   ~60 s Ollama evict budget and then blocked 180 rows (§2, item B).

**Conclusion for Q1:** the operator's "agy did it faster" is true for whole-run wall time, but the
cause is *not* slower inference — it is (a) ~40 new slow browser rows, (b) 300 s deadline pins,
(c) one gate that killed 76 % of the C run, forcing re-runs. Naming commits: `df171d9fd`,
`d28eae3bf`/`ce98e8e69` (suite size), `7dbefe845` (deadline), `36b88683e` (slow-seat WARN, cosmetic).

## 2. Outcome — every baseline-PASS row that is not clean now

| Row | Baseline | cfe67a16e | 52e1a5fc4 (snapshot) | Classification |
|---|---|---|---|---|
| `s2-p2-auto-research` | PASS 269.8 s | WARN 302.2 s | FAIL 301.6 s | **Product change** (deadline kill) × **seat change** (ctx16k→32k). OWUI chat `f8ce0b3c` assistant content is literally `[Pipeline stream error — the reply ended early: turn deadline exceeded after 300s]` (84 chars) vs baseline chat `fc3d8d9e` 12,063 chars completed in 165 s reasoning. The C-run WARN "chat turn completed" was a **grader miss** (fixed on this branch). N-run FAIL is the repetition grader firing on the same truncated turn. |
| `s2-p1-auto-coding::bigfix` | PASS 129.0 s | FAIL 127.5 s | PASS 8.3 s | **Pre-existing flakiness now caught.** C-run chat `81ce828a` assistant response is a 47,055-char degenerate loop ("I will search the web for current information…" ×~90); baseline chat `dc8de4ff` answered cleanly in 324 chars. The repetition grader (`ef24999cf`, 11-23 — after baseline) caught a real model defect; N run passed clean. Keep the grader. |
| `p0-portal-trace` | FAIL | WARN | WARN | **Improved** (hops fixed; residual warnings: `com.portal5.weekly-rebuild`, `engines/seat fit`). |
| `s5-route-kubernetes-rbac` | (new) | FAIL 313.1 s browser-budget TimeoutError | WARN 305.2 s slow-seat | **Harness**: browser driver + scenario budget + slow-seat WARN; answer content graded fine ("human-grade conversation and content checks passed"). |
| `s5-media-music-audio` | (new) | FAIL 59.9 s | FAIL 61.2 s | **Harness expectation vs async product**: turn ends with the ACE-Step job still "Generating (8 steps)"; grader demands the WAV payload in-turn. An async-poll scenario exists (`s5-media-async-poll-music`) but was BLOCKED in C. Needs orchestrator judgment: grader should accept the queued-job contract or the row should poll. |
| `s5-media-voice-clone` | (new) | PASS 75.9 s | FAIL 78.6 s ("transcribed audio did not preserve: portal, 5") | **Unresolved — flake or STT/clone regression.** First divergent result between the two current runs; needs a re-run before classifying. |
| `s5-persona-destructive-agentorchestrator` | (new) | FAIL 77.0 s (persona contract `destructive_warning`) | PASS 100.0 s | **Harness artifact, already fixed** by `cc40a20d0` (grade persona contracts by property, not exact wording) — C ran before it, N ran after. |
| `s5-compliance-multiframework` | (new) | FAIL 449.3 s | FAIL 630.2 s | C-run FAIL = **product regression (safety_guard Layer B)**: answer tail shows both `compliance_ask` calls returned errors; revert `3fab2e074` cites exactly this ("compliance_ask 14:43Z, QAT cfe67a16e"). N-run FAIL is a **different, real grader finding** (missing GDPR Art. 32(1)(a) citation) with the guard unwired. |
| `s5-security-hunt-workflow` | (new) | FAIL 98.1 s ("retrieved results before terminal status") | PASS 94.4 s | **Flake/guard-adjacent** — passes on N with the same contract (`29ca82a0e` is in both SHAs). |

**B. The 180 BLOCKED rows (C run) — unrecorded gate failure.** Every blocked row says only
"blocked by inter-phase gate failure"; `results.jsonl` contains **zero** `gate-*` rows and the run
dir has no gate artifact (`grep -c '"gate-' results.jsonl` = 0). Reconstructed timeline
(host logs, UTC):

- 14:50:03 oMLX unloads `Qwen3.8-27B-oQ4e-mtp` (intra-phase eviction before the research turn; `~/.omlx/logs/server.log`).
- 14:51:00 `s2-p2-auto-research` starts on Ollama `Nex-N2-mini …ctx32k`; killed by the 300 s turn deadline ≈ 14:56:02 (trace `duration_ms: 300004.6`).
- ≈14:56 the phase-transition gate runs: oMLX resident 0 (nothing in server.log after 14:50:03), so the failing check was on the **Ollama side** — the just-killed turn's runner still resident/in-flight and the 60 s `OLLAMA_EVICT_BUDGET_S` exhausted (`tests/qat/gate.py:47`), or `resident_total > 0` (`gate.py:548-557`). Report written 14:57:12 — only ~70 s after the turn ended, matching the 60 s budget, not the 600 s wait.
- The exact failing check is **inference, not proof — because the harness never recorded it.** That evidence hole is fixed on this branch (§5).
- Corroboration: the N run **passed the identical phase transition** (executed `s5-rag-followup`, the first row blocked in C) at ≈16:05Z with no gate block → the C block was a transient post-deadline engine state, not a standing infra failure.

## 3. Settings drift per main seat (baseline `62db8816` → `52e1a5fc4`)

| Seat / scope | Baseline | Now | Commit / justification |
|---|---|---|---|
| `auto-security` primary | `VulnLLM-R-7B-4bit` | `Inkling-2-Mini-oQ4e-mtp` | `4100fda69` (seat Inkling on auto-security) — justified, A/B cited |
| `auto-general-uncensored` | Huihui-Qwen3.6-35B-abliterated `ctx8k`, temp 0.7 / top_p 0.8, `think:false`, presence 1.5 | `Inkling-2-Mini-abliterated-oQ4e-mtp`, **context_limit 262144**, predict 32768, temp 1.0 / top_p 0.95, `reasoning_effort: low`, `emits_reasoning: true` | `8a4e1ef4d`, `8782e04f9`, `ddd53e761` — operator A/B #6 parity decision; justified but a full sampling+identity swap |
| `auto-research` window | 16384 | **32768** (`portal.yaml:979` + ctx32k tag) | `b8d336e9c`/`02383c16c` "32k context upgrades" — justified in-message, but it is the direct cause of research turns crossing the 300 s cap (§2) |
| `auto-audio`, `auto-audio::music`, `auto-vision`, `security-reviewer`, redteam variant | ctx8k tags | ctx16k/24k/64k twins (same weights) | `b8d336e9c`, `02383c16c` — derived `-ctxNk` tags, 0 extra bytes |
| tools-specialist `predict_limit` | 4096 | 16384 | `e4acf1d41` — longer generations on 32k thinking seats |
| `auto-coding::cad` `max_tool_hops` | null | 10 | `02383c16c` — live 450 s loop evidence cited; justified |
| browser workspaces tools | `browser_get_markdown` | `list_sessions`/`reset_session` (+`router:false` flags) | `b8d336e9c`, `3efc4ea3e` sandbox session isolation |
| routing | post-injection text, OWUI memory context included | pre-injection user text (`5cb9f43ec`), memory excluded (`13cdf8587`), handoff scoped (`b40a80159`), tool history isolated (`92b33ef01`) | each commit carries live-evidence messages |
| safety_guard Layer B | wired (`d5d4a20b2` pre-baseline + `817209717` harden) | **unwired** | `3fab2e074` revert — operator decision, cites QAT cfe67a16e damage |
| load_guard | — | sibling-resident waits (`8ffe66733`, `95dd2e818`), shield ordering (`1b958e0e9`, `2f4053724`), glm4moelite MLA sizing (`0d9f0e916`), turn/load waits bounded (`7dbefe845`) | live-defect messages |
| sandbox | network enabled | `--network none` for user code | `ce3f31fa1`, `532bce77e` |
| **host engines** | Ollama 0.40.17, oMLX 0.8.1 | Ollama 0.40.18, oMLX 0.8.3; `~/.omlx/model_settings.json` migrated v2→v3 11-24, rewritten 11-25 11:26 | `scripts/engine_autoupdate.py`, contract-passing. **No commit-level evidence trail for the settings migration — flag.** The 0.8.x "Queued unload … until active scheduler work drains" behavior (server.log 11-26 08:02:37, 08:08:47) is new vs baseline and interacts with QAT eviction. |
| `defaults.request_timeout` | 300 (existed, applied to non-stream requests) | 300 — **now also a hard wall-clock cap on every streaming turn** | `7dbefe845`; the value didn't change, its meaning did. This is drift no config diff shows. |

## 4. Harness drift since baseline (can it flip or slow a row?)

| Change (commit) | Effect | Judgment |
|---|---|---|
| Stage-5 browser-GUI default (`df171d9fd`) + 17/25-journey suites (`d28eae3bf`, `ce98e8e69`) | +40 slow rows; budget timeouts (`k8s-rbac` C FAIL) | Real UI coverage, but budget needs headroom over the 300 s pipeline cap; artifact risk |
| Repetition check (`ef24999cf`) | bigfix C FAIL | **Real defect caught** — 47 KB loop verified in OWUI chat `81ce828a`. Keep |
| Slow-seat WARN ≥180 s (`36b88683e`) | 7 baseline rows ≥180 s (max 353.9 s) would all be WARN now | Signal, not failure; colors verdicts vs baseline. Keep but read with §3 deadline context |
| Inter-phase gate hardening (`c72e7a0a6`, `9e73ab334`, `9c8d4471e`, `4743b3e89`) | C run: 180 BLOCKED, **nothing recorded** | Block-on-infra is correct; **non-recording was a harness defect** — fixed on this branch |
| Turn graded "completed" on router error notice | research C WARN despite error-frame content | **Grader defect** — fixed on this branch (stream-error notice → FAIL infra) |
| Persona contract exact-wording grader | persona-destructive C FAIL | Artifact — already fixed by `cc40a20d0` |
| Stage-5 graders measure artifact+answer (`f96586229`), WAV upload (`5c084abc6`), hunt contract (`29ca82a0e`), memory disambiguation (`a5f4f341a`) | music-audio FAIL (async job), hunt FAIL→PASS | music-audio expectation mismatches the async ACE-Step contract; others verified working on N |
| Provenance/lineage stamping (`eb6ab69c8`), trace verification (`3272c81a6`), p0-load-guard probe (`3f1c924c2`) | run_meta + per-row SHA | Positive; baseline had none of this (hence the SHA derivation in §0) |

## 5. Ranked harm list

1. **300 s whole-turn cap (`7dbefe845`)** — kills healthy long turns (research completed at
   269.8 s baseline; baseline also has 353.9 s and 336.3 s PASS rows), produced the C-run cascade
   (killed turn → engine busy at gate → 180 BLOCKED), and degrades user-visible answers to an
   error frame. Not reverted: it fixes a real unbounded-wait defect and three commits build on it.
   Remediation brief: `coding_task/BRIEF_TURN_DEADLINE_TOTAL_CAP_20261126.md`.
2. **Unrecorded gate failure (harness)** — 76 % of the C run was unblockable-undiagnosable.
   **Fixed on this branch**: blocked rows now carry the failing check detail and the run dir gets
   `gate_blocked_<phase>.json`.
3. **safety_guard Layer B (`d5d4a20b2`/`817209717`)** — replaced legitimate tool results with
   injection refusals (compliance-multiframework C FAIL). Already reverted by `3fab2e074`;
   recorded here for the ledger.
4. **ctx32k seat upgrades (`b8d336e9c`, `02383c16c`)** — evidence-backed seat decisions, but they
   pushed `auto-research` past the new 300 s cap. Interaction effect, not a revert candidate
   (seated models are evidence-chosen; needs an A/B if changed).
5. **Browser-GUI stage-5 default (`df171d9fd`)** — per-row wall cost and one budget TimeoutError
   FAIL; keep coverage, give budgets headroom.
6. **Stream-error turns graded "completed" (harness)** — **fixed on this branch**.
7. **Engine upgrades (oMLX 0.8.3 queued-unload semantics, Ollama 0.40.18)** — plausible
   contributor to eviction-budget failures at gates; unproven, no version-pinned evidence either way.

## 6. Side-by-side pace table (rows present in baseline and either current run)

Statuses/durations: baseline | cfe67a16e | 52e1a5fc4 (snapshot 16:12Z). Seat column shows drift.

| scenario | base | dur | cfe67a16e | dur | 52e1a5fc4 | dur | base seat | now seat |
|---|---|---|---|---|---|---|---|---|
| p0-execute-preflight | PASS | 0.4 | PASS | 0.4 | PASS | 0.4 | — | — |
| p0-exposure-gap | PASS | 0.3 | PASS | 0.3 | PASS | 0.3 | — | — |
| p0-lab-ready | PASS | 3.1 | PASS | 3.1 | PASS | 2.9 | — | — |
| p0-portal-trace | FAIL | 6.9 | WARN | 7.2 | WARN | 8.2 | — | — |
| p0-retired-aliases | PASS | 0.3 | PASS | 0.3 | PASS | 0.3 | — | — |
| p0-routing-baseline | PASS | 4.1 | PASS | 4.7 | PASS | 4.9 | — | — |
| p0-sweep-freshness | PASS | 0.0 | PASS | 0.0 | PASS | 0.0 | — | — |
| s1-hardening | PASS | 0.2 | PASS | 0.2 | PASS | 0.2 | — | — |
| s2-p1-auto | PASS | 34.4 | PASS | 30.5 | PASS | 30.5 | auto | auto → hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k |
| s2-p1-auto-audio | PASS | 14.5 | PASS | 20.4 | PASS | 16.3 | gemma4:12b-it-qat-ctx8k | gemma4:12b-it-qat-ctx8k → gemma4:12b-it-qat-ctx16k |
| s2-p1-auto-audio::image | PASS | 8.2 | PASS | 8.3 | PASS | 8.3 | granite4.1:8b-ctx16k | — |
| s2-p1-auto-audio::music | PASS | 8.3 | PASS | 6.3 | PASS | 8.3 | lfm2.5:8b-ctx8k | lfm2.5:8b-ctx8k → lfm2.5:8b-ctx16k |
| s2-p1-auto-audio::video | PASS | 4.3 | PASS | 6.3 | PASS | 4.2 | granite4.1:8b-ctx16k | — |
| s2-p1-auto-coding | PASS | 16.3 | PASS | 18.4 | PASS | 16.4 | Qwen3.8-27B-oQ4e-mtp | — |
| s2-p1-auto-coding::bigfix | PASS | 129.0 | FAIL | 127.5 | PASS | 8.3 | Qwen3-Coder-30B-A3B-Instruct-4bit | — |
| s2-p1-auto-coding::cad | PASS | 66.6 | PASS | 52.7 | PASS | 26.5 | Qwen3-Coder-30B-A3B-Instruct-4bit | — |
| s2-p1-auto-compliance | PASS | 80.7 | PASS | 70.8 | PASS | 14.4 | hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k | hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k → Qwen3.8-27B-oQ4e-mtp |
| s2-p1-auto-compliance::reading | PASS | 16.3 | PASS | 10.3 | PASS | 10.3 | mlx-community--gemma-4-26b-a4b-it-4bit | — |
| s2-p1-auto-daily | PASS | 30.4 | PASS | 34.6 | PASS | 34.6 | hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k | — |
| s2-p1-auto-daily::deep | PASS | 38.4 | PASS | 18.5 | PASS | 18.5 | Qwen3.8-27B-oQ4e-mtp | — |
| s2-p1-auto-daily::fast | PASS | 26.3 | PASS | 28.6 | PASS | 14.3 | unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit | — |
| s2-p1-auto-daily::inkling | PASS | 58.6 | PASS | 26.6 | PASS | 26.5 | inkling-2-mini:ctx256k | — |
| s2-p1-auto-daily::nemotron | PASS | 22.4 | PASS | 28.6 | PASS | 24.4 | hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k | — |
| s2-p1-auto-documents | PASS | 12.3 | PASS | 12.4 | PASS | 14.3 | gemma-4-26b-a4b-it-QAT-4bit | — |
| s2-p1-auto-general-uncensored | PASS | 22.4 | PASS | 18.4 | PASS | 18.4 | hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:q4_K_M-ctx8k | hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:q4_K_M-ctx8k → Inkling-2-Mini-abliterated-oQ4e-mtp |
| s2-p1-auto-reasoning | PASS | 22.4 | PASS | 22.5 | PASS | 22.4 | hf.co/bartowski/K2-Horizon-MoVA-36B-A4B-GGUF:Q4_K_M-ctx64k | — |
| s2-p1-auto-reasoning::math | PASS | 26.4 | PASS | 32.6 | PASS | 24.4 | glm-4.7-flash:Q4_K_M-ctx24k | — |
| s2-p1-auto-research | PASS | 34.4 | PASS | 34.6 | PASS | 26.5 | hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M-ctx16k | hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M-ctx16k → hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M-ctx32k |
| s2-p1-auto-security | PASS | 4.2 | PASS | 22.5 | PASS | 12.3 | VulnLLM-R-7B-4bit | VulnLLM-R-7B-4bit → Inkling-2-Mini-oQ4e-mtp |
| s2-p1-auto-spl | PASS | 40.5 | PASS | 50.8 | PASS | 14.4 | Qwen3.8-27B-oQ4e-mtp | — |
| s2-p1-auto-vision | PASS | 60.6 | PASS | 69.0 | PASS | 87.1 | qwen3-vl:32b-ctx8k | qwen3-vl:32b-ctx8k → qwen3-vl:32b-ctx16k |
| s2-p1-security-reviewer | PASS | 10.3 | PASS | 10.3 | PASS | 10.3 | granite4.1:8b-ctx8k | granite4.1:8b-ctx8k → granite4.1:8b-ctx16k |
| s2-p1-ui-roster | PASS | 100.2 | PASS | 41.7 | PASS | 58.0 | — | — |
| s2-p2-auto-reasoning | PASS | 52.5 | PASS | 48.8 | PASS | 46.8 | hf.co/bartowski/K2-Horizon-MoVA-36B-A4B-GGUF:Q4_K_M-ctx64k | — |
| s2-p2-auto-reasoning::math | PASS | 40.5 | PASS | 63.0 | PASS | 40.7 | glm-4.7-flash:Q4_K_M-ctx24k | — |
| s2-p2-auto-research | PASS | 269.8 | WARN | 302.2 | FAIL | 301.6 | hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M-ctx16k | hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M-ctx16k → hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M-ctx32k |

totals: baseline 1266s; C-run 1233s over 36 common rows; N-run 956s over 36 common rows

## 7. What the orchestrator must verify live

See `## ORCHESTRATOR RUNS` in the worker report. The N run had not finished at writing time; the
`s4-*`/`s3-*` blocks (which contain the baseline's 353.9 s / 336.3 s / 296 s rows) are the rows
most at risk from the 300 s cap and had not been reached yet.
