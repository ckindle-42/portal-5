# UAT 20260627 known issues — operator awareness for bench_tps/bench_sec/persona_matrix

Run reference: `tests/UAT_RUN_LOG.md` entry 20260627T0112Z
Status at this writing: **147P / 3W / 42F / 4S / 1M** — routing 100% correct.

## The regression story (resolved in Phase 2 of TASK_PREFLIGHT_NEXT_3_HEAVY_SUITES_V2)

**Before the refactor, supergemma4 ran fine on bench_security.** That's
documented in operator memory and was the correct observation. Here's
what happened:

1. `backends.yaml` always declared `supergemma4-26b-uncensored:Q4_K_M`
   with `supports_tools: true` — based on the aspirational workspace
   description ("attack plan with execute_bash/execute_python for live
   PoC").
2. Pre-refactor: `validation.registry` was None because lifespan
   startup never injected it. `_model_supports_tools()` ALWAYS
   returned False regardless of the metadata flag. **Tools were
   never injected into any model.**
3. bench_security worked because its chain driver dispatches tools
   directly from Python via `_lab_mcp_call` — the model generates plan
   text, driver parses and dispatches. No model-side tool support
   needed.
4. Commit `7fee599` correctly fixed the registry injection. Now
   `_model_supports_tools()` returns True for supergemma4 — and
   tools ARE injected.
5. supergemma4 then sees tool definitions and tries to dispatch
   `execute_bash` itself — but empirically enters a reasoning loop
   without producing a valid tool call. UAT WS-PE03 killed at 1353s.

**The fix in Phase 2 sets `supports_tools: false` for
supergemma4-26b-uncensored.** This restores the pre-refactor
behavior for this specific model (no tools injected to it; driver
dispatches; chain works) while preserving the `7fee599` registry
fix for every other tool-supporting model.

## Blocking — addressed in this task

- **supergemma4 reasoning loop on `auto-purpleteam-exec`** — Phase 2
  flips `supports_tools: false`. Pre-refactor behavior restored.
- **Slow models** (phi4-reasoning, tongyi-deepresearch,
  qwen3.5-abliterated) — Phase 4 per-workspace timeout caps so they
  complete within budget.
- **Tongyi-deepresearch "wrong workspace"** (3 UAT tests) — Phase 3
  diagnosis: only 1 workspace has this hint, so it's classifier
  accuracy or test expectation drift, not a data issue. Documented
  here for operator triage; routing fix deferred to a separate task.

## Non-blocking — surface during runs

### Content-quality (model output didn't match assertions)

These don't affect bench_tps (raw t/s) and only edge-case bench_sec /
persona_matrix scenarios. Watch the run output; if a known FAIL
persists, it confirms a model issue rather than infrastructure.

| Workspace | Model | UAT failure shape |
|---|---|---|
| auto-coding | qwen3-coder | P-D02/03/04/22: code-review keywords missing |
| auto-cad | qwen3-coder | WS-CAD-03 STL conversion: "does not exist" — investigate cad MCP path mapping |
| auto-pentest | gemma-4-abliterated | WS-09: SQL injection keywords absent |
| auto-phi4 | phi4-reasoning:plus | WS-PHI4-02: physics keywords absent (output length OK) |
| auto-research | tongyi-deepresearch | P-R05 evidence labels; P-R07 prompt injection |
| auto-security | vulnllm-r-7b | P-S08 REDACTED placeholder missing |
| auto-security-uncensored | baronllm-abliterated | WS-28 SSRF keywords absent (16s — not a tool issue) |
| auto-daily | gemma4 | WS-DD-09 URL absent; WS-DD-14 5050 sum absent |
| auto-music | lfm2.5 | M-01 Whisper transcript content mismatch |
| transcriptanalyst | granite4.1 | TR-01 docx artifact path missing |

### Tool-dispatch open defect — `tool_choice:auto`

UAT discovered models with tools available sometimes hallucinate the
answer instead of dispatching the tool (T-02, TV-01/04/05/06,
DD-TV-01). Models affected: qwen3-coder, magistral-small, gemma4.

**For the next 3 runs:**
- bench_tps: doesn't use tools — not affected
- bench_security: chains use driver-managed dispatch (not model
  decision) — not affected
- persona_matrix: doesn't test tool dispatch — not affected

This is a separate defect (`tool_choice:required` implementation
needed) that primarily affects UAT. Documented for full-stack
visibility.

### Environment / dispatcher

- `A-05 / A-06` (Telegram / Slack bot): SKIP — no bot tokens on dev box
- `T-08 / WS-11` (ComfyUI): SKIP — verify mcp_comfyui health before
  bench_security runs that exercise it
- `A-07` (Grafana): MANUAL visual check

## How to use this doc during the upcoming runs

1. **bench_tps:** If a workspace shows abnormal t/s (e.g., budget
   timeouts on phi4/tongyi), check Phase 4's PER_WORKSPACE_TIMEOUT
   values. They should complete; if not, raise the cap.

2. **bench_security:** Phase 2's supergemma4 fix should make
   `auto-purpleteam-exec` exec chains complete in pre-refactor
   timeframes. If they hang, investigate whether the driver's text
   parser still recognizes the supergemma4 output format (which is
   now untouched by the pipeline's tool injection path).

3. **persona_matrix:** Routing 100% correct in UAT. Watch for the
   tongyi-deepresearch finding (Phase 3) — if any persona shows
   unexpected routing labels, it's likely the classifier-accuracy
   issue and not a regression.
