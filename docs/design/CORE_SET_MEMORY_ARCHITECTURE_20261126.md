# Core-set memory architecture — design review (2026-11-26)

**Status:** design only; no seat, config, engine, or lifecycle change is approved by this document.  
**Decision:** **adopt the working-set idea, not a new gateway and not an unconditional “never evict / never reject” rule.** Start with one hunt workflow on one shared Inkling model. Use oMLX's native multi-model scheduler, retain the Pipeline as the cross-engine and capability-aware coordinator, and make one large-specialist working set the initial policy. Consolidate other seats only after outcome-graded live A/Bs under `docs/MODEL_SEAT_PROCESS.md`.

## 0. Evidence boundary and corrections to the draft

This review read the checked-in router, native Ollama transport, load guard, workspace/backend config, model-seat process, fleet closeout, known limitations, QAT notes in `coding_task/RESUME_20261125.md`, and the uncommitted working-set analysis on `lane/working-set-coresidency`. It did not load/unload a model, change the live stack, or execute a new model benchmark. Numbers labelled **incident**, **historical**, or **upstream** are not new measurements on this host.

Four corrections materially change the design:

1. **The current guard is not a 0.1-second rejector.** `portal/platform/inference/load_guard.py` defaults `LOAD_GUARD_WAIT_S` to 120 seconds, waits for in-flight work and model transitions, evicts eligible idle residents, and has batch overrides. The incident still proves that a bounded wall-clock wait and fallback are the wrong terminal semantics for useful work; it does not justify replacing the guard wholesale.
2. **Current oMLX already has the central scheduler features.** Upstream documents multi-model LRU eviction, pinning, per-model TTL, continuous batching, process-memory enforcement, and per-model profiles. The checked-in limitation saying that one oMLX model wipes another's cache is an installed-version/host measurement, not a reason to build a third scheduler before checking the current engine contract.
3. **Per-request context is not a free tag deletion on Ollama.** Portal deliberately drops load-time options in `ollama_native.py`. Current Ollama queues loads, but its scheduler reloads a runner when load-time options such as `num_ctx` differ. Forwarding different contexts for each role on one tag can therefore create reload thrash rather than remove it.
4. **The model guard is not the whole host.** EmbeddingGemma, speech/transcription, VL reranking, media generation, Docker, and ordinary host pressure share unified memory but are not all Pipeline model residents. A core set fixes the 2026-11-26 model-pair failure; it cannot by itself prevent a media job or a test-worker wave from shrinking the dynamic ceiling.

The uncommitted working-set analysis independently reaches the important hunt-specific conclusion: routing `security-reviewer`, `hunt-reasoning`, and `auto-council` to one resident model makes the incremental weight cost of the latter two zero. Its proposed pair lease is useful only while they remain different models; it should not become permanent machinery after a successful consolidation.

## 1. Verdict on the five-part concept

| Draft element | Verdict | Required change |
|---|---|---|
| One strong tool-calling core + tiny router + embedder | **Adopt, initially for security/hunt only.** | “Core” is a routing and residency policy, not proof that one model is best at every task. Pin only after a full working-set fit is measured. |
| One specialist swap slot | **Adopt as one *large* specialist, not one model of any size.** | Small independent judges/helpers may coexist when the measured budget permits. Do not evict a useful small model merely to satisfy a one-slot metaphor. |
| Queue, don't reject | **Adopt for transient contention only.** | Queue on state changes and client cancellation; retain explicit `never_fit`, invalid-request, engine-down, and overload/backpressure errors. No total wall-clock kill. Core traffic must not head-of-line-block behind a specialist swap. |
| One tag per weights; context per request | **Defer and narrow.** | Use one resident context policy per Ollama runner. A single tag with alternating `num_ctx` reloads. oMLX aliases/profiles already avoid duplicate weights; GGUF `-ctxNk` tags share blobs but represent different runner configurations. |
| Data decides merges; no model removals | **Adopt unchanged.** | Each merge is a named seat decision with a live incumbent control, outcome receipts, independent judges, and a reversible 2–3 day real-use trial. “Unproven” keeps the incumbent. |

### What is missing from the concept

- **A capability contract, not just a memory contract.** Tool calling, exact job-id preservation, JSON/schema adherence, modality, refusal posture, context, and structured-output behavior are seat properties. A same-family GGUF fallback is not automatically an equivalent fallback.
- **A distinction between static impossibility and temporary busyness.** Queueing cannot make `core + specialist + KV + prefill > budget` fit. That request needs a deterministic `never_fit` at plan/admission time, not a hung HTTP turn.
- **KV, prefill, and concurrency in the budget.** Weights-only arithmetic is an upper bound. Ollama parallel slots multiply context allocation; oMLX active sequences and prefill also consume memory.
- **Interactive/job QoS on the shared core.** oMLX continuous batching removes weight swaps, not GPU contention. Eight hunt calls can delay the analyst. Start with bounded hunt concurrency and measure interactive TTFT while hunts run.
- **Host jobs outside the two chat engines.** Media and other host MLX jobs need admission into the same eventual host-memory plan; otherwise the “whole problem” remains unsolved.
- **An emergency recovery path.** “Never evict the core” must mean *never during ordinary specialist replacement*. A fixed core must not turn external host pressure into another watchdog reset. Operator/host-safety recovery may still unload it.
- **Prefix-cache realism.** Different role prompts and tool schemas do not share a prefix merely because they share weights. Consolidation saves weights and swaps; it does not guarantee prefix hits.

## 2. Adopt versus build

### Steelman: build the policy in the Pipeline

The Pipeline is the only layer that sees all of the following together: workspace and variant identity, engine aliases, requested tools, UI versus API audience, chain/council semantics, job leases, Ollama and oMLX residency, and user-visible fallback receipts. It already has a host-wide cold-load lock, cross-engine idle eviction, per-model in-flight tracking, and memory metrics. Keeping policy there avoids another control plane and lets a hunt fail as a retryable job rather than as plausible prose from an incapable fallback.

The cost is real: `load_guard.py` is already a large, multi-process coordinator with polling and race-prone settle behavior. Adding role policy, fair queues, and native oMLX lifecycle calls without deleting duplicate mechanisms would make the system worse. **Build only the thin cross-engine residue**: working-set declarations, condition/event-driven waiting, capability checks, and receipts. Native engine scheduling should remain native.

### Steelman: adopt llama-swap or another gateway

[llama-swap](https://github.com/mostlygeek/llama-swap) is credible prior art, not a toy. Its [group/matrix/capacity routers](https://llama-swap.ai/docs/guides/routing/groups-and-matrix) express persistent models, mutually exclusive large models, allowed co-resident sets, and manually declared resource pools. It serializes swaps, waits for model readiness, supports TTL, and its health timeout resets when loading progress changes—good stall-based behavior. Its [queue documentation](https://llama-swap.ai/docs/guides/routing/capacity-and-queues) also shows why it is not a complete answer: per-model/global concurrency limits reject with 429 rather than queue, and capacity requirements are operator-declared rather than automatically measured.

A gateway would be attractive if Portal were starting from independent `llama-server` processes. It could own the core persistent group and one large swap group in one place. But putting it **in front of the existing engines as remote peers** does not give it authority over their internal residents. Replacing them with one process per model would sacrifice oMLX's native continuous batching, tiered prefix cache, MLX-specific acceleration, admin model profiles, and existing engine contract. It would add a third scheduler and a second source of memory truth without understanding Portal's tool/fallback semantics.

LM Studio's JIT/TTL and Ollama's scheduler validate the product pattern, but neither coordinates both existing engines. LiteLLM-style routers route providers; they do not solve unified-memory residency on this host.

### Recommendation: adopt oMLX's scheduler; keep Ollama's; coordinate, don't replace

Current [oMLX](https://github.com/jundot/omlx) already documents the required native mechanisms: multi-model LRU, pinning, per-model TTL, continuous batching, process-memory enforcement, and per-model profiles. Its [Admin API](https://github.com/jundot/omlx/blob/main/docs/admin-api.md) exposes model settings/load state and an activity feed with waiting/prefilling/generating requests. Use those surfaces instead of reproducing them.

[oMLX 0.8.4](https://github.com/jundot/omlx/releases/tag/v0.8.4), published 2026-11-26, is particularly relevant:

- Inkling 2 Mini routed-expert SSD offload is reported to reduce a 24 GB Mac footprint from **17.0 GB to 10.2 GB**;
- Inkling Lightning MTP now works with concurrent requests, and the release reports **220.3 tok/s aggregate for two requests on M5 Ultra**—useful evidence of direction, **not** an M4 Pro result;
- model load during another model's teardown now waits instead of failing;
- per-request cache-store controls allow one-shot calls to avoid polluting reusable prefixes.

The installed engine must pass Portal's existing engine-contract check before any of these features is used. The release is same-day upstream evidence, not proof that this host's current version/configuration has them.

[Ollama's scheduler](https://docs.ollama.com/faq#how-does-ollama-handle-concurrent-requests) already queues model loads FIFO, evicts idle models, defaults `OLLAMA_MAX_QUEUE` to 512, and supports multiple residents. Its [current scheduler source](https://github.com/ollama/ollama/blob/main/server/sched.go) shows the critical context caveat: changed runner options trigger reload. Keep it as the Ollama authority. The Pipeline remains the only cross-engine authority.

### Agent-stack prior art

Role prompts on one model are normal practice. [CrewAI agents](https://docs.crewai.com/en/concepts/agents) independently select role, tools, function-calling LLM, and context policy; they need not select different base models. [LangChain's multi-agent guidance](https://docs.langchain.com/oss/python/langchain/multi-agent) explicitly says a single agent with dynamic tools/prompts often achieves similar results, and emphasizes context engineering over model proliferation. This supports role-sharing, but also warns that isolated reviewers and parallel work have different context/QoS needs. “Same weights” must not become “same prompt, same tools, same independence claim.” In particular, an independent judge for a model-seat decision must not be the contestant's own core model.

## 3. Memory budget: the current core leaves roughly a 10 GiB specialist

Use one holistic envelope for design arithmetic even though the current load guard does not charge every host service to its own model budget:

```text
B = 37 GiB                         incident approximation, not a fixed ceiling
M = 2 GiB                          current LOAD_GUARD_MARGIN_GB default
I = 16.5 GiB                       incident Inkling projection
R = 5.4 GB                         historical pinned-router measurement
E = 2.2–3.4 GB                     historical EG2 service range in consumer run logs
Smax = B - I - R - E - M - K - P
K = core/specialist KV + parallel-slot allocation, unknown here
P = prefill/transient headroom, unknown here
```

The router and EG2 figures come from `reports/embedding_consumers/RUNTIME.md`; `I`, `B`, and the 15.3 GiB hunt Gemma projection are incident inputs. GB/GiB reporting is not normalized in those sources, so these are planning approximations. Re-measure all values in one live snapshot before using them for admission.

| Core scenario | Core set before specialist | Upper bound for specialist after 2 GiB margin, **before K/P** | Consequence |
|---|---:|---:|---|
| Current Inkling, 16.5 | 24.1–25.3 | **9.7–10.9** | Existing 15.3 hunt Gemma and larger specialists are not a valid resident pair. |
| Inkling expert-offload candidate, 10.2 upstream | 17.8–19.0 | **16.0–17.2** | Hunt Gemma 15.3 is nominally possible, but KV/prefill can still invalidate it. |
| Small core at 6.0 (illustrative, not a seat selection) | 13.6–14.8 | **20.2–21.4** | More specialist room, but quality/tool ability must win a seat A/B. |

**No existing large specialist is certified by this arithmetic.** Under the current Inkling core, the largest allowable specialist is at most about 10 GiB and less after KV/prefill. Under expert offload, 15.3 GiB is only a static candidate. The 29.1 GiB Qwen3.8 GGUF incident footprint does not fit any of these core-set envelopes. A specialist that cannot fit must run after the core is deliberately unloaded in a separate maintenance mode, be replaced after a seat decision, or remain unadmitted; queueing does not change that algebra.

The first hunt pilot does **not** need the offload to work: sharing the already-resident Inkling removes the separate 15.3 GiB Gemma weight allocation entirely. Offload is a second, independent A/B for specialist headroom and latency.

### Required full-working-set equation

Admission must eventually use measured values for:

```text
core weights + core hot KV (interactive + hunt sequences)
+ one large specialist weights + its active KV
+ pinned router + host services reserve
+ prefill/transient reserve + non-model safety margin
```

For Ollama, use its actual runner context and `OLLAMA_NUM_PARALLEL`; the FAQ notes that context allocation grows with parallel requests. For oMLX, measure engine-reported actual size and activity at representative concurrency. A static `estimated_size` alone is not a fit proof.

### Initial KV/context policy by role

These are starting caps to test, not permission to silently truncate a task. Prompt-budget overflow must produce a visible compaction/routing decision.

| Role | Initial resident window | Why / measurement |
|---|---:|---|
| Tiny intent/task router | 2K, max concurrency 1 | Current seat; titles/tags/follow-ups do not need chat-scale KV. |
| Hunt source understanding / notable JSON | 8K | Current prompts are short; validate real maximum prompt tokens and schema validity. |
| Security reviewer interactive | 32K starting cap, not 256K by default | Preserve job ids and tool receipts; test real hunts/reviews. Escalate a genuinely larger case deliberately. |
| General chat / documents / research core candidates | 32K | Matches current daily/documents/research seats; measure tool-schema plus result usage. |
| Shared core engine ceiling | 32K or 64K after measurement | One stable oMLX core configuration; do not allocate 256K for every role by default. |
| Coding/deep/SPL specialist | 96K/128K according to incumbent | Current quality evidence is tied to large contexts; no silent downgrade during consolidation. |
| Compliance reading/mapping | 128K specialist | Real full-document readings and citations depend on this window. |
| Compliance council Qwen/Granite | 32K/16K | Keep current independent-seat contracts. |
| Audio/vision | 16K | Modality-specific specialist; image token memory must be included in P/K. |

On Ollama, implement this as a **stable context per resident runner**, not alternating per-request values. On oMLX, verify whether the installed profile/context controls change only request settings or force a reload before using profiles for context. Sampling profiles are not evidence of dynamic context support.

## 4. Design invariants

1. **Core hits do not wait for specialist replacement.** They enter the native core scheduler directly.
2. **One large-specialist replacement is serialized and FIFO.** Its queue wakes on request completion, model activity/state transition, memory-counter change, engine recovery, and client cancellation—not on a total elapsed-time deadline.
3. **A stalled queue is observable.** Record queue position, blocker, last state change, engine request id where available, and progress. Elapsed time is telemetry. A lack of forward state transitions invokes diagnosis/cancellation policy, not an arbitrary successful-turn kill.
4. **Statically impossible work fails honestly.** `never_fit` includes the full working set and is produced before an indefinite wait. Dynamic `over_budget_now` queues.
5. **Ordinary swaps never evict core or busy models.** Host-safety recovery is a separate explicit path. A native core pin is enabled only after a fit proof and fixed/justified host reserve.
6. **Fallback must preserve the requested contract.** Tools, modality, JSON/schema, safety posture, and minimum context are checked per engine/model. Otherwise return a retryable unavailable state for API/jobs or a visible incapability notice for chat; never silently produce a plausible non-tool answer.
7. **A job and its chat driver share receipts and a lease only while needed.** The lease prevents mid-job eviction; it does not pin an unused model forever.
8. **No independent-judge collapse.** Compliance diversity seats and independent model-evaluation judges remain independent unless their own decision evidence says otherwise.
9. **No duplicate schedulers.** oMLX owns oMLX batching/LRU/pin/TTL; Ollama owns its runner queue/LRU; Portal owns only cross-engine admission, role policy, capability, and host-job coordination.
10. **No new test suite.** Implementation lanes extend existing unit tests as merge gates and prove behavior through existing QAT scenarios and real OWUI workflows.

## 5. Small-footprint candidates (≤ approximately 10 GB)

Vendor agent benchmarks are intake evidence only. They do not predict this Pipeline's parser, exact job-id handling, refusal behavior, or ability to perform `hunt_sources → hunt_start` in one turn. The deciding run is the same real hunt and the same real role workflow through OWUI → Pipeline → engine, with the incumbent reproduced in that run and independent judges for subjective outcomes.

The “specialist bound if core” column substitutes the candidate for Inkling in the Section 3 envelope and still excludes KV/prefill. “Shares current Inkling?” means only that the candidate is below the 9.7–10.9 GiB static upper bound beside current Inkling; it is **not** a co-fit claim.

| Priority / candidate | Actual format and footprint evidence | Tool evidence and uncertainty | Shares current Inkling? | Specialist bound if core |
|---|---|---|---|---:|
| **A0 — Inkling-2-Mini-oQ4e-mtp with routed-expert SSD offload** | oMLX oQ4e + MTP. Current checkpoint is 15.7 GiB including DSpark per `config/backends.yaml`; 0.8.4 reports 10.2 GB on a 24 GB Mac for **oQ4e** with experts on SSD. Applicability to the MTP checkpoint and the draft's extra memory is unproven. Ollama `inkling-2-mini` NVFP4 remains a separate fallback artifact. | Best starting evidence: the reviewer performed sources→start in 2/2 trials; Granite and Qwen3.8 did not start. Unknown: offload latency on M4 Pro, SSD wear/IO, concurrency, and whether offload engages at this host's settings. | Same core; a 15.3 Gemma specialist would leave only 0.7–1.9 before K/P | 16.0–17.2 |
| **A1 — Qwen3.5-9B** | Existing oMLX `Qwen3.5-9B-oQ4e-mtp`: **6.529 GB (6.081 GiB)**; Ollama Q4_K_M: **6.6 GB**, including a 922 MB vision projector. Intake facts are in `coding_task/FINDING_AUTODAILY_COLDSTART_INTAKE.md`. | [Vendor card](https://huggingface.co/Qwen/Qwen3.5-9B): BFCL-V4 66.1, TAU2 79.1. Local oMLX typed `get_weather` passed 2/2 on 0.8.1; the Ollama tag's stored template is only `{{ .Prompt }}`, so its native renderer/tool loop still needs proof. Existing auto-daily cold-start screen is a different seat decision. | Yes; 3.1–4.7 remains before K/P | 19.6–20.9 |
| **A2 — NVIDIA Nemotron 3.5 Bolt E4B** | [Official Q4_K_M GGUF](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB): **6.18 GB** despite the “4GB” product name; optional DFlash is additional. A UD-Q4_K_XL ctx8k GGUF is already registered. oMLX needs a supported Gemma-4 conversion and parser proof. | Vendor Q4 results include BFCL-v3 67.31, ToolSandbox 74.13, RelyToolBench 69.29. NVIDIA's voice-agent guide also documents calls emitted as plain text in some sessions; this is exactly why a live multi-turn test is required. | Yes; 3.5–4.7 remains before K/P | 20.0–21.2 |
| **A2 — Mistral Ministral 3 8B Instruct 2512** | [Official model](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512) has native function calling/JSON and vision; [MLX 4-bit artifact](https://huggingface.co/mlx-community/Ministral-3-8B-Instruct-2512-4bit) is **5.6 GB**. Ollama GGUF Q4_K_M is the fallback intake target, not an installed artifact claimed here. | Native Mistral tool parser is documented. No Portal evidence. It could later contest light vision as well as core, but that would be a separate named seat decision. | Yes; 4.1–5.3 remains before K/P | 20.6–21.8 |
| **A3 — LiquidAI LFM2.5-8B-A1B** | [Vendor release](https://www.liquid.ai/blog/lfm2-5-8b-a1b) reports **under 6 GB** and day-one MLX + llama.cpp support. Intake must select and measure exact MLX 4-bit and GGUF Q4_K_M artifacts. The local ~5 GB *uncensored fine-tune* is not the base model. | Vendor BFCLv3 64.79 and strong chained-tool claims. Local evidence is only 5/5 extraction on the uncensored fine-tune with tools disabled; it does not transfer to base-model tool calling. Reasoning-only output needs loop/latency checks. | Yes; about 3.7–4.9 remains before K/P | 20.2–21.4 |
| **A3 — Qwen3.5-4B compact alternate** | New MLX 4-bit + GGUF Q4_K_M intake; exact artifacts must be measured. Use only if 9B cannot clear the full working-set budget. | [Vendor card](https://huggingface.co/Qwen/Qwen3.5-4B): TAU2 79.9 but BFCL-V4 50.3 versus 66.1 for 9B. It is not an equal-quality assumption. | Expected at 4-bit, but unproven until an artifact exists | Approximately 21.2–24.4 at 3–5 GB |
| **Baseline — Gemma 4 E4B QAT** | Existing Ollama QAT artifact, about 6.1 GB in current config; an oMLX counterpart would need verification. | Existing WFE: 9/9 home:coding and 9/9 discovery:research, explicitly **not separated** from incumbent at small n. No successful hunt-start evidence. It is a control, not the leading candidate. | Yes; about 3.6–4.8 remains before K/P | 20.1–21.3 |

**Do not reopen on footprint alone:** Granite 4.1 8B and Qwen3.8-27B both failed to call `hunt_start` in the 2026-11-26 two-run-per-arm screen; Qwen3.8 is also far above this footprint band. Bonsai's very small builds were already rejected on agentic WFE results (21/42 and 11/42 versus 33/42) and the closeout says the single-use win was not worth a third engine. A new third-party BFCL table does not overturn those real-use findings.

### The measurement that decides the core/hunt candidate

1. **Named decision:** `hunt-reasoning` and its council helper share the reviewer core, incumbent Gemma-4-26B QAT; action on a win is one reversible workspace-hint change plus a 2–3 day trial. The fallback if unproven is the incumbent.
2. **Preflight:** capture the real reviewer request and one real hunt JSON request through the product; prove each candidate's template/parser, no-tools hunt call, maximum prompt size, exact JSON/schema, and engine-reported full footprint. No rows count before independent judges approve setup and grading.
3. **Small outcome sample:** reuse real indexed telemetry and labelled hunt notables, not generated documents. Compare source understanding, false notable rate, missed notable rate, valid JSON, exact evidence references, and terminal job outcome. The incumbent must reproduce its known result in the same run.
4. **Workflow acceptance:** run `s5-security-hunt-workflow` twice per arm. Require sources→start in one turn, `COMPLETE`, `splunk_requests > 0`, answer consistent with service receipts, and no cross-engine 507/no-answer fallback. A conversation that merely talks about a hunt is not a row.
5. **Concurrency and residency:** with a hunt active, issue a real reviewer chat turn. Record core resident count, queue/TTFT, hunt throughput, oMLX activity, host memory, and any fallback. Test hunt concurrency 1, 2, then 4; do not begin at 8.
6. **Stop rules:** two valid inconclusive runs close the question and keep Gemma. Any malformed tool/job id, silent model substitution, or setup mismatch voids the affected row. Offload and model-choice A/Bs are separate decisions so a latency setting cannot be confused with model quality.

## 6. Workspace map — all 22 production workspaces

“Core” below means already on the proposed Inkling/core control plane, not that a fleet-wide pin is approved. “Candidate-to-merge” means the cheapest next A/B may consolidate it; the incumbent stays until that run wins. “Specialist” means modality, context, quality, refusal posture, or independent-judge diversity currently justifies a separate seat. Variants are explicit where they change the answer.

| Workspace | Current seat / evidence from config and QAT history | Map | Unknown and cheapest decisive live measurement |
|---|---|---|---|
| `auto` | Intent router; its 9B hint is not the normal destination after classification. | **Core control plane** | No model merge. Prove ordinary OWUI prompts route without loading the fallback hint; retain tiny router. |
| `auto-general-uncensored` | Inkling **abliterated**, live-proven 2026-11-25 including Ollama failover and CBRN behavior. | **Specialist: safety/lineage** | Do not merge into standard Inkling. A/B only if a single checkpoint can preserve uncensored answers and CBRN refusals on real prompts. |
| `auto-daily` | Nemotron 30B-A3B; fast/deep/Gemma variants; an Inkling variant already exists. Cold-start Qwen9/Gemma12 screen remains open in the seat ledger. | **Candidate-to-merge** | Use the existing Inkling variant in the already-bounded real daily tasks: memory, documents, web, titles excluded, ordinary chat. Grade outcomes and cold/warm TTFT; do not disturb the open cold-start screen's controls. |
| `auto-coding` | Qwen3.8-27B 96K; real-use 15/16 versus Qwen3-Coder 5/16. Many specialist variants. | **Specialist** | Test Inkling only on a small set of real repo repairs with test outcomes. A general chat/tool win is not coding evidence. Keep 96K and coding-specific variants. |
| `auto-spl` | Qwen3.8-27B, selected on SPL/coding evidence; shares Qwen with coding/deep/compliance. | **Specialist: consolidate by family first** | Real SPL/YARA/Sigma correctness and tool receipts. Before a core A/B, route this seat to the same Qwen specialist as other Qwen roles to remove swaps without changing model. |
| `auto-security` | Standard Inkling; QAT security 8/8 in 116.9 s. Uncensored and multi-hop variants have separate contracts. | **Core (base)** | Pin only with reviewer/hunt fit. Base can share immediately after QoS proof; pentest, uncensored, chains, and independent council variants remain specialist. |
| `tools-specialist` | Qwen3.6-35B multi-call composition; E4B fast variant has small-n WFE evidence. | **Candidate-to-merge** | Real multi-tool sequences, not single weather calls: parallel calls, result carry, correction after a tool error, exact typed arguments. Inkling wins only with no outcome loss. |
| `auto-reasoning` | K2-Horizon-MoVA base; Qwen deep and GLM math are deliberate quality exceptions. | **Candidate-to-merge (base); specialist variants** | Blind-judge real analysis/research synthesis with factual correctness and uncertainty. Deep/math remain separate until their own A/Bs. |
| `auto-council` | All reviewer roles and synthesizer already share Gemma QAT; 12/20 correct and 16/20 key issue, faster than the dense roster. It is also the hunt council helper. | **Candidate-to-merge, tied to hunt** | First make it share whichever model wins `hunt-reasoning`, avoiding a third resident. Compare the same proposal set for missed risks and false challenges. Do not call same-model role calls independent judges for seat selection. |
| `auto-documents` | Gemma QAT 32K; WFE beat Granite, tied Qwen, pooled QAT/plain 46/48 each. | **Candidate-to-merge** | Existing real document create/read/convert scenarios; require correct tool outcome, valid generated bytes/download URL, and content fidelity. |
| `auto-research` | Nex-N2-mini promoted on research probes; recent QAT also saw a four-minute runaway and loop-cap fixes. | **Candidate-to-merge** | Real web research with source receipts, cited answer correctness, and terminal completion. Core may improve the loop, but Nex's factuality/synthesis wins require an incumbent control. |
| `auto-vision` | Qwen3-VL 32B 16K; smaller Qwen3-VL 8B had only a four-case parity floor. | **Specialist: modality** | Image turns and vision-tool outcomes. Qwen3.5-9B or Ministral can contest a *light-vision* seat later, not replace 32B on text-only evidence. |
| `security-reviewer` | Standard Inkling; only seat observed reliably doing sources→start in one turn. | **Core (pilot)** | The hunt A/B above, including a mid-hunt chat. Cap 256K by measured need rather than assumption. |
| `hunt-reasoning` | Gemma QAT 8K, no tools, max concurrency 8; co-load failure with Inkling caused the incident. | **Candidate-to-merge: first** | Labelled real notable judgments and two terminal hunts per arm. If Inkling is unproven, keep Gemma and test offload/smaller candidates instead. |
| `auto-compliance` | Qwen3.8-27B 64K request budget; reading variant uses Gemma plain 128K. Compliance judgment evidence is prompt-sensitive, Qwen stable at 0.952 in the recorded paraphrase probe. | **Specialist** | Do not merge a compliance judge on generic tool evidence. Split simple CVE/catalog work only if real tasks show it is separable; reading requires full-corpus citation/coverage A/B at real packet size. |
| `compliance-mapping` | Gemma plain 128K, machine map/reduce/batch reader. | **Specialist: long context; shares reading family** | Real map/reduce packets with citation and coverage. Consolidate runtime with reading/overflow before considering a smaller core; prove 128K need and quality. |
| `compliance-council-qwen38` | Qwen3.8 independent council seat. | **Specialist: independent judgment** | Keep for diversity. Only a compliance council roster decision with F2, abstention, citation violations, and paraphrase range can change it. |
| `compliance-council-granite41` | Granite 30B independent council seat; prior F2 range 0.833–0.919 across prompt wordings. | **Specialist: independent judgment** | Same council decision, with prompt-paraphrase range attached. No core merge by convenience. |
| `compliance-council-deepseek-r1` | DeepSeek-R1-Qwen3-8B 64K, small independent council seat. | **Specialist: small independent** | It may coexist outside the one-*large*-specialist rule if measured. Merge only after the same council outcome evidence; small size alone is not a reason. |
| `compliance-reading-overflow` | Gemma QAT 64K, explicitly selected for overflow. | **Specialist: long context; shares mapping family** | Real >32K requirement packet that forces overflow. Reuse the same long-context Gemma specialist rather than another resident where engine/context semantics permit. |
| `auto-audio` | Gemma 12B multimodal 16K; image/video/music variants currently use Granite 8B only as a job-driving LLM. | **Specialist (base); candidate-to-merge (media drivers)** | Base needs real audio/image understanding. For image/music/video, test Inkling on start→status→download receipt workflows; the actual media model is a separate host-memory job. |
| `task-router` | Gemma E4B obliterated 2K, pinned, max concurrency 1; titles/tags/follow-ups. | **Core helper** | Already the right shape. Keep pinned and separate; measure its current footprint, no seat A/B needed for the architecture. |

### Background-job map

| Job / caller | Target working set | Reason and proof |
|---|---|---|
| Hunt reviewer chat | Standard Inkling core | Existing sources→start capability; prove two terminal hunts plus mid-hunt chat. |
| Hunt source understanding and notable judge (`PORTAL_HUNT_JUDGE_MODEL`, default backend `omlx-general`) | Same model that wins the hunt-core A/B | Removes the second 15.3 GiB weight allocation. Hunt calls have no tools; prove JSON and labelled judgment, not just chat tool calls. |
| Hunt council (`auto-council`) | Same hunt-core model during the pilot | Already role-prompt sharing on one model; prevents a third resident. Do not claim model-independent evaluation from it. |
| Deterministic security review | No additional chat model by default (`DEFAULT_READER=None`) | Keep it deterministic. Embedder remains resident; do not invent a judge to fill the core. |
| Research synthesis and routine research tools | Candidate core after research A/B | Real source/citation outcome. WFE/seat judges remain independent and are not folded into a contestant core. |
| Compliance map/reduce/reading/overflow | Long-context Gemma specialist initially | Real packet context and citation coverage dominate; consolidate these roles with each other first. |
| Compliance council | Qwen + Granite + DeepSeek specialists initially | Independent roster and prompt-sensitive F2 evidence; one-large plus small-specialist co-fit is measured, not assumed. |
| OWUI titles/tags/follow-ups | Existing task-router helper | Current 2K pinned seat avoids chat-model loads. |
| Memory, RAG, compliance retrieval, Bully | Existing EmbeddingGemma host service | It is part of the host reserve, not a reason to load another chat model. |
| Image/music/video generation | Core LLM driver is an A/B; generation engine joins host-job admission | MFLUX/ACE-Step/LTX peaks can exceed the proposed specialist allowance. A model-core design that ignores these jobs is incomplete. |

This map deliberately produces **few immediate seat changes**: standard security/reviewer on Inkling, hunt reasoning/council as the first candidate, and family-level consolidation of Qwen and long-context Gemma roles. Everything else is a measured migration queue, not a fleet-wide reassignment.

## 7. Target architecture

### Request classes and scheduling

| Class | Scheduling decision |
|---|---|
| Core interactive and core background | Dispatch to the resident logical core immediately, subject to bounded per-role generation concurrency. Do not queue behind a large-specialist cold load. |
| Large specialist | Admit into one host-wide FIFO replacement queue. One large specialist may be resident beside core; a second waits for the first to become idle and be reclaimed. |
| Small specialist/helper | Allow beside core and the large specialist only when the full projection fits. The one-large rule does not force pointless swaps. |
| Router/embedder | Existing always-on services, charged to the host reserve. They are not specialist-slot members. |
| Media/host MLX job | Initially use its existing admission control; then join the same host plan so it cannot consume the memory reserved for core + specialist + prefill. |

“Logical core” is one identity across engines, not one copy on each. If oMLX is down and a compatible Ollama Inkling fallback serves a chat, new core work stays on that fallback while oMLX recovers. Once idle, recovery drains and unloads the duplicate before returning to the pinned oMLX core. Never let recovery create two 16 GB core residents merely because the primary returned.

### Queue semantics without a wall-clock kill

1. **Plan before enqueue.** Compute `never_fit` from the full declared working set. Return it explicitly with the largest offending component; do not wait 120 seconds and call the same condition a transient refusal.
2. **Register admitted work FIFO across Pipeline workers.** This is operational scheduling state, not conversation state. Existing request-count concurrency limits remain the backpressure boundary; the design does not require an unbounded number of open HTTP requests.
3. **Wait on a state version/condition.** Wake on request completion, model load/unload/activity change, memory-counter movement, engine recovery, or client disconnect. Cross-process polling can remain a missed-wakeup safety mechanism, but elapsed total time is not the decision to fail.
4. **Reclaim only eligible idle specialists.** Busy core, busy specialists, the tiny router, and active job leases are not eviction candidates. Core requests continue while an idle specialist is replaced.
5. **Expose honest waiting.** Trace queue position, blocker, last transition, and engine request id. Any transport keepalive is not assistant content and must not fabricate reasoning or a result. Client cancellation removes the queue entry.
6. **Fail only a real terminal condition.** Invalid request, incompatible capability, static `never_fit`, engine failure, explicit queue-capacity backpressure, or cancellation. A slow but progressing cold load is none of these.

The existing global/workspace request semaphores and `OLLAMA_MAX_QUEUE` still provide overload protection. “Queue, don't reject” is the normal single-host memory-contention policy, not a promise to accept infinite work or keep a dead client forever.

### Fallback contract

Declare and preflight capabilities per engine/model, not just a global `supports_tools` boolean:

```text
tools / parallel tools / typed arguments / exact identifiers
JSON or schema / modality / minimum context / refusal posture
```

- A hunt requires tools on the reviewer call, exact job ids on every engine, JSON on hunt-reasoning calls, and terminal service receipts. An Ollama fallback that only returns friendly prose is **not a fallback** for that workflow.
- A chat fallback may preserve “users always get an answer” only when the model can satisfy the request's required capabilities. Otherwise the honest answer is the visible incapability/queue status, not a response from an unrelated model.
- Preflight the actual Ollama Inkling fallback on sources→start before marking it hunt-compatible. The existing typed weather probe is insufficient.
- Preserve a visible route/model receipt on every fallback. Do not retry a started stream into a second answer.

## 8. Phased plan and live proofs

Every phase is independently reversible. Before each Pipeline change, run the normal offline gates; after merge, the orchestrator rebuilds through `./launch.sh`, runs `./scripts/smoke_stream.sh`, and proves the real OWUI → Pipeline → engine path. No phase creates a new benchmark suite.

### Phase 1 — hunt workflow: remove the second model before adding scheduler machinery

**Change:** one reversible seat experiment points `hunt-reasoning` and the hunt council helper at standard Inkling, already used by `security-reviewer` and base `auto-security`. Keep all three role prompts and request sampling distinct. Start hunt concurrency at 1, then measure 2 and 4. Do not enable expert offload in this arm.

**Why first:** it directly addresses the failed workflow and can reduce the pair's weight requirement by 15.3 GiB without waiting for an engine upgrade, a smaller model, or new queue code.

**Live proof:**

1. Capture the current Gemma incumbent's real labelled-notable results and one real terminal hunt as the control. If it cannot reproduce its known outcome, the setup is void.
2. Run the Inkling arm's preflight and independent grading review, then two `s5-security-hunt-workflow` runs. Require sources→start in the first turn, `COMPLETE`, nonzero Splunk work, and an answer true to receipts.
3. During a real running hunt, use the reviewer in OWUI for a status/explanation turn. Require exact job id, correct tool result, no 507, no fallback to a non-tool model, and no mid-prefill abort.
4. Inspect oMLX activity: one standard Inkling resident serves reviewer and hunt calls; no Gemma load occurs for these roles. Record interactive TTFT and hunt throughput at concurrency 1/2/4; choose the highest tested concurrency whose interactive p95 TTFT is no more than 2× its solo baseline and whose outcomes remain correct. Report elapsed time; never kill on it.
5. Run a 2–3 day real-use trial only after the A/B wins. Two valid inconclusive runs keep Gemma.

**Simplify on success:** the hunt-specific Gemma resident and the proposed per-pair co-residency lease become unnecessary. The `da1ccdf6e` job-waits stopgap remains temporarily for other seats; remove its hunt special case only after the general queue lands.

**If unproven:** restore Gemma and test Inkling expert offload + Gemma co-residency, then Qwen3.5-9B, against the same decision. Do not keep Inkling merely because it is the concept's preferred core.

### Phase 2 — native core residency and one-large queue

**Change:** after the Phase 1 fit proof, configure standard Inkling as an oMLX pinned/preloaded model with a bounded stable context. Replace the specialist's total wait deadline with the state-change queue above. Use oMLX native activity/load state and Ollama `/api/ps`; keep the Pipeline's host-wide lock and cross-engine accounting. Set a justified fixed host model/reserve envelope or prove that the dynamic ceiling cannot invalidate the declared fit.

**Live proof:**

- Start a real hunt on core, then issue two different real large-specialist workflows from OWUI. The first may replace the idle specialist; the second must show queued state and run after the first drains. A core reviewer turn must still complete while the specialist waits.
- Let a genuine cold specialist load exceed the old 120-second wait if that is what the host naturally does. Pass means continued progress and eventual correct completion with elapsed time recorded, not 507 at 120 seconds. Do not inject an artificial delay.
- Cancel a queued OWUI turn and verify that its queue entry disappears without evicting core or running the cancelled specialist.
- Ask the plan for a statically impossible core + oversized specialist combination. It must return `never_fit` with components rather than queue indefinitely.
- Stop oMLX during a real compatible fallback test. The Ollama core candidate must either pass its capability preflight and preserve the workflow or visibly refuse that workflow. Recovery must not leave duplicate core copies resident.

**Simplify on success:** remove time-based `quiet`/`deadline` refusal behavior for transient specialist contention, the hunt-only wait stopgap, and any duplicate per-pair lease. Retain `never_fit`, host-safety admission, backpressure, and metrics.

### Phase 3 — bring non-chat host jobs into the same memory envelope

**Change:** extend the existing media/host-job admission receipt to declare estimated peak, active state, and reclaimability to the host plan. Do not add a second gateway. Core + specialist reserves must include concurrent MFLUX/ACE-Step/LTX and other configured host MLX work.

**Live proof:** while a hunt is active on core, run a real `image_start` from OWUI and then a real music job. Each either runs within the declared envelope or waits with a visible job state. Require correct generated bytes/download URL, hunt completion, no 507, no host swap emergency, and no mid-generation unload. Repeat with a specialist resident. If the jobs cannot fit, the receipt must say what it is waiting for; elapsed render time is not failure.

**Simplify on success:** one host admission receipt explains chat and media waits. Existing media-specific estimates stay as input data, not a separate competing decision.

### Phase 4 — consolidate families and merge core candidates one seat at a time

**Change:** first make same-model roles share runtime without changing their model:

- Qwen3.8 SPL/coding/deep/compliance roles use the Qwen specialist rather than independent swaps.
- Compliance reading/mapping/overflow use the appropriate long-context Gemma runtime, with plain/QAT differences preserved where the seat ledger requires them.
- Hunt council always follows the selected hunt reasoner.

Then run the Section 6 candidate-to-merge A/Bs in this order: `tools-specialist`, `auto-documents`, `auto-daily`, `auto-research`, media job drivers, base `auto-reasoning`. Each gets its own small real-task sample and reversible trial. Coding, long compliance, vision, uncensored, and independent council seats are not bulk migrations.

**Live proof per seat:** incumbent and candidate each perform the same real OWUI task with the same uploads/tools; the outcome and actual artifact/receipt decide. Record model loads during a two-role sequence: a same-family consolidation must not reload identical weights, and a core merge must not load the retired seat. Any quality regression restores the hint.

**Simplify on success:** remove redundant runtime swaps and old `model_hint` wiring only after the trial. Workspaces and role prompts remain; this is not a workspace-removal program.

### Phase 5 — context/tag and code simplification

**Change:** choose one stable context per Ollama resident from the measured role policy. Forward request-time `num_ctx` only when the whole resident uses the same value or an intentional reload is the requested behavior. Use oMLX profiles for sampling only after the installed contract proves their behavior. Preserve GGUF fallbacks and their own capability probes.

**Live proof:** alternate two real roles that previously used different `-ctxNk` tags. The shared resident must retain its chosen context with no runner reload, no truncation, and correct outcomes. Deliberately alternating two different `num_ctx` values in a contract probe must expose the expected reload, documenting why per-role dynamic context was not adopted. Run the engine contract check and streaming smoke after every transport change.

**Delete only after receipt/caller audit:**

- unused derived `-ctxNk` aliases (zero extra weight bytes is expected; the win is fewer runner configurations, not disk reclaim);
- `preferred_residents` if native core pin/preload fully replaces it;
- `hot_seat_protect_s` if measured multi-model residency makes its prefix-cache workaround unnecessary;
- per-pair co-residency declarations and the job-waits stopgap after the generic working-set/queue covers their callers;
- capacity-fallback variant selection that can violate capability, replaced by the capability-aware path;
- duplicate elapsed-time refusal logic, while retaining stall detection and report-only latency.

Do not delete plain versus QAT weights as “context tags”; they are different artifacts and remain governed by WFE/seat decisions. Do not delete the open auto-daily screen's artifacts before its ledger row closes.

### Phase 6 — final whole-system acceptance

Run targeted real regressions first, then one quiet-host QAT on one SHA. The quiet-host requirement remains: core residency does not make pytest/xdist or other external pressure free.

Acceptance requires:

- two hunt workflows complete with real Splunk work and truthful answers;
- a mid-hunt reviewer turn stays on capable core;
- specialist queue/cancel/`never_fit` proofs pass;
- no cross-engine 507 or tool-incapable silent fallback in those paths;
- media job admission respects the declared host envelope;
- existing QAT rows have no outcome regression versus the accepted baseline;
- final resident/log snapshots contain no unexpected duplicate core or retired-seat reload.

A stitched collection of historical green rows is not the final proof.

## 9. Risks and explicit tradeoffs

| Risk | Why it matters | Mitigation / decision evidence |
|---|---|---|
| Quality loss from one generalist | Inkling's hunt tool success does not imply coding, compliance, research, math, or document quality. | Section 6 per-seat A/Bs, incumbent controls, independent judges, instant hint revert. Specialist is a permanent supported category. |
| Correlated “council” judgments | Same-model role prompts can share blind spots; auto-council already accepts this tradeoff for speed. | Keep compliance diversity and external independent seat judges. Do not market same-core calls as independent model review. |
| Core concurrency and head-of-line blocking | Shared weights eliminate loads, not GPU serialization or long-prefill interference. | Start hunt concurrency 1; test 2/4 against interactive p95 and outcomes. Bound background work; do not assume M5 Ultra release numbers apply to M4 Pro. |
| KV/prefill exceeds the static math | 256K core defaults and parallel slots can invalidate an apparently fitting pair. | Stable smaller contexts, full-working-set admission, real activity/RSS snapshots, explicit `never_fit`. |
| Prefix-cache misses/pollution | Different system prompts and tool schemas share little or no prefix; one-shot hunt calls can evict useful chat blocks. | Compare real TTFT/cache behavior. Use supported `X-oMLX-Cache-Store: off` only after an A/B for one-shot roles; do not infer hits from `cached_tokens`. |
| Fallback silently drops tools or changes safety | Same-family GGUF/MLX builds differ in renderer, parser, template, quant, and refusal posture. | Capability preflight per engine and workflow; visible incapability is preferable to a wrong answer. Uncensored remains a separate identity. |
| “Always answer” conflicts with honesty | An unrelated or incapable model produces a 200 response but fails the actual job. | Availability means a truthful completion/status. Jobs/API retain retryable errors; chat gets an explicit notice. |
| Core pin worsens host emergencies | A permanent 16 GB reservation plus media/Docker/test pressure can recreate swap/jetsam risk. | Pin only after full fit; keep host-safety recovery and fixed/justified reserve. Include host jobs before declaring completion. |
| Queue hides a deadlock or OWUI timeout | No wall-clock kill can turn an engine wedge into an infinite HTTP turn. | Terminal engine-health error, client cancellation, bounded request-count backpressure, queue/blocker/last-transition receipts, transport keepalive. |
| Dynamic `num_ctx` reloads on Ollama | One tag with role-varying context can be slower and less stable than derived tags. | Stable context per runner; prove reload behavior before tag deletion. |
| Offload causes latency/SSD problems | Expert streaming may make hunt batches or interactive turns IO-bound and writes/cache may add disk pressure. | Separate offload A/B with TTFT, throughput, actual RSS, SSD IO/cache limits, and rollback. Never require it for Phase 1. |
| Native engine upgrade changes contracts | Same-day oMLX features can alter admin APIs, parsers, cache, and memory accounting. | Existing engine auto-update contract, native arm64 check, targeted live proofs before feature use, rollback. |
| Scheduler duplication | Portal + oMLX + Ollama + llama-swap would produce contradictory eviction and fallback decisions. | No new gateway. Native engines own local scheduling; Portal owns only cross-engine/host policy. |
| Test/bench proliferation | A new architecture can otherwise spawn another unbounded campaign and suite. | Named seat decisions, small real samples, existing QAT scenarios, two-inconclusive stop rule, no new suite. |

## 10. Orchestrator command sheet

These are the commands for the live operator/orchestrator after the relevant implementation merges; they were **not** run by this design lane.

### Rebuild and smoke the actual change

```bash
cd /Users/chris/projects/portal-5
./launch.sh rebuild && ./launch.sh up && ./launch.sh seed
./scripts/smoke_stream.sh
```

Success requires the seed to contain the changed workspace prompt/hint, smoke to pass, and the running container to contain the merged config. Rebuild alone does not reseed OWUI.

### Run the existing hunt scenario twice from one immutable snapshot

```bash
cd /Users/chris/projects/portal-5
SHA=$(git rev-parse --short HEAD)
git worktree add "/Users/chris/projects/portal-5-wt/qat-$SHA" "$SHA"
cd "/Users/chris/projects/portal-5-wt/qat-$SHA"
uv sync --all-extras --frozen
uv run python -m tests.qat \
  --scenario s5-security-hunt-workflow \
  --output-dir "results/qat/core-hunt-$SHA-a"
uv run python -m tests.qat \
  --scenario s5-security-hunt-workflow \
  --output-dir "results/qat/core-hunt-$SHA-b"
cat "results/qat/core-hunt-$SHA-a/QAT_REPORT.md"
cat "results/qat/core-hunt-$SHA-b/QAT_REPORT.md"
```

Both reports must be PASS, and the stored service receipts—not just the grader's conversation text—must show terminal `COMPLETE`, `splunk_requests > 0`, the same job id in answer and receipt, and no 507/fallback substitution. Any setup void is fixed and rerun; it is not scored against the candidate.

### Capture the real resident/activity evidence

```bash
curl -fsS http://127.0.0.1:11434/api/ps | python3 -m json.tool
curl -fsS \
  -H "Authorization: Bearer $OMLX_API_KEY" \
  http://127.0.0.1:8085/admin/api/activity | python3 -m json.tool
docker logs --since 30m portal5-pipeline 2>&1 \
  | grep -E 'load_guard|backend.selected|capacity_fallback|hunt'
```

On an older installed oMLX, use its existing `/v1/models/status` and `/api/status` read surfaces instead of assuming the new Admin API exists. The successful Phase 1 snapshot has one standard Inkling resident for reviewer/hunt and no hunt Gemma load. The failed snapshot has a second model, an Ollama fallback that did not pass hunt capability, repeated cold loads, or 507/no-answer entries.

### Check the core-set projection before enabling a pin

```bash
cd /Users/chris/projects/portal-5
curl -fsS -X POST http://127.0.0.1:9099/admin/load-plan \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"models": [{"engine": "omlx", "model": "Inkling-2-Mini-oQ4e-mtp"}]}'
```

Replace/extend `models` with the actual specialist declaration accepted by the running route. The response must include every core/specialist component and fit with the measured KV/prefill reserve. A response covering weights alone is insufficient for Phase 2; implement the full declaration rather than treating this current endpoint as proof of the final envelope.

## 11. Coding-lane decomposition

1. **Hunt-core seat A/B:** reversible config, real labelled/hunt evidence, fallback capability preflight; no scheduler rewrite.
2. **Native residency + one-large queue:** oMLX native pin/activity integration, cross-engine condition queue, static `never_fit`, cancellation, receipts; delete the hunt stopgap after proof.
3. **Capability-aware fallback:** per-engine contract and logical-core recovery without duplicate residents.
4. **Host-job admission:** media/host peaks join the same plan and receipts.
5. **Family/context consolidation:** same-model runtime sharing first, then measured role merges and tag simplification.
6. **Final targeted QAT + one-SHA acceptance:** no new suite, no bulk seat migration.

The architecture is successful if it makes the common path boring: reviewer and hunt use one hot model, specialists wait visibly when they truly cannot coexist, and no request is answered by a model that cannot perform the requested contract.
