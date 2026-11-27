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
