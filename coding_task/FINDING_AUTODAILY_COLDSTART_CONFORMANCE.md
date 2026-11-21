# Auto-daily cold-start — pre-push conformance (HQ) close-out

Date: 2026-11-21
Lane: `lane/autodaily-coldstart`
Gate: `validate_system` check **HQ** (`scripts/validation/wfe.py:check_serving_conformance`)
refused the push with `5 conformance finding(s) (reasoning_budget_fit,
sampling_mode_fit, sampling_mode_mismatch, tools_unsupported)`.

HQ runs two audits and counts any WARN or FAIL: `settings_audit.run_audit()` over the
served seats, then `settings_audit.audit_tags()` over every installed tag. The five
findings were all in the first. Audit code is identical on `origin/main`
(`git diff HEAD origin/main -- tests/wfe/settings_audit.py` is empty), so the run here
reproduces the refusal rather than approximating it.

Before: `4 FAIL / 1 warn`. After: `0 FAIL / 0 warn`, with the installed-tag audit also
`fail_count 0 / warn_count 0` over 103 tags. No warning was tuned away and no model card
was edited.

## The five findings and their fixes

| Seat | Kind | Cause | Fix |
|---|---|---|---|
| `bench-autodaily-qwen35-9b` | `tools_unsupported` (FAIL) | the seat declared the 14 auto-daily tools over a `supports_tools: false` model | tools withdrawn from the seat (see below) |
| `bench-autodaily-qwen35-9b` | `reasoning_budget_fit` (FAIL) | thinking seat served `predict_limit: 8192`; target is `min(card 81920, 32768, window//2)` = 32768 with no baked window | `predict_limit: 32768` |
| `bench-autodaily-qwen35-9b` | `sampling_mode_fit` (FAIL) | a tool seat served the `thinking_general` arm (presence 1.5) instead of the card's `thinking_precise_coding` | thinking profile and flat block moved to 0.6 / 0.95 / 20 / presence 0.0 |
| `bench-autodaily-qwen35-9b` | `sampling_mode_mismatch` (WARN) | `thinking_general` and `instruct_reasoning` are byte-identical in the card, so the served values also matched a think-off arm | falls out of the same edit: the precise arm matches no instruct mode |
| `bench-autodaily-gemma4-12b` | `tools_unsupported` (FAIL) | same as Qwen | tools withdrawn from the seat |

`gemma4:12b-it-q4_K_M` had no other finding: the `gemma4` card carries neither
`recommended_sampling_modes` nor `recommended_max_output`, so mode-fit, mode-mismatch and
budget-fit are inert for it, and its card temperature 1.0 over the eval lane's 0.7 stays an
INFO (`sampling_card_over_lane`) as for every other `bench-*` seat.

## The tool decision

Both candidates are *unproven*, not *disproven*, for tool calls. Neither was dropped, and
neither was marked `supports_tools: true`:

- **`true` would be a fabrication.** `config/backends.yaml` evidence for the flag is a
  typed tool-call probe, and neither tag has one. The Qwen library tag's stored template
  is `{{ .Prompt }}` with no RENDERER/PARSER (a real red flag, not a family inference), and
  oMLX was unreadable during this run (HTTP 401), so not even its inventory is confirmed.
- **The declaration was also false at runtime.** With `supports_tools: false` the router
  strips the tools array before the request leaves (`portal/platform/inference/router/
  streaming.py:2919-2944`, `non_streaming.py:1187-1192`), so a seat carrying 14 tools over
  such a model never shows them to the model. The seat description's "same production tool
  set as auto-daily" claim described config, not serving.
- **Dropping the candidates would assert a failure that is not established.** Sibling
  builds of both families are probed tool-capable on this host
  (`gemma4:12b-it-qat-ctx8k`, `huihui_ai/qwen3.5-abliterated:9b`, both `supports_tools:
  true`). Nothing here shows the 12B Gemma 4 or the 9B Qwen3.5 loses tools; it shows no
  probe has run on these tags.

So the two bench seats keep their `model_hint`, sampling, budget and cold-start role, and
drop the tool list they cannot exercise. Both descriptions now name the typed tool-call
probe as the gate before the auto-daily real-use arm, as does the plan header
(`tests/wfe/plans/autodaily_coldstart_screen_20261120.yaml`).

The real-use arms are unaffected by this either way: they address `auto-daily` with a
`?model=` override, not the bench workspace, and `auto-daily`'s own tool set is untouched.
The cold-start phase sends `portal_no_tools: true` with no tools array
(`scripts/speed_gate.py:_cold_stream`), so C1 needs no tool declaration to run.

**Known consequence.** With no tools on the seat, `_seat_uses_tools_or_coding` is false and
`sampling_mode_fit` stops being applied to `bench-autodaily-qwen35-9b`. The check returns
the moment the probe passes and the tools list comes back; the sampling was fixed to the
card's precise arm regardless, so the seat already serves what the check would demand.

## When the probe passes — the edit that finishes this

```yaml
# config/backends.yaml: the proven entry only (group that serves it)
- id: qwen3.5:9b-q4_K_M
  supports_tools: true
# config/bench_workspaces.yaml: restore the 14 auto-daily tools on the seat
tools: [web_search, web_fetch, kb_search, kb_list, read_pdf, read_word_document,
        read_excel, create_word_document, create_excel, create_powerpoint,
        execute_python, remember, recall, transcribe_audio]
```

The probe itself is `uv run python -m tests.wfe.settings_audit --tag <tag> --behavioral`
(it FAILs `template_tools_ignored` on prose instead of `tool_calls`) for the Ollama tags,
and a direct `/v1/chat/completions` two-tool call for the oMLX checkpoints. It needs the
tags installed and oMLX reachable — neither is true in this worktree, which is why it was
not run here.

## Verification (this worktree)

```text
$ uv run python -m tests.wfe.settings_audit           # after
[info] bench-autodaily-qwen35-9b: omlx_settings_no_entry ...
[info] bench-autodaily-gemma4-12b: sampling_card_over_lane ...
4 FAIL / 1 warn                                       # before
0 FAIL / 0 warn                                       # after

$ settings_audit.audit_tags(installed_tags(backends))  # the other half of HQ
{'checked_tags': 103, 'fail_count': 0, 'warn_count': 0}

$ uv run python -m portal.platform.inference.cli config validate
config OK

bench-autodaily-qwen35-9b -> ('omlx-general', 'omlx', 'Qwen3.5-9B-oQ4e-mtp')
bench-autodaily-gemma4-12b -> ('omlx-general', 'omlx', 'gemma-4-12B-it-oQ4e-mtp')
```

## Still unproven

- Tool calls on either candidate, on either engine. Unchanged by this finding.
- That `predict_limit: 32768` is served inside a real window: the base tags bake no
  `num_ctx` and are not installed here, so Ollama's own default window serves them until
  the orchestrator repoints to the `-ctx16k` tags. At that repoint the target drops to
  8192 (half of 16k) and 32768 is still audit-clean — only under-serving fails — but a
  32k output cap on a 16k window is incoherent, so it should come down in the same edit.
- That the oMLX checkpoints load at all on this host's oMLX build.
