# WFE Prompt Surface Rebaseline V2 — Seat Baseline Closeout

- **Campaign:** `wfe_prompt_surface_seat_20261012` (pipeline mode, 87 rows, n=3)
- **Measurement HEAD:** `2b27d8c4` (includes the R8 instrument fix below)
- **Supersedes:** `wfe_prompt_surface_rebaseline_20261012` as the baseline for the affected
  workspaces. V1 remains a direct-engine reference only; its rows are not row-comparable
  with V2 (note wording and the p6j `packet_complete` definition changed).
- **Runtime:** Ollama `0.40.0`; oMLX healthy (one mid-arm outage, recorded per row);
  Portal stack up; pipeline image verified fresh (built 09:08, after the last
  `portal/`+`config/` commit at 07:59).

## Review corrections (2026-10-13)

A review of this closeout found that the seat baseline it declares is not valid, and that
its headline attribution rests on a confound. The Decision below is withdrawn.
`wfe_prompt_surface_seat_20261012` stands only as a diagnostic run. The seat baseline is
TASK_WFE_PROMPT_SURFACE_REBASELINE_V3. The instrument fixes below are in `tests/wfe/`,
with a unit test for each.

1. **19 of the 30 auto-compliance rows are not seat evidence.** The seat is the oMLX alias
   `Qwen3.8-27B-oQ4e-mtp`. 17 rows ran entirely on the Ollama failover and 2 switched
   engine mid-row. The R8 fix `2b27d8c4` accepted the raw tag as well as the alias, so
   failover rows counted as seat rows. Fixed: `seat_primary()` resolves the one model
   production routes to (routing groups, then backend priority), and every model turn of
   a pipeline row must be served by it. A failover turn or a missing trace makes the row
   BLOCKED (`not seat evidence:`), offline rescore keeps it BLOCKED, and the arm stops at
   the first such row.
2. **The "oMLX loops, Ollama passes" split compares different tasks.** The failover
   window covered p6j-02 r1 through p6j-11 r2, so p6j-14/19/24 never ran on Ollama and
   p6j-03/05/06/09 never ran on oMLX. The control table's "seat 11/18" row mixed both
   engines. No committed Ollama-engine arm exists, so the engine factor of the
   "seat × think-off × format clause" conjunction is unmeasured. The attribution is
   withdrawn.
3. **The mid-arm "manual unload" was the pipeline, not an outside actor.** The pipeline
   log shows the sequence:
   - At 22:47:04Z a tool-loop request to oMLX timed out, and the pipeline fell back to
     Ollama.
   - Ollama cold-loaded the 27B GGUF.
   - `load_guard` freed the "idle" oMLX seat through `/admin/api/models/…/unload`.
   - From 22:49Z every reload of the seat was refused with HTTP 507 ("does not fit under
     the dynamic memory ceiling") while the GGUF stayed resident.

   VulnLLM-R-7B was preloaded by the pipeline's own warmup at the 22:40Z container
   recreate and expired on oMLX's 300 s TTL at 22:45:33Z; no external probes were
   involved. `execute_arm` also kept the raw Ollama tag resident (`drain_others(model)`)
   while the seat was the oMLX alias. Fixed: the arm keeps nothing on Ollama when its
   seat is an alias. The production failover chain is recorded for V3.
4. **Loops were fed by two harness defects.**
   - `repo_search(pattern, <file>)` ignored the file and grepped the whole sandbox. The
     model asked for `nerc_cip_map.json`, got back the same `packet.json:3` line, and
     repeated the call up to 12 times (p6j-14 r1/r2).
   - The packet tasks could read the whole repository, including Portal's compliance
     source and `config/compliance/y21_resolutions.yaml` /
     `tests/unit/test_compliance_y21_error_classes.py`, which discuss P6J-14 and P6J-19 by
     id. 11 of the 12 compliance loop rows read compliance repo files; no PASS row did.

   Fixed: a scoped `repo_search` searches only that path, and a missing path is an error.
   Every compliance packet task declares `repo_read: false`, so the sandbox has no
   repository fallback and the tool description says so. Production's compliance seat has
   no repository either.
5. **General-deep's prompt names `/workspace`, which the harness did not map.**
   res-ollama-ctx r1 tried `/workspace/...` paths 13 times, and every read errored.
   Laguna's code-kv also wrote to `/workspace/parse_kv.py`. Fixed: `/workspace` and
   `/workspace/uploads` map to the sandbox root. The closeout's "zero tool errors inside
   the loops" was also wrong: the tool log's `error` flag marked only argument-parse
   failures. It now marks dispatch errors as well.
6. **tools-specialist's 6 FAILs are an engine delivery fault, not "mxfp8 writes invalid
   Python".** All six rows end on the pipeline's placeholder "⚠️ The model did not
   produce an answer. Please retry.", and the three code-fix-fizz rows made no file write.
   A replay of the code-fix-fizz turn reproduces it:
   - granite-4.1-8b-mxfp8 emits `<tool_call>{"name": "file_read", "arguments": {…}}}`,
     with one extra `}`.
   - Non-streamed, oMLX returns that text.
   - Streamed, which is the production path, oMLX drops it and returns empty content
     with `finish_reason=stop`. The pipeline then substitutes the placeholder.

   The runner scored the placeholder as the model's answer. Fixed: the placeholder is
   stripped and flagged (`evidence.pipeline_no_answer`, notes prefix). The engine defect
   affects production tools-specialist users and is recorded for V3.
7. **The laguna code-kv "loops" are an instruction/key mismatch.** The instruction said
   a backslash-escaped semicolon is `\\;` (two backslashes, as the model reads it). The
   hidden suite tests `r"note=a\;b"` (one). In all five laguna code-kv turn-cap rows
   (seat r0/r1, card-think r0/r1/r2) the hidden suite passed 7/7: the parser was
   right, and the model was chasing its own tests written to the instruction. The
   tools-specialist backslash literal sits in the same spot. Fixed: the instruction
   names `\;`. Code-kv rows from before the fix are not comparable.
8. **R6 protocol steps were skipped.**
   - Item 3: the no-format control ran on oMLX only, not on the production engine.
   - Item 4: no rendered post-tool prompt was captured. The P0 smoke checked the
     system message only.
   - No thresholds were recorded before the run.
   - General-deep's loops had no control at all.
9. **The pipeline's stream error frames were read as empty answers.** `_parse_stream_v1`
   ignored a `data: {"error": …}` frame, and no V2 row hit one. Fixed: an error frame
   raises, giving HARNESS_ERROR.

A wider audit of every evaluation instrument followed; see `docs/WFE_INSTRUMENT_AUDIT_20261013.md`. It found, among others, that WFE measured an arbitrary persona prompt instead of the workspace's, and that challengers ran at the incumbent's sampling.

The P0 receipts, the V1 offline regrade and the comp-p6j-06 result stand. Everything
under "P2 — Results and deltas" and "R6 loop attribution" below is descriptive history,
not a baseline or an attribution.

## Decision

The seat baseline for the seven affected workspaces is
`wfe_prompt_surface_seat_20261012`: every incumbent scored on its home suite **as the
workspace serves it**, `WFE_ENGINE=pipeline`, `.env` sourced for `PIPELINE_API_KEY`, one
request in flight, one arm per process, campaign drains as the swap/memory guard. Nothing
was promoted, removed, or reconfigured; `config/portal.yaml` is unchanged.

Four of the seven seats are served through committed production aliases
(`config/backends.yaml` workspace_routing → priority-10 oMLX groups), so the seat number is
an oMLX-seat number for auto-compliance, general-deep, tools-specialist and
auto-coding::laguna, and an Ollama number for tools-specialist::fast, auto-research and
auto-coding::fast-repair. The per-row `evidence.served_models` field records which engine
served every row; the comparison table reports both where they split.

## P0 — Preflight receipts (no model calls except the smoke and preflight probes)

1. **Unit tests.** `uv run pytest tests/wfe/tests -q`: **215 passed** at start, including
   `test_pipeline_run_row_sends_the_note` and
   `test_home_compliance_suite_has_no_unblocked_tool_demand`. **217 passed** after the R8
   fix added two tests.
2. **Affected set.** Re-derived at HEAD 6f6819dc from
   `workspace_context(ws)["harness_note"]` across `tests/wfe/workloads.yaml` and
   `tests/wfe/plans/*.yaml`: the same **7 workspaces** as V1 (auto-compliance,
   general-deep, tools-specialist, tools-specialist::fast, auto-research,
   auto-coding::fast-repair, auto-coding::laguna). Every incumbent `model_hint` is
   unchanged since V1, so the plan arms carried over (header comment updated to cite V2).
3. **Dry run.** `WFE_ENGINE=pipeline … --dry-run`: **87 rows** (11 compliance + 3 research
   + 3 coding tasks × 7 workspaces × 3 repeats), **zero `WARN prompt/tool surface` lines**.
   Exactly 3 rows are `comp-reading-contract-01`; by construction
   (`requires_tools` ⊄ harness surface, `runner.py` run_task) they return BLOCKED with no
   model call.
4. **Pipeline smoke** on auto-compliance (`--smoke`). The trace stores bodies only with
   `PORTAL_TRACE_BODIES=1`, so the flag was enabled in the untracked `.env`, the pipeline
   container recreated, the smoke run, the trace pulled, and the flag reverted (container
   recreated at 0) — the pipeline's own debug-logging route, no repo change. Receipt:
   `tests/wfe/results/campaigns/wfe_prompt_surface_seat_20261012/p0/smoke_trace_checks.json`.
   From `bodies.backend_request` — the request **as received by the model** — on all four
   task turns:
   - served model `Qwen3.8-27B-oQ4e-mtp` on backend `omlx-reasoning` — the incumbent tag
     `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` through its committed production alias;
   - the received system message contains `WFE HARNESS TOOLS:` **and** the workspace
     `system_prompt_append` (note before append — the pipeline injects the append last,
     production preinject order);
   - exactly the six harness tools (`file_read file_list repo_search pytest_run file_write
     http_get`);
   - think off (`chat_template_kwargs.enable_thinking=false` — the pipeline applies the
     workspace's `think: false`; the client correctly sends no think field in pipeline
     mode) and lane sampling (temperature 0.3, top_p 0.95, top_k 20, min_p 0,
     repetition_penalty 1.1). The output cap is redacted in traces ("max_tokens" contains
     "token"); the pipeline applies the seat `predict_limit` 24576 from portal.yaml.
   The smoke row itself (comp-p6j-01) scored FAIL — the model answered PARTIAL against a
   SUPPORTED key, a model outcome, not an instrument failure.
5. **Positive control for the audit.** `audit_workspace` on a copy of the compliance suite
   with `requires_tools` removed from `comp-reading-contract-01` emits
   `task comp-reading-contract-01 demands tool not in harness surface: compliance_ask` and
   `…: compliance_requirement`; the unmodified suite is clean. The zero-WARN receipt can
   fail. Receipt: `…/p0/positive_control.json`.

### R8 instrument fix found and fixed in P0 (own commit)

The first smoke **did not start**: `preflight_pipeline` returned REVIEW — "pipeline served
'Qwen3.8-27B-oQ4e-mtp', arm is 'hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k'". The
served-model checks (preflight and the per-row guard) compared the served id to the raw arm
tag, but production routing deliberately aliases the tag onto the oMLX seat. Under the raw
check every aliased seat would REVIEW at preflight, and `--force` would not have helped:
the per-row guard would have BLOCKED every row the same way. A seat baseline was
impossible by construction — an instrument defect in the seat path (R8), fixed in commit
`2b27d8c4`: `seat_served_candidates()` resolves the arm tag through `workspace_routing` +
group aliases; the alias target and the raw tag are both accepted, any third model is
still a mismatch. Unit-tested (`test_seat_served_candidates_resolve_the_production_alias`,
`test_preflight_pipeline_accepts_alias_rejects_drift`); no rows existed to re-run.

## P1 — Run

Arms ran in the required order, each in its own process, appended into one campaign
(manifest backed up with `cp` before every `--append`, R4): auto-compliance (33 rows,
2160s), general-deep (558s), tools-specialist (296s), tools-specialist::fast (420s),
auto-research (190s), auto-coding::fast-repair (181s), auto-coding::laguna (390s). No
HARNESS_ERROR anywhere; the 3 BLOCKED rows are the expected `comp-reading-contract-01`
instrument outcome, excluded from rates.

**Mid-arm fallback, recorded per row.** Auto-compliance rows p6j-02 r1 through p6j-11 r2
(17 rows) were served on the raw Ollama tag because oMLX went absent: its log shows
VulnLLM-R-7B-4bit loaded at 22:40:30Z (external max_tokens=1 probes), both models unloaded
at 22:45:33Z and 22:47:05Z (the Qwen unload is `admin.routes … Manually unloaded`), and
Qwen3.8-27B-oQ4e-mtp reloaded at 23:01:10Z. The pipeline fell back, the row guard accepted
the raw tag as the arm's registered candidate, and `evidence.served_models` records the
split. The fallback window is itself the strongest R6 evidence (below).

## P2 — Results and deltas

`P/F/B/BLK` = PASS / FAIL / BUDGET_EXHAUSTED / BLOCKED. Turn-cap loops count B rows at ≥16
turns. Rates exclude BLOCKED.

| Workspace | Seat served | P/F/B/BLK | Loops | Median wall | vs pre-fix pipeline | vs V1 direct (regraded) |
|---|---|---|---:|---:|---|---|
| auto-compliance | oQ4e-mtp ×13, GGUF ×17, BLK ×3 | 16/2/12/3 | 12 (11 oMLX, 1 Ollama) | 30.4s | none exists (`saluki_spike_20261011` is direct — labeled so) | P22/F8/B3, loops 3 → wrong answers 8→2 but loops 3→12 |
| general-deep | oQ4e-mtp ×9 | 6/0/3/0 | 3 | 30.1s | none exists (same label) | P9 → P6/B3 |
| tools-specialist | granite-4.1-8b-mxfp8 ×9 | 3/6/0/0 | 0 | 23.8s | none in pipeline at 0.40.0; historical `wfe_full_20260911` (Ollama 0.33.2) P6/B3 | loops 3→0, FAILs 0→6 |
| tools-specialist::fast | gemma4:e4b-it-qat-ctx8k (raw, Ollama) | 9/0/0/0 | 0 | 41.3s | `engine_ab_ollama_040` P9, 42.0s → unchanged | P7/F2 → P9 (V1's two turn-1 FAILs gone) |
| auto-research | Nex-N2-mini (raw, Ollama) | 9/0/0/0 | 0 | 4.6s | `engine_ab_ollama_040` P9, 4.5s → unchanged | P9 → P9 |
| auto-coding::fast-repair | kat-coder (raw, Ollama) | 7/2/0/0 | 0 | 19.0s | `engine_ab_ollama_040` P8/F1, 20.9s → −1 PASS | P9 → P7/F2 |
| auto-coding::laguna | Laguna-XS-2.1-4bit ×9 | 7/0/2/0 | 2 (code-kv) | 21.6s | none in pipeline at 0.40.0; historical `wfe_laguna21_seat_20260925` (Ollama 0.34.2) P9 | P7/B2 → P7/B2 (same two code-kv loops) |

Totals: **57 PASS, 10 FAIL, 17 BUDGET_EXHAUSTED, 3 BLOCKED, 0 HARNESS_ERROR, 0 REFUSED.**

**The seat split inside auto-compliance is the headline.** Same checkpoint, same suite,
same served prompt and tools, same turn cap: rows served on the oMLX alias went
**P1 / F1 / B11 (11 of 13 looped, median 99.2s)**; rows served on the Ollama GGUF fallback
went **P15 / F1 / B1 (median 23.1s)**. general-deep, whose nine rows all ran on the oMLX
alias after it recovered, looped 3/9. Every other seat looped 0 except laguna's two
code-kv rows.

### V1 offline regrade (R8 rescore, no model calls)

`rescore_debug_dir` on a `cp` of V1's debug dir (no `--campaign-id`, so nothing wrote
back): 87 runs re-scored, **exactly 3 verdicts changed, all REFUSED → FAIL on
auto-compliance** (comp-p6j-06 r0, r1; comp-p6j-09 r2) — as predicted by the V1 review.
Regraded V1 numbers are used in the table above. Receipt:
`tests/wfe/results/campaigns/wfe_prompt_surface_seat_20261012/p2/v1_rescore_receipt.txt`
and `v1_regraded_summary.json`.

### Answers to the task's specific questions

- **auto-compliance:** with `comp-reading-contract-01` BLOCKED, turn-cap loops remain:
  **12 of 30** countable rows (p6j-14 ×3, p6j-19 ×3, p6j-24 ×2, p6j-01 ×2, p6j-02,
  p6j-11). `comp-p6j-06` **moved off ABSTAIN: 3/3 PASS** with `packet_complete` now
  defined (as did p6j-03/05/09). Remaining wrong answers, one line each:
  - `comp-p6j-01` r0 (oMLX): answered `PARTIAL` where the key is `SUPPORTED` — hedged on
    whether a fixed 35-day cycle satisfies a maximum-interval premise instead of supporting.
  - `comp-p6j-11` r1 (Ollama fallback): answered `PARTIAL` where the key is `ABSENT` — the
    rationale itself names the missing R2 testing obligation, then stops short of ABSENT.
- **tools-specialist::fast:** V1's two turn-1 FAILs (plan written, no tool call) **did not
  recur**: the seat went 9/9, matching the pre-fix pipeline rows (9/9). No
  request/response comparison was needed; the direct-mode regression did not reproduce on
  the seat path, so the note is not implicated.
- **tools-specialist `code-kv` (R6):** no loop anywhere — the mxfp8 seat instead writes
  **syntactically invalid Python** (`if c == '\':` — unterminated string literal,
  recorded verbatim in `tool_call_log`), so the hidden suite errors at collection
  (code-kv ×3, code-fix-fizz ×3, deterministic — temperature 0, so n=3 is one draw). The
  cross-arm code-kv column is the same-instrument control: gemma 3/3 PASS, kat 1/3 PASS
  (two 6/7 near-misses), laguna 1/3 PASS, granite 0/3 collection errors. This is a seat
  conversion-fidelity finding (mxfp8 quantization degrading code emission), not an
  instrument fault and not a loop.
- **auto-coding::laguna `code-kv` (R6):** looped 2/3 on the seat (the third PASSed at 9
  turns), same two tasks as V1. One row shows a malformed tool call — arguments arrived
  embedded in the tool-name field (`pytest_run\n<_key>args…`) — recorded in the debug
  receipt; the row was already a turn-cap outcome.

### R6 loop attribution (controls are committed campaign arms, R5)

Protocol: `portal_wiki/canonical/unit-wfe-loop-attribution-protocol.md`. Controls ran in
two committed-plan campaigns with `--debug-dir` inside each campaign directory
(`tests/wfe/plans/prompt_surface_rebaseline_v2_r6_think.yaml`,
`…_r6_noformat.yaml`; suites `compliance_agentic_loopset.jsonl` — the six looping p6j
tasks verbatim — and `…_loopset_noformat.jsonl`, same tasks with the output-format
sentence removed, completion signal and checker kept):

| Arm (auto-compliance loopset, n=3 ×6 tasks) | Seat served | Result |
|---|---|---|
| Seat baseline rows on the same 6 tasks, lane think-off, format clause | oQ4e-mtp | 11/18 looped |
| **think-on** (card think; everything else identical) | oQ4e-mtp | **0 loops** — 16 PASS / 2 FAIL, 2-turn answers |
| **no-format** (format sentence removed; lane think-off) | oQ4e-mtp | **0 loops** — 18/18 answered in 2 turns (FAIL on the JSON checker, as expected) |
| Seat baseline fallback rows, lane think-off, format clause | Ollama GGUF | 1/17 looped |

Instrument checks that cleared before any attribution: zero-WARN dry run backed by the
positive control; harness note and append verified in the received prompt (P0.4); six
tools; lane sampling; tool arguments logged; zero tool errors inside the loops; seeded
n=3 throughout; rendered-prompt capture done at P0 via trace bodies on the actual request.
The laguna and think arms are `label:`-stamped plan variants
(`@think-on-09904277`, `@card-think-35f4592f`).

**Attribution (auto-compliance and general-deep loops):** the loop requires the
conjunction *oMLX oQ4e-mtp seat × think-off × format-clause* — removing any one factor
eliminates it, and the same checkpoint on the Ollama seat under identical everything-else
passes. This is a **seat/lane-fit result** (the seat's template path interacting with the
lane's forced think-off under an output-format demand), not evidence about Qwen3.8-27B
capability: think-on answers in 2 turns on the same seat. Per the campaign's own rule,
`think: false` stays (it is the committed misconfiguration guard), so the seat number
stands as the number the workspace serves today — with the caveat that a seat whose
routing alias changes (or whose think policy changes) moves this baseline.
General-deep's three loops (res-ollama-ctx r1, res-repo-grounded r1/r2) sit on the same
seat under the same conditions and take the same attribution; no separate control arm was
spent on them.

**Attribution (laguna code-kv):** across four now-measured configurations the row counts
are loop 8 / pass 4 of 12 (seat think-off 2/3 loop; V1 direct 2/3; V1 card-think control
1/3; **seat card-think (temp 1.0, top-p 1.0, top-k 20) 3/3 loop**). Think-on does not fix
it on the seat; the malformed tool-call artifact appears in one loop. Controls ran and
failed to clear either the task or the instrument cleanly: recorded as a **task-lane fit
failure of Laguna-XS-2.1 on code-kv**, stable across engines and think settings — no
single-cause model blame, and the two baseline loops remain the honest seat number.

## P3 — Records, gates, delivery

Delivery records: the plan (`prompt_surface_rebaseline.yaml`, header citing V2), both R6
control plans and suites, the P0 receipts (`p0/positive_control.json`,
`p0/smoke_trace_checks.json`), the generated fitness report
(`docs/WFE_FITNESS_REPORT_wfe_prompt_surface_seat_20261012.md` — it flags
tools-specialist repeats as deterministic: three rows, one draw), the compact JSON receipt
(`docs/WFE_PROMPT_SURFACE_REBASELINE_V2.RECEIPTS.json`), and this closeout. The complete
campaigns stay in the ignored local results tree. `wfe_prompt_surface_seat_20261012`'s
manifest was `cp`-backed up before every append (`manifest.bak-armN.json`).

R7 decisions, from the sources: nothing promoted, removed or reconfigured; the four
production aliases stand; auto-compliance's `think: false` stands; the oMLX mid-arm
manual unload is recorded as an operational event (oMLX server.log 22:45:33Z, 22:47:05Z,
23:01:10Z) without changing any routing decision. The HK public-text scan ran against the
staged index before commit and flagged seven files, which stay local with the rest of the
ignored results tree: the compliance-named arm log
(`wfe_prompt_surface_seat_20261012/p1_auto-compliance.log`, "compliance run output in a
results directory"), the V1 debug copy
(`…/p2/v1_debug_copy/hf.co_unsloth_Qwen3.8-27B-GGUF_Q4_K_M-ctx32k.debug.jsonl`,
operator-derived content), and the no-format control campaign's Qwen debug record plus
four row files (`wfe_prompt_surface_seat_r6_noformat_20261012/debug/hf.co_unsloth…jsonl`,
`rows/39181e9ed04c.json`, `57bdd43b8865.json`, `6e7b8fb9f452.json`, `f3d24c392b93.json` —
operator-derived content: the stripped-format transcripts quote the determination packets
in full). A re-run of the HK check after unstaging is clean; outcomes, attribution and
receipts carry the analysis without the flagged text.

**Gates:** `uv run pytest tests/wfe/tests -q` 217 passed. Unit gate
`uv run pytest tests/unit portal/modules/security/tests -n auto -x --tb=short -q`:
**4,822 passed, 6 skipped** (367s). `bash scripts/ci_local.sh`: **PASS** — Ruff, format,
mypy, and the clean-venv Python 3.12 unit run (4,822 passed, 6 skipped; 387s). The
full-tree `validate_system --skip-pytest` run shows the pre-existing non-blocking HL
compliance data-path finding (served-vs-declared context on oMLX seats, "not blocking")
and one more instance of it after this campaign: the same declared-32768 vs served-262144
warning now also lists `omlx-reasoning` serving the auto-compliance hint — informational;
the seat baseline records served reality per row rather than the declared window.
