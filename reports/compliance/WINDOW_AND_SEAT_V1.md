# WINDOW_AND_SEAT_V1 — the window decides the seat: measurement, then the workspace reads

Task: `coding_task/TASK_COMPLIANCE_WINDOW_AND_SEAT_V1.md` · Base: `7c5f9c3b` (2026-09-17)
Campaign artifacts: `reports/compliance/window_and_seat/`

---

## §P0 — what already measures this

Per the execution rules, every phase reuses an existing harness or names why it
could not. The mapping, recorded before any new work:

| phase | harness (existing) | what it already does | what this campaign adds |
| --- | --- | --- | --- |
| P1.2 | `tools_manifest_{compliance,rag}_mcp.json` + `/api/chat` `prompt_eval_count` diff | the served schema array and an exact token counter | the before/after numbers below |
| P1.3 | `reader.read()` seed/bootstrap (`reader.py`), `bench_long_context_probe.py` for window arithmetic | the nested engine | drop the duplicated text-bearing components |
| P1.4 | `tests/wfe/compliance_preflight.py::first_turn_thread` + `populations` | rebuilds the reader's first-turn thread exactly; per-identity population survey | live `/v1` per-turn counters through the workspace |
| P2 | `llama.cpp/docs/multi-gpu.md` arch list; `tests/wfe/settings_audit.probe_tag` | supported-architecture universe; per-tag preflight | enumeration record + pull/runnability verification |
| P3 | `tests/benchmarks/bench/lifecycle.py` (`_warmup_ollama_model`, `_wait_ollama_idle`, `_check_memory_pressure`) | load, reclaim, memory pressure | per-candidate per-window table |
| P4.1 | `tests/wfe/settings_audit.py::_probe_tools_rendered` / `_probe_think_honored` | **already implements `template_tools_ignored` and `template_think_ignored`** — both probes the task asks for are live in the shared audit (landed `54f96434`/`01d6fc46`) | verify, extend to candidate tags via `probe_tag`; no new probe code needed unless a gap shows |
| P4.2 | router `_stream_with_tool_loop_impl` (`streaming.py:284` logs `Tool loop hop=%d/%d`) | the 20-hop loop itself | a scratch-workspace loop probe per candidate |
| P4.3 | `settings_audit.baked_params` / `ctx_from_tag` / `_template_sha`; `compliance_preflight.applied_versus_requested` | applied-vs-requested audit | per-candidate rows in this report |
| P5 | `config/compliance/reading_prompt.md` versioning (front-matter `prompt_version` + sha, `reader.load_prompt`) | the artifact pattern | the same pattern for the WORKSPACE prompt |
| P6 | `scripts/compliance_acceptance.py` + `config/compliance/cases/cip_007_6.yaml` | live cell runner, guard, artifacts-under-rev | a `workspace` adapter (the `/v1` conversation path); the agent's written judgments; rubric deletion |
| P7 | `reading_transport.chat()` — `answer_budget`/`reasoning_allowance`/`budget_exhausted_in_reasoning` already landed (`ea37da78`) | the allowance split | verification + report; `DEFAULT_EFFORT` stays `False` |
| P9 | `scripts/validation/compliance_acceptance.py` checks **HG** (acceptance currency) and **HH** (seat template identity) | both §P9.1 gates already registered in `validate_system` | run green at campaign end |

### §0.2 arithmetic — measured, and corrected

The task's table priced the schema tax off the whole compliance manifest
(24,813 chars ≈ 8,300 tokens, ~25% of a 32k window). **The workspace path never
serves the whole manifest** — `tool_registry.get_openai_tools()` filters to the
workspace's 23 whitelisted tools (`portal.yaml` → `compliance-reading.tools`),
so the served payload is:

* 23 tool schemas, exactly as served: **10,867 chars**
* measured in tokens on the incumbent (`prompt_eval_count` diff, same
  conversation with and without `tools`): **2,868 tokens per turn** —
  **8.75% of a 32,768 window**, not 25%.
* chars/token on the schema blob: 3.79 (the task's observed thread range
  2.95–3.06 does not apply to JSON schemas; the direction of the correction is
  that the tax is smaller than drafted).

The remaining §0.2 consumers stand: `compliance_context(budget_tokens=60000)`
defaults to a packet up to 60k tokens — 183% of the window in one call — and
that tool is in the list today; `compliance_read` defaults to 20,000 chars
(~21%); uncapped per-turn reads over 20 hops are unbounded. §P1 exists because
of them, and the smaller measured tax makes §P1 *more* tractable, not less
necessary.

### Fleet and environment (start of campaign)

* Ollama `0.33.2`-line serve on localhost:11434; `OLLAMA_NUM_PARALLEL=4`,
  `OLLAMA_MAX_LOADED_MODELS=5`, `OLLAMA_GPU_OVERHEAD=21474836480` (**20 GiB —
  the corrected value; recorded per §P3.3**), `OLLAMA_FLASH_ATTENTION=1`,
  `OLLAMA_KV_CACHE_TYPE=q8_0`, models on `/Volumes/data01/ollama/models`.
* Host: 64 GB unified memory, 21 portal containers up, MLX audio/embeddings and
  the reranker in the stack.
* Incumbent installed: `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` (18.0 GB
  on disk) and the bare tag (18.0 GB). Nemotron Lightning installed **baked at
  8k** (`...:q4_K_M-ctx8k`, 25.5 GB). `Qwen3.6-35B-A3B:UD-Q4_K_XL-ctx32k`
  installed (23.3 GB). `gemma4:26b-a4b-it-q4_K_M` installed **unbaked** (18.0 GB).
  `lfm2.5:8b-ctx8k` already installed (5.2 GB). No Ling-3.0-tiny.
* `HF_TOKEN` present in `.env` (used for candidate pulls).

Commit: `chore(compliance): P0 — what already measures this`
