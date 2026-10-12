# WFE Prompt Surface Rebaseline — Closeout

- **Campaign:** `wfe_prompt_surface_rebaseline_20261012`
- **Measurement HEAD:** `2c2fd0cdb95a4da34d63d697d2aedf877aa8a571`
- **Prompt/tool-surface fix:** `1394c0dd`
- **Runtime:** Ollama `0.40.0`; Portal stack up; images rebuilt before P1.

## Decision

The affected incumbent baseline is now `wfe_prompt_surface_rebaseline_20261012`. The seven incumbents ran only on their home suites at n=3. Nothing was promoted or removed, and `config/portal.yaml` is unchanged. The four prompt-byte-identical workspaces retain their prior baselines.

## P0 — Discovery and smoke

At HEAD, `workspace_context(ws)['harness_note']` identified **7 affected workspaces**: `auto-compliance`, `general-deep`, `tools-specialist`, `tools-specialist::fast`, `auto-research`, `auto-coding::fast-repair`, `auto-coding::laguna`. The unaffected set is `auto-coding`, `auto-coding::uncensored`, `auto-documents`, and `auto-general-uncensored`.

The plan at `tests/wfe/plans/prompt_surface_rebaseline.yaml` contains only each affected incumbent and its home suite. Its header links this task and records R5 for future card-reasoning candidates. Home suite counts were 11 compliance, 3 research, and 3 coding tasks; across 7 workspaces and three repeats the dry-run returned **87 rows** and **zero `WARN prompt/tool surface` lines**.

The auto-compliance smoke returned **PASS**. Its debug record ends with the `WFE HARNESS TOOLS:` note, `think=false`, lane sampling (temperature 0.3, top-p 0.95, top-k 20, min-p 0, repeat penalty 1.1, max tokens 24,576), and exactly six tools: `file_read`, `file_list`, `repo_search`, `pytest_run`, `file_write`, `http_get`. Receipt: `tests/wfe/results/debug/wfe_prompt_surface_rebaseline_smoke_20261012/`.

R2 check found the pipeline image predated `1394c0dd`; `./launch.sh rebuild` completed before P1. Stack remained up. P1 ran one request at a time, one arm per process, in the required order. The memory watchdog reported no trip.

## P1/P2 — Before and after

`P/F/B/H/R` means PASS / FAIL / BUDGET_EXHAUSTED / HARNESS_ERROR / REFUSED. Turn-cap loops count `BUDGET_EXHAUSTED` rows with at least 16 turns. Median wall time uses every row with a recorded wall time.

| Workspace | Incumbent · suite | Before P/F/B/H/R | After P/F/B/H/R | Turn-cap loops | Median wall (s) | Pre-fix source / comparability |
|---|---|---:|---:|---:|---:|---|
| `auto-compliance` | compliance_agentic · `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | P18 / F5 / B8 / H2 / R0 | P22 / F5 / B3 / H0 / R3 | 8 → 3 | 23.1 → 20.0 (-3.1) | `saluki_spike_20261011`; same Ollama 0.40.0; prompt surface changed |
| `general-deep` | research · `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` | P9 / F0 / B0 / H0 / R0 | P9 / F0 / B0 / H0 / R0 | 0 → 0 | 28.3 → 27.8 (-0.5) | `saluki_spike_20261011`; same Ollama 0.40.0; prompt surface changed |
| `tools-specialist` | coding · `granite4.1:8b-ctx8k` | P6 / F0 / B3 / H0 / R0 | P6 / F0 / B3 / H0 / R0 | 3 → 3 | 14.3 → 14.8 (+0.5) | `wfe_full_20260911`; pre-fix Ollama 0.33.2 vs post-fix 0.40.0; prompt surface changed |
| `tools-specialist::fast` | coding · `gemma4:e4b-it-qat-ctx8k` | P9 / F0 / B0 / H0 / R0 | P7 / F2 / B0 / H0 / R0 | 0 → 0 | 42.0 → 36.5 (-5.5) | `engine_ab_ollama_040`; pre-fix WFE_ENGINE=pipeline vs post-fix direct Ollama; prompt surface changed |
| `auto-research` | research · `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M-ctx16k` | P9 / F0 / B0 / H0 / R0 | P9 / F0 / B0 / H0 / R0 | 0 → 0 | 6.2 → 3.9 (-2.3) | `wfe_full_20260911`; pre-fix Ollama 0.33.2 vs post-fix 0.40.0; prompt surface changed |
| `auto-coding::fast-repair` | coding · `kat-coder-v2.5-dev:Q4_K_M-ctx32k` | P8 / F1 / B0 / H0 / R0 | P9 / F0 / B0 / H0 / R0 | 0 → 0 | 20.9 → 25.9 (+5.0) | `engine_ab_ollama_040`; pre-fix WFE_ENGINE=pipeline vs post-fix direct Ollama; prompt surface changed |
| `auto-coding::laguna` | coding · `portal5/laguna-xs21:q4_K_M-ctx128k` | P9 / F0 / B0 / H0 / R0 | P7 / F0 / B2 / H0 / R0 | 0 → 2 | 21.7 → 36.3 (+14.6) | `wfe_laguna21_seat_20260925`; pre-fix Ollama 0.34.2 vs post-fix 0.40.0; prompt surface changed |

The P1 total was **69 PASS, 7 FAIL, 8 BUDGET_EXHAUSTED, 3 REFUSED, 0 HARNESS_ERROR** across 87 rows. Auto-compliance turn-cap loops fell from **8/33 to 3/33**; its PASS count rose from 18 to 22, while 3 rows were REFUSED. Tools-specialist remained at 3/9 turn caps; Laguna had 2/9 new turn caps. These outcomes are retained without retry.

The comparisons are descriptive. The served prompt changed by design. In addition, tools-specialist and auto-research pre-fix runs used Ollama 0.33.2; the fast-tools and fast-repair pre-fix runs used `WFE_ENGINE=pipeline`; Laguna used Ollama 0.34.2. The current campaign used direct Ollama 0.40.0. These differences prevent treating the deltas as a controlled estimate of the prompt fix alone.

## R6 — Loop attribution

The auto-compliance `comp-reading-contract-01` user instruction requires `compliance_requirement` first and says to call `compliance_ask`; neither is among the six WFE proxy tools. The served system prompt now clearly names the proxy surface and says unavailable production tools do not exist, but the task still explicitly demands them. All three baseline repeats exhausted the cap without calling a compliance tool. A seeded n=3 no-format control also looped 3/3 (17 turns, 21–24 tool calls, zero tool errors), so the JSON clause did not drive it. A card-think n=3 control at Qwen sampling also looped 3/3 (17 turns, 28–34 tool calls). The direct task/tool mismatch is the attributed cause; no model-specific blame is assigned.

Qwen’s first post-tool prompt was captured on the actual `/v1` request and compared with Ollama’s exposed Jinja template. Across the no-format and think-on captures, actual counts were 35 tokens below the rendered prompt with the trailing newline removed (36 below the exact render); the known newline explains one token, leaving 35 unexplained. That route/render delta remains open and is not assigned to the model.

For tools-specialist, `code-kv` exhausted at 17 turns in all three incumbent rows. Its Granite 4.1 card says it has no reasoning mode, and the coding task contains no output-format clause, so think-on and no-format controls are N/A. The actual calls and arguments are in the debug receipt. Under R6, the same-instrument incumbent loop is classified as an instrument/task interaction; no model-specific cause is asserted.

For Laguna, the think-off baseline had 2/9 code-kv turn caps. The card-think control at temperature 1.0, top-p 1.0, top-k 20, n=3 returned 2 PASS and 1 BUDGET_EXHAUSTED (17 turns). This supports a lane-fit contribution but is mixed and not a loop-free result. Ollama exposes only the Go template `{{ .Prompt }}` for this tag, not the official embedded Jinja, so the exact token comparison is unavailable. No model-specific cause is asserted.

A separate direct-native API think-on attempt for Qwen returned one HARNESS_ERROR at turn 2 (`HTTP 400` while replaying tool-call arguments). It is recorded as an instrument error and was not retried into a pass. The card-think results above use the existing `/v1` route with fresh seeds.

## P3 — Records, gates, and delivery

Delivery records include the plan, P0 smoke record, P1 manifest, aggregate report, public row/debug/preflight receipts, generated fitness report, this closeout, the compact JSON receipt, and the updated WFE wiki unit. The complete campaign remains in the ignored local results tree. The public commit omits two raw records flagged by the HK provenance scan: `tests/wfe/results/campaigns/wfe_prompt_surface_rebaseline_20261012/debug/hf.co_unsloth_Qwen3.8-27B-GGUF_Q4_K_M-ctx32k.debug.jsonl` and `tests/wfe/results/campaigns/wfe_prompt_surface_rebaseline_20261012/rows/5cab39ab6240.json`. Both files remain locally; the aggregate report and compact receipt retain outcomes and R6 attribution without the matched text. The wiki now names this campaign as the current baseline. A scan found no other portal-wiki fact unit quoting a pre-fix PASS rate for an affected workspace. The generated fitness report flags `tools-specialist` repeats as deterministic because its temperature is 0; those three rows are repeated observations, not independent draws.

R7 decision from the evidence: retain all current seat/configuration decisions; this task is a measurement rebaseline only. Future card-reasoning candidates must be measured separately at lane policy and card think+sampling.

**Gate status:** `uv run pytest tests/unit portal/modules/security/tests -n auto -x --tb=short -q` passed (4,822 passed, 6 skipped; 369.25s). `bash scripts/ci_local.sh` passed: Ruff, formatting, mypy, and the Python 3.12 unit run (4,822 passed, 6 skipped; 387.92s).

## Review corrections (2026-10-12)

A review of this closeout found that the run did not produce the baseline the task was for: a seat baseline future challengers can be compared against. The Decision above is withdrawn. `wfe_prompt_surface_rebaseline_20261012` stands only as a direct-engine measurement.

1. **Wrong engine, and the fix was absent from the standard engine.** Every row ran direct Ollama (`WFE_ENGINE` unset). The WFE fitness unit names pipeline mode as the seat-testing path. In pipeline mode `campaign.run_row` sent `system_prompt_base`, which never carried the harness note, so a pipeline run would have reproduced the pre-fix mismatch. Fixed: `workspace_context` returns `system_prompt_pipeline` (base + note; the pipeline adds the append), and the note's wording no longer depends on its position.
2. **"Zero WARN" was vacuous.** `prompt_tool_mismatches` returns nothing once the note marker is present, and the audit never read user turns. The success criterion could not fail, and it missed `comp-reading-contract-01`, whose user turn demands `compliance_requirement` / `compliance_ask`. Fixed: the audit flags a task whose instruction demands a tool the surface lacks.
3. **`comp-reading-contract-01` cannot pass in WFE.** Its checker scores the `compliance_ask` receipt, and the harness offers no compliance tools in any engine mode. Every recorded run (6 in `saluki_spike_20261011`, 3 here, 6 R6 controls) hit the turn cap. The R6 controls could not change that. Fixed: the task declares `requires_tools`, and the runner returns BLOCKED (an instrument outcome excluded from rates) without a model call.
4. **The 3 REFUSED rows were wrong answers.** They were complete ABSTAIN/PARTIAL JSON answers ending with `DETERMINATION COMPLETE`, and their rationales contained "I cannot …". The refusal relabel now skips a reply that carries the task's completion signal. An offline `rescore_debug_dir` of this campaign, with no model calls, moves exactly those 3 rows from REFUSED to FAIL. Auto-compliance therefore reads P22 / F8 / B3, not P22 / F5 / B3 / R3, and its wrong answers rose from 5 to 8 against the pre-fix run.
5. **`comp-p6j-06` (expected ABSENT; incumbent ABSTAIN 3/3).** The key is right. In all 30 p6j packets, `packet_complete: false` maps to ABSTAIN and a null candidate in a complete packet maps to ABSENT. That matches the module (`assessment.py`: an exhaustive search with no candidate gives ABSENT, a non-exhaustive one gives UNRESOLVED). The instruction never defined `packet_complete`, and it now does in both compliance suites.
6. **R6 controls are not reproducible.** They ran from uncommitted scripts with receipts in `/tmp`. V2 runs controls as plan arms with overrides, inside the campaign directory.
7. **Not investigated:** the `tools-specialist::fast` regression (2 FAILs at turn 1, a plan written but no tool call). It is in V2 scope under pipeline mode.

The comparisons and the R5/R7 decisions above remain descriptive history. The seat baseline is TASK_WFE_PROMPT_SURFACE_REBASELINE_V2.
