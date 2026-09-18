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

---

## §P1 — the window is spendable (code record)

* **P1.1 caps** (`portal/modules/compliance/tools/compliance_mcp.py`): `compliance_context`
  now defaults to `mode="index"` — the whole neighbourhood as ids/sides/paths/pages,
  **no text**, standard-level fixed body collapsed to stated counts (measured: 210 of 233
  rows for Part 2.2 were the standard's own Section 4/6/implementation-plan body,
  identical for every requirement). `mode="packet"` is the old assembly, explicit.
  Parent-R2 index: 20,552 chars ≈ 5.4k tokens ≈ 16% of a 32k window — under the
  one-fifth ceiling at the worst case. `compliance_read` default `max_chars`
  20,000 → **6,000** (the nested engine's bound), truncation stated.
  `compliance_requirement` (+`nerc_cip_requirement` via it) gets a **per-call** 6,000-char
  text ceiling shared across matched parts, clips stated, budget-exhaustion named.
  `compliance_links` capped at 50 edges; `compliance_notes` per-note 4,000/limit 20;
  `compliance_answers` per-answer 2,000; `compliance_conflicts` spans 1,000 each;
  `compliance_sources(include_sections=true)` sections 4,000 each. `compliance_ask`'s
  declared default drops 60,000→12,000 to match what `reader.read()` actually enforces
  (a declared policy the code ignores is worse than no policy). `compliance_ask` itself is
  NOT text-capped — its receipt is the point of the tool, scripts consume it whole, and
  §P8.3 removes it from the conversation list entirely; a clipped receipt would corrupt
  the acceptance record it exists to keep.
* **P1.2 schema tax — measured, and corrected against §0.2.** The task priced the tax
  off the whole 43-tool manifest (24,813 chars ≈ 8,300 tokens). The workspace path
  serves only its 23 whitelisted schemas: **10,867 chars = 2,868 tokens exactly**
  (measured by `prompt_eval_count` diff on the incumbent, same conversation ± tools),
  ≈ 8.75% of a 32k window. After one-line descriptions carrying the ceilings:
  9,531 chars = **2,634 tokens** (−234). The remaining weight is parameter schemas,
  not prose; the bigger cut (dropping `kb_search`, `kb_list`, `compliance_trace`)
  waits for §P6's own transcripts, per the task, and lands with §P8's list edit.
* **P1.3 seed duplication — killed.** `reader.read()`'s seed now renders NO
  text-bearing regulatory component; requirement/measures/technical_basis ship once,
  through the recorded bootstrap, inside the same cacheable prefix. The seed's
  omission disclosure drops those three (they arrive two messages later; a "you have
  not seen this" that is false on the next line is a lie). Measured on the live store:
  seed Part 2.2 3,853→2,520 chars; parent R2 6,906→2,771 chars. `first_turn_thread`
  (the preflight's window probe) mirrors the new construction exactly.
* **P1.4 — see §P6's tables; the number that sets the window is there.**

### rung-0 findings fixed on the way to a live measurement

1. **The deployed router did not contain the workspace.** The pipeline image was built
   2026-09-12; `compliance-reading` is absent from its baked `portal.yaml` — `WORKSPACES`
   had no entry, so `model_hint` was empty, hint enforcement was vacuous, and the
   request fell to the first healthy general backend. The product's workspace has been
   **not deployed** on `/v1` since Sep 12; nothing noticed because the last campaign ran
   through the MCP (`compliance_ask`), not the workspace. Fix: rebuild `portal-pipeline`
   with the current config; verify `WORKSPACES['compliance-reading']` in-container
   (hint, 32k, 23 tools).
2. **The seat's tag was not registered where the workspace routes.**
   `compliance-reading` routes to the `general` group; the incumbent
   `…Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` was registered only under `coding` and `reasoning`.
   Even with the workspace deployed, hint enforcement would skip every general backend
   and the last-candidate-accepts-any rule would serve *any* model — observed live
   pre-fix: Nemotron Lightning **baked at 8k** and gemma-4-26b via oMLX answering a
   workspace that declares 32k. Fix: registered the tag in `ollama-general`'s models
   (supports_tools: true), `docker compose build portal-pipeline`, live-verified:
   `x-portal-route: compliance-reading;ollama-general;…Qwen3.8-27B-GGUF:Q4_K_M-ctx32k`.
   Both are rung 0 (a setting was not applied), both found by the smoke-first rule
   before any campaign cell ran.
3. **Router token counters are per-worker.** `metrics._REGISTRY` is a plain
   `CollectorRegistry` per uvicorn worker; with 4 workers, `/metrics` shows only the
   scraping worker's counters, so `portal_input_tokens_total` deltas undercount by the
   workers that did not serve the scrape. Not fixed here (deployment-wide concern);
   the campaign's per-turn numbers instead read the **usage chunks Ollama emits per
   hop** (already forwarded to the client by the tool loop — empty-choices chunks pass
   through), whose final `prompt_tokens` per turn is the server-tokenized high-water
   mark. Counters stay in the record as a cross-check lower bound.

---

## §P2 — the slate

### P2.0 the method — enumerate architectures, then find models

The runtime's supported-architecture list is the universe of what can run here.
From `llama.cpp/docs/multi-gpu.md`'s published set — MoE/hybrid: Grok, MPT, OLMoE,
DeepSeek2, GLM-DSA, **Nemotron-H**, **Nemotron-H-MoE**, **Granite-Hybrid**, **LFM2-MoE**,
Minimax-M2, Mistral4, **Kimi-Linear**, Jamba, **Falcon-H1**; SSM: Mamba, Mamba2; other:
PLAMO2, MiniCPM3, Gemma-3n, OLMo2, BitNet — intersected with the four legs
(hybrid/recurrent attention · low active parameters · tool support · ≤ ~25 GB at Q4):

* **Nemotron-H-MoE** → the installed Nemotron 3.5 Lightning 30B-A3B (mis-baked 8k).
* **Granite-Hybrid** → IBM Granite 4 `small-h`/`tiny-h`, **official on Ollama**
  (`granitehybrid` arch verified in the pulled tag).
* **LFM2-MoE** → LFM2-24B-A2B, LFM2.5-8B-A1B — **killed live, see P2.2**.
* **Kimi-Linear** (the KDA origin) → priced out of the band: 48B total at Q4 ≈ 27–30 GB.
* **Falcon-H1** → dense hybrids only (0.5/1.5/3/7/34B — no MoE/low-active variant in
  the band; a 34B dense hybrid reads every weight per token on this box).
* **Ling-3.0-tiny** (KDA 3:1 + MLA, 1.3B active) — found by naming, kept by the
  architecture leg; runnability is the open question (P2.2).

Four of these (Nemotron-H-MoE's own model aside) would not have been found by naming
models: the LFM2 MoE pair, Granite 4 `-h`, and the Kimi-Linear/Falcon-H1 price-outs all
came from the arch list inward.

### P2.1 the slate

| tag | attention | active | state at campaign start |
| --- | --- | --- | --- |
| `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` (incumbent) | GDN 3:1, dense | 27B | in fleet, 32k baked |
| `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:q4_K_M-ctx8k` | Mamba-2 + MoE | 3B | in fleet, **baked 8k — the recorded error, fixed in §P8** |
| `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k` | GDN 3:1 + MoE | 3B | in fleet, 32k |
| `gemma4:26b-a4b-it-q4_K_M` | sliding+global, unified KV, cross-layer sharing | 4B | in fleet, unbaked |
| `granite4:tiny-h` | granitehybrid (Mamba-2 + attention MoE) | ~1B of 6.9B | **pulled this campaign** — official, Q4_K_M, tools capability, 1M native ctx |
| `granite4:small-h` | granitehybrid | ~9B of 32B | **pulled this campaign** — official, Q4_K_M |
| `Ling-3.0-tiny` | KDA 3:1 + MLA | 1.3B of 7.9B | arch support question — P2.2 |

### P2.2 the runnability blockers — verified, not worried about

* **LFM2 family: the §P2.2 cache kill is WITHDRAWN — see §P3.1.** The
  two-turn `prompt_eval_count` comparison that killed the family measured a
  metric that reads the full prompt on cache hits. With the duration
  instrument, `lfm2.5:8b`'s turn-2 prefill is 0.08 s against 2.56 s — the
  cache holds, and llama.cpp
  [#16491](https://github.com/ggml-org/llama.cpp/issues/16491) does not
  reproduce on Ollama 0.34.0 under sequential or lightly-interleaved traffic.
  LFM2-24B-A2B and LFM2.5-8B-A1B revert to the candidate pool; the 24B was
  never pulled and its speed is unmeasured. The family's other recorded
  blocker — chat template dropping tools (upstream PR #23826) — was never
  reached and remains the thing `settings_audit`'s `template_tools_ignored`
  probe exists to catch on any future LFM2 trial.
* **Ling-3.0-tiny: arch support.** llama.cpp merged `bailingmoe3` (PR #26608,
  2026-08-17); Ollama's own support is not in a released version, and community Ollama
  pages (`maternion/ling-3.0-tiny`) still need the LOCAL runner to know the arch.
  Installed runner: **Ollama 0.34.0**. The pull/load attempt and its outcome are
  recorded in the §P3 table — if it does not load, this is
  `honest-BLOCKED: bailingmoe3 not in installed Ollama`, a deliberate build decision
  (chat stays Ollama, Rule 8), not a backend swap trigger. MLX stays for
  audio/embeddings/reranking.
* **Granite 4 `-h`:** reasoning not supported at release (bears on §P7's rung-4 lever);
  `granite4:tiny-h` shows capabilities `completion, tools` in `/api/show` — the
  §P4 probes decide, not the card.
* **Contrary datapoint (Ling on Vulkan slow prefill):** if the arch loads here, the
  §P3 numbers are the Apple-Metal answer; if not, it stays open on the record.

### P2.3 tool support by preflight, not registry

`settings_audit.probe_tag` (the `template_tools_ignored` probe) runs per candidate in
§P4 — including the new pulls. The registry's `supports_tools` both-ways record for
`qwen3.6:35b-a3b` is exactly why the probe, not the field, is the producer.

### P2.4 ruled out, with the reason

* `Ling-3.0-flash` — architecturally the ideal shape (KDA 5:1 + gated MLA, 5.1B active),
  ~70 GB at Q4: the box cannot hold it co-resident with 21 containers. First candidate
  to revisit if hardware changes.
* `granite4.1:30b` — already excluded (36.4 GB resident driving 50.6 GB swap). Not
  re-tested. The `-h` variants are a different size family and were never tested here.
* MiniMax-M2, DeepSeek-V4-Flash, GLM-5.3-Flash, Qwen3.8-Flash-Next, dots3 —
  architecturally sound, all far past the ~25 GB footprint gate. The band is recorded;
  the next pass does not re-walk it.

### P2.5 families enumerated but not yet priced

* **Kimi-Linear** — the KDA origin; 48B total ≈ 27–30 GB at Q4 → past the gate. Origin
  tech already priced via Ling-3.0-tiny.
* **Falcon-H1 / H1R** — parallel attention+Mamba2 heads in one mixer; six sizes
  0.5–34B, all **dense** (no low-active MoE variant) → a 34B dense hybrid reads every
  weight per token on this box; the ≤7B ones give nothing the incumbents don't. No
  variant in the band.
* **Nemotron-H (non-MoE, 8B)** — the family replaces ~92% of attention with Mamba2;
  dense-active 8B → decode reads 8B/token: slower than every A3B candidate, faster
  than the 27B dense incumbent, and the MoE Lightning in the fleet already occupies
  the family's good seat. Not priced further.
* **Jamba Mini** — 52B total/12B active ≈ 26 GB+ at Q4 → past the gate.
* **Bamba (9B Mamba2)** — fits the size band but has no official Ollama distribution;
  packaging, not architecture, is the blocker. Recorded for the next pass.
* **PLAMO2 / MiniCPM3/5** — MiniCPM5-1B already in fleet (0.7 GB) as a toy lane;
  neither family has a tool-capable variant in the band worth a slot against the above.

Null results stated: none of P2.5 produced an in-band candidate that the slate missed.

Commit: `docs(compliance): P2 — the slate, its runnability gate, and what is ruled out`

---

## §P3 — what the box affords, per candidate (stack up: 21 containers, MLX audio/embeddings, reranker)

Sweep harness: `scripts/window_seat_sweep.py` (new; reuses `bench/lifecycle.py`'s
unload/idle discipline — what it could not reuse: lifecycle benches short-prompt TPS,
this needs prefill at the ~20k high-water, decode at length, two-turn cache ratio,
free pages and swap with each model loaded). All candidates measured under identical
conditions, sequentially, nothing else running. Raw rows:
`reports/compliance/window_and_seat/p3_measurements.json`.

| candidate @ window | decode tok/s | prefill tok/s (20.5k tok) | cold load | swap grew |
| --- | --- | --- | --- | --- |
| incumbent Qwen3.8-27B dense @32k | 12.0 | 94.4 | 16.6 s | no |
| Nemotron Lightning 30B-A3B @32k | 51.9 | 643.3 | 21.9 s | no |
| Qwen3.6-35B-A3B @48k | 44.3 | 589.6 | 11.3 s | no |
| Qwen3.6-35B-A3B @32k | 44.0 | 591.4 | 10.5 s | no |
| gemma4 26B-A4B @32k | 55.8 | 493.9 | 9.1 s | no |
| granite4:tiny-h (7B/1B) @32k | **78.8** | **1278.1** | 3.3 s | no |
| granite4:small-h (32B/9B) @32k | 22.2 | 275.2 | 13.9 s | no |
| Ling-3.0-tiny (7.9B/1.3B) | **104.5** | 1040.1 | 3.7 s | no |

* The §0.4 prediction holds: active parameters decide decode. Every A3B/low-active
  candidate beats the 27B dense incumbent by 4–9×; the incumbent's prefill (94 tok/s)
  means turn one of `parent` pays ~4 minutes in prefill alone at the high water.
* **No swap growth on any candidate.** The `granite4.1:30b` disqualifier (50.6 GB
  swap) does not recur anywhere on this slate.
* **Instrument caveats, recorded**: `/api/ps` `size` does not move with KV allocation
  on Ollama 0.34 (the "resident at window N minus window 1" column reads 0.0 for
  every architecture — the cache-cost-of-the-window number needs an allocation-level
  instrument; not solvable from the public API this round). macOS `Pages free` is a
  weak pressure signal (the box shows ~60–100 "free" MB with an 18 GB model loaded
  and no swap); swap-growth is the hard disqualifier and it never fired.
* **Cache-cost caveat, superseded by a bigger finding** — see §P3.1: nothing holds
  prompt cache on this deployment, so the architecture-specific KV-reuse advantage
  is currently unrealised for every candidate equally.
* Fleet co-residency (§P3.3): the sweep ran models one-at-a-time on an otherwise
  idle Ollama. `granite4:tiny-h` is the only candidate that meaningfully shrinks the
  seat's footprint (≈4.4 GB at Q4_K_M; 16.5 GB free pages at load vs ~0 for the
  18–25 GB candidates) — co-resident with the audio/embeddings/reranker lanes
  without eviction pressure. `OLLAMA_GPU_OVERHEAD` = 20 GiB (the corrected value);
  at 20 GiB it binds nothing on this slate (largest candidate 25.5 GB < overhead +
  headroom), recorded so the next footprint gate pass does not re-discover it.

### §P3.1 the cross-turn prompt cache — answered three times, correctly once

This question was closed wrongly twice before it was closed rightly, and the
history stays on the record because the wrong instruments are still in the repo's
muscle memory.

1. **Wrong (over-inclusive kill).** The §P2.2 two-turn test compared
   `prompt_eval_count` between turns and concluded LFM2's cache "cleared every
   turn" — the family was disqualified on it. **`prompt_eval_count` reports the
   TOTAL prompt length, not tokens evaluated**; on a cache hit it still reads the
   full count. The number cannot answer the cache question, and the LFM2 kill
   built on it was void.
2. **Wrong (over-broad retraction).** Reading the same metric on more models —
   including a pure-attention control (`hermes3:8b`) and `/api/generate` with
   byte-identical prompts — produced "cache holds for nobody; slot rotation
   swallows it". Also an artifact of the same metric, enshrined briefly in this
   report and withdrawn.
3. **Right (the duration field).** `prompt_eval_duration` is the signal: it
   collapses ~50× on a cache hit. Measured turn-over-turn on the restarted
   daemon, sequential traffic:

   | model | turn-1 prefill | turn-2 prefill | |
   | --- | --- | --- | --- |
   | hermes3:8b (pure attention, control) | 10.49 s | **0.11 s** | holds |
   | incumbent Qwen3.8-27B GDN @32k | 41.23 s | **1.29 s** | holds |
   | `lfm2.5:8b` (lfm2moe) | 2.56 s | **0.08 s** | holds |
   | Ling-3.0-tiny (bailingmoe3) | 2.64 s | **0.13 s** | holds |
   | granite4:tiny-h (granitehybrid) | 3.45 s | **0.09 s** | holds |

   And under interleaved traffic (a second, unrelated conversation between the
   two turns — `NUM_PARALLEL=4` gives it its own slot): the first
   conversation's cache **survived** (turn-2 prefill 0.09 s). The upstream
   random-miss symptom ([ollama#5303](https://github.com/ollama/ollama/issues/5303))
   does not reproduce at this concurrency on Ollama 0.34.0.

**Verdict**: cross-turn prompt caching works on this deployment for every
architecture tested, hybrid and pure. §P6.4's "later turns faster than the
first" is a live expectation, not a hope. **The LFM2 cache kill is formally
withdrawn** — llama.cpp [#16491](https://github.com/ollama/ollama/issues/16491)
does not reproduce on Ollama 0.34.0 under sequential or lightly-interleaved
traffic; LFM2-24B-A2B reverts to the candidate pool with its speed unmeasured
(the 24B was never pulled). The cache-cost-of-the-window remains unmeasured
(`/api/ps` size does not track KV allocation); with caching working, it matters
less than the §P3 prefill/decode table for the seat decision.

Process note, owed to the operator who asked the right question: the project's
known failure mode — harnesses and templates quietly mis-configured, producing
confident bad numbers — is exactly what happened here, twice, in one campaign.
The rule that held is the one the task already states: **a measurement instrument
is validated by a control before its verdicts are believed.** The pure-attention
control and the duration counterweight were added only after the first two
readings; they should have been in the harness from §P2.2.

---

## §P4 — the loop, the settings actually applied, and the templates

### P4.1 the probes were already in the shared audit

`settings_audit._behavioral_probes` already carried `template_tools_ignored`
(`_probe_tools_rendered`) and `template_think_ignored` (`_probe_think_honored`) —
landed in `54f96434`/`01d6fc46` between the task draft and this campaign. Nothing
new was written; `probe_tag` ran per candidate instead.

### P4.1-bis probe verdicts, and the template investigation

Raw: `reports/compliance/window_and_seat/p4_probes.json`.

| candidate | tools rendered | think | template sha | notes |
| --- | --- | --- | --- | --- |
| Nemotron Lightning @32k | ✓ | honored | `c1d545bca1bb` | clean, 0 fails |
| Qwen3.6-35B-A3B @48k | ✓ | honored | `55d4931433fe` | clean, 0 fails |
| gemma4 26B-A4B @32k | ✓ | honored | `b507b9c2f6ca` | clean, 0 fails |
| granite4:tiny-h @32k | ✓ | refused-400 | `0f6ec9740c76` | system-probe FAIL |
| granite4:small-h @32k | ✓ | refused-400 | `0f6ec9740c76` | |
| Ling-3.0-tiny | ✓ | honored | `eb6226c94ae3` | system-probe FAIL |

* **The granite twins' `think` refusal is the documented state, not a defect**: HTTP
  400 "does not support thinking" — IBM shipped Granite 4.0 hybrid without reasoning.
  On /v1 the workspace pins `think:false`, which injects `reasoning_effort=none` —
  the suppressing direction, verified safe on non-thinking models — so the downgrade
  path never fires in the product.
* **The system-probe FAILs on tiny-h and Ling were investigated as suspected
  template limitations, and the template is exonerated.** Reproduced at
  `num_predict` 20 AND 300, `think:false` honored, zero thinking chars, clean
  `stop`: tiny-h answers `GREEN.`, Ling `Green.` — both render the system prompt
  and both decline to obey an instruction that contradicts what they know (say
  BLUE about grass). Same template (`0f6ec9740c76`) with small-h (9B active) obeys.
  So this is **small-active-model instruction-following**, a genuine seat signal
  for a workspace whose control surface is a large system prompt — a model
  property, not a template or budget artifact. The probe's `template_system_ignored`
  name overstates what it measured; noted as a probe-naming debt, not fixed here.
* **One real template finding**: Ling's template defaults `thinking_option` to ON
  when the flag is absent (Bailing V3 template, read in `/api/show`). The workspace
  pins `think:false`, so the product is safe; any client that omits the flag gets
  thinking by default and a starved `num_predict`.
* **Tag-case finding**: `ollama create` normalised the Nemotron window tag to
  `…:Q4_K_M-ctx32k` (uppercase Q) and refuses the lowercase spelling of the same
  name while the 8k sibling (`…q4_K_M-ctx8k`) exists in lowercase. The uppercase
  tag is the canonical 32k Nemotron tag going forward; the legacy lowercase 8k tag
  is the §P8.2 deletion.

Commit: `feat(compliance): P4 — tool-loop and applied-settings probes in the shared audit`
