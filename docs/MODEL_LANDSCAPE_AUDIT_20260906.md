# Model landscape audit and remaining work — 2026-09-06

This is a dated, read-only audit of saved project evidence and local model-store metadata. **The claim “53 production tags / ~782 GB plus 62 pending / ~784 GB” reproduces an old report, but is not an accurate account of current unique storage or unfinished evaluations.**

The execution deliverable is [Task: close every model disposition](TASK_MODEL_FLEET_CLOSEOUT_20260906.md), with a [188-identity worklist](MODEL_FLEET_CLOSEOUT_20260906.tasks.json). Its goal is to close each identity as integrated, deliberately retained for a named purpose, or removed with a durable project record, then retire the old pending category.

No project scripts, tests, model calls, server queries, downloads, cleanup, configuration changes, or job controls were run. Only filesystem reads and independent parsing/arithmetic were used; this document and its evidence snapshot are the deliverables. An active job may change files after observation. “Configured” below means present in configuration, not live routing verified during this audit. Upstream model-card scores are outside this audit; a catalog's marketing claim is not a locally reproduced result.

## 1. What the numbers actually mean

| Claim / measurement | Finding |
|---|---|
| 53 production / 781.9 “GB” | This is the heading in `reports/model_cleanup_audit.md`. All 53 exact tags remain in the inspected Ollama store, but their manifest layers total **381.177 GiB after deduplication**, not 781.9 GiB. The 53 names collapse to 26 names after case folding and removing context suffixes; this is a naming count, not a count of distinct checkpoints. |
| 62 pending / 784.1 “GB” | The old ledger has 62 entries, but **only 29 exact tags are present; 33 are absent** from the inspected store. The present set references **351.114 GiB** of unique blobs. Only **259.232 GiB** is exclusive to those 29 tags relative to all other current manifests. This is a storage upper bound for removing the entire set, **not a deletion recommendation**. Some have current production roles. |
| 62 untested models | False. Independent structured-result inspection found a test-attempt record naming every one of the 62 tags. Attempts include successes, failures, skips and limited probes; the number of completely accepted models cannot be inferred from that fact. |
| All checkboxes mean complete | False. All 62 boxes are checked, but their recorded verdict labels are **30 keep-open, 20 investigate, 12 investigate-refresh**. None of those labels is a final promote/decline disposition. |
| Current Ollama store | **138 manifests; 381 blob files; 1,064.363 GiB logical blob size and 1,064.364 GiB allocated by file-stat accounting.** Summing every tag's referenced sizes yields 1,875.924 GiB, illustrating how badly aliases inflate totals. |
| Current whole landscape | `config/backends.yaml` has **246 model registrations, 160 unique ID strings, 12 backend entries, 7 groups**. These are configuration counts, not installed models. `config/portal.yaml` has **78 workspaces: 53 bench-prefixed and 25 others**. Neither count is an executable queue. |

The original report totals the `size` field returned by `/api/tags`; its `gb()` divides by `1024**3` while labeling the result “GB.” These are **GiB**, not decimal GB. It does not deduplicate layer digests, calculate sharing between categories, or measure physically reclaimable space. Source: [audit implementation](../scripts/model_cleanup_audit.py), especially `production_bases`, `classify`, `gb`, `render_ledger`, and `render_report`.

The old full report contains 130 tags across all categories. The inspected store has 97 of those exact tags plus 41 other tags. An absent tag is evidence of absence in this store, **not proof of a recorded decline**, and weights may survive under other tags or in MLX/Hugging Face storage. Both old report and ledger have filesystem modification dates of 2026-08-31 UTC, but cite mostly August 11–12 evidence; the latest saved pending-analysis report is August 13. File modification time is not proof of evidence freshness.

### Other storage that the old claim omits

| Store | Unique logical GiB within that root | Interpretation |
|---|---:|---|
| `/Volumes/data01/ollama/models/blobs` | 1,064.363 | GGUF and associated content-addressed layers. |
| `/Volumes/data01/omlx-models` | 243.776 | Includes symlinks into the Hugging Face cache. |
| `/Volumes/data01/hf-cache` | 333.161 | Includes chat, OCR, embedding, speech, image and video artifacts. |
| Union of the three model-store roots | **1,535.683** | Deduplicated by device/inode across roots, including manifests and small metadata. Allocated file-stat total: **1,535.687 GiB**. Do not add the three root totals; they overlap. |

These are filesystem metadata measurements, not a volume-free-space prediction. Inode accounting does not resolve APFS clone/snapshot sharing. Weight contents were neither read nor hashed. The manifest-referenced blob byte total and actual blob sizes agree to rounding; only a few bytes fall outside the referenced set. There is no evidence here of hundreds of GiB of ordinary unreferenced Ollama blobs waiting for garbage collection.

Large non-chat cache consumers include Qwen-Image-2512 (~53.7 GiB), ltx-2.3-mlx-q4 (~55.6 GiB), Z-Image-Turbo (~30.6 GiB), and FLUX.2-klein-4B (~14.9 GiB). These are not automatically pending model evaluations. REAP-288 alone occupies ~68.5 GiB in the oMLX tree. The substantial disk footprint is real; attributing it all to an evaluation backlog is not.

## 2. Why the old classifier cannot determine remaining work

1. **It misses production roles.** It reads workspace/variant `model_hint`, but not arbitrary nested council members, `expert_model`, persona pins, or all backend alias relationships. Current configuration references three old pending entries: Aquila's ctx16k tag in `auto-research`; Mistral Small 3.2 in council member lists; Foundation-Sec in blue-team expert roles. Those require dependency review before any disposal decision. The current UD-Qwen3.6 ctx32k production tag also shares weights with its pending base tag.
2. **Production classification is based on names, not acceptance evidence.** Context suffix stripping classifies sibling tags together without proving that each context setting or serving engine was tested. A manually selectable variant and a default also have different acceptance requirements.
3. **“Documented keep” is a substring match in older audit prose.** Any mention can qualify, even if the prose is not a keep decision. Production/keep checks also precede catalog verdict checks.
4. **An evidence citation is not necessarily a measurement.** Structured `results` rows receive better matching, but other file shapes fall back to whole-text matching. Rebench plans are not excluded from that fallback and appear as the first evidence citation in the old checklist. A plan, incidental model mention, skip, or HTTP failure cannot establish a passing bench.
5. **Checked status does not reduce the header count.** `render_ledger` counts the classifier's entire pending list while preserving checkboxes and investigation notes. The heading is neither the unchecked count nor a count of planned jobs.
6. **Freshness rules themselves aged.** The [August 13 analysis](../reports/PENDING_VERDICTS_ANALYSIS_20260813T170155Z.md) says 0/62 lack post-August-10 evidence, yet the saved checklist retains 12 investigate-refresh verdicts. Neither tells us whether the later Ollama/oMLX versions, scorer repairs, changed templates, or current context settings invalidate a specific result.

The [fact-unit catalog](../portal_wiki/canonical/unit-fact-model-catalog.md) calls its 246 registrations “model ids.” There are only 160 distinct ID strings in those registrations. Likewise, `CLAUDE.md`'s single-Ollama-tier description is contradicted by the configured oMLX backends and aliases. Use current configuration for intended routing and runtime traces for actual routing; old prose alone is insufficient.

## 3. What has actually been exercised

### Historical pending set

Every old pending tag has at least one structured attempt with the tag in a model/result identity field. Appendix A cites the most recent filename-dated exact-tag artifact found in the bounded scan. These are **attempt citations**, not blanket PASS certifications. Workspace-only results can provide additional evidence, but need the historical workspace-to-model mapping; current mappings must not be retroactively imposed on old runs.

The scan covered JSON files under `tests/benchmarks/results`, `tests/results`, and security candidate results, excluding `_archive` directories and files larger than 15 MB. It recognized model/workspace identity fields alongside result/error/skip/score fields and excluded metadata/config/prompt branches. Result identity comparisons were case-insensitive but did not strip context suffixes; on-disk presence used exact manifest spelling. It did not treat report prose as measured evidence. The evidence snapshot lists the paths found. No match in this bounded scan would mean “not established here,” not “never tested.”

### Coding: completed work exists

The August 26–27 [MoE coding report](../tests/benchmarks/results/BENCH_REPAIR_MOE_CODERS_20260826.md) agrees with its [raw 210-sample checkpoint](../tests/benchmarks/results/BENCH_REPAIR_CHECKPOINT_066355de23d5.json):

| Exact candidate lane | One-shot successes | One-repair successes |
|---|---:|---:|
| HauhauCS coder | 28/50 | 14/20 |
| Gemma4 heretic coder | 50/50 | 20/20 |
| Ornith 1.5 coder | 43/50 | 19/20 |

This is a completed ten-problem coding exam on Ollama 0.32.15, not proof of performance on every real repository, tool flow, or context length. Current ctx256k aliases are not the bare tags named in the sample records. Historical [coding repair results](../reports/CODING_BENCH_REPAIR.md) also exist for Devstral, Devstral Small 2, and the Qwen coder incumbent; do not schedule those as never tested. Preserve their stack/scorer provenance when deciding whether a targeted rerun is needed.

### September 6 judgment evaluation: fresh results, incomplete acceptance

The [saved rescored artifact](../tests/benchmarks/results/judgment_probe_v6_rescored_20260906T224306Z.json) contains 12 model entries with 30 cases each. Eleven have zero recorded execution errors; Phi4 Q4 has **30 HTTP 500 errors**, `config_unverified: true`, and `broken: true`. Its zero scores are not evidence of model reasoning quality. Appendix B preserves the rescored metrics, which differ from the original capture's exact-accuracy values; do not combine scorer versions.

Qwen3.8-27B ctx32k and Qwen3.6-27B ctx16k each have 0.90 exact accuracy and 0.9524 F2 on this rescoring, with one false-supported answer each. These results do not prove general compliance acceptance or justify a fleet-wide promotion. Granite4.2-30B Q8 and Granite4.1-8B Q8 also have separate earlier September 6 runs but are absent from the 12-entry rescored file. A consolidated comparison must either rescore those captured outputs under the same rubric or state their exclusion. The current active job's completion was not inferred from filenames or queried from a process/server.

### Limited probes, historical decisions, and invalidated evidence

- **CAD:** the [August 27 partial](../tests/benchmarks/results/cap_cad-overhaul_20260827T164110Z.moe-only.SUPERSEDED.md) is explicitly superseded because of permissive geometry schema, ignored feature keys, missing baked context, and missing bounding-box PASS gating. It cannot support promotion. Geometry fixture validation is not a replacement model gauntlet.
- **Qwen3.8 GGUF / MLX / MTP / DFlash2:** these are separate runtime/checkpoint configurations. The [GGUF catalog](../portal_wiki/canonical/unit-model-catalog-hf-co-unsloth-qwen3-8-27b-gguf-q4-k-m.md) explicitly says the full coding sweep was deferred in favor of IDE use. The [MTP catalog](../portal_wiki/canonical/unit-model-catalog-qwen3-8-27b-oq4e-mtp.md) records speed and tool probes, not a complete coding acceptance. The September 6 GGUF judgment results do not certify the MLX acceleration variants.
- **REAP-288:** [catalog evidence](../portal_wiki/canonical/unit-model-catalog-qwen3-8-flash-next-reap-288-mlx-4bit.md) records quiet-host speed/tool probes and memory limits, explicitly leaves card HumanEval unreproduced, and records an operator decision against an auto default. It is configured as a selectable coding variant. A bounded comparison against Laguna remains a separate optional question; a broad automatic-promotion sweep conflicts with the recorded disposition.
- **Cascade-2:** the [August 31 follow-up](../config/FOLLOWUP_REASONING_OVERHAUL_REMAINING_V1.md) explicitly supersedes its challenger rebench and records it fully dropped. Do not revive B1/C3 from older planning prose.
- **OLMo and decline lists:** that follow-up retains OLMo-3.1:32b-think as a Tier-2 candidate, contradicting the older blanket decline list. Granite4.1:30b-ctx16k remains configured in council/blue-team roles and was just exercised in the judgment run. SuperGemma also remains selected by security variants. No family-wide cleanup should be inferred from the old ~150 GB estimate.

### oMLX conversion work: the “six empty directories” task is stale

The [pool repair task](../config/TASK_OMLX_REASONING_POOL_REPAIR_V1.md) and its follow-up describe six missing conversions. All six now resolve to nonempty filesystem trees: DeepSeek R1 (~4.3 GiB), Granite 8B (~8.5), Granite 30B (~16.8), Tongyi (~16.0), HauhauCS (~18.2), and VulnLLM (~4.0). **Do not plan six fresh conversions based on those documents.** Existing bytes do not prove loadability, tool parsing, or production route success; those are the remaining runtime checks if no newer valid trace closes them.

Two different oMLX directory entries are dangling symlinks: `MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit` and `SuperQwen3.8-27b-abliterated-MLX-4bit`. They are not installed usable checkpoints at those paths. Determine whether either is still wanted before scheduling a download. The store also contains an installed DFlash2 draft (~3.6 GiB); the presence of its files is not speed/quality validation.

## 4. Work plan

Priorities below describe proposed follow-up work, not authorization to execute it during this audit. Complete the active job before scheduling inference work, and reconcile its final outputs first.

| Priority | Work package | Concrete remaining work | Done when / dependency |
|---|---|---|---|
| P0 | Close the active evaluation record | Preserve final captures; establish the actual model/runtime/template/context/scorer for each row; reconcile the 12-model rescoring with separate Granite Q8 baselines; diagnose Phi4 HTTP 500 before a targeted retry. | One comparable result table distinguishes successful captures, errors, skipped candidates and remaining cases. Depends on active job finishing. |
| P0 | Replace the stale pending ledger | Reconcile all 62 rows in Appendix A: 33 absent tags, 29 present; explicitly protect current roles; retain historical evidence and record final disposition or a specific unanswered capability question. | Each row has status, owner, evidence, exact identity and next action. Checked boxes and “investigate” cannot stand for closure. No blanket repull of absent tags. |
| P0 | Repair inventory accounting | Make installed tags, unique weight digests, configured roles, accepted evaluations and queued jobs separate fields. Count unique bytes and exclusive bytes; include council/expert/persona/alias dependencies. Do not use report mentions as test evidence. | Reproducible report whose counts reconcile to manifests and whose queue comes from explicit work items. Implement later; this audit changes no code. |
| P1 | Resolve keep/decline decisions before new benches | Review the present historical pending set, larger recent additions and currently selected specialists. Read existing results first; identify the exact missing decision criterion. | A disposition per checkpoint/role, with any retention deadline and evidence. Bytes alone do not determine promotion or decline. |
| P1 | Validate oMLX pool completion | Inspect existing checkpoint completeness and recorded tool/load traces, then test only unresolved serving/alias/parser behavior when idle. Check DFlash2/MTP configurations separately. | Correct model actually served through intended route; tools and memory behavior verified. No automatic reconversion of six already populated trees. |
| P1 | Finish adaptive UAT | Reconcile actual corpus against AI-3/11/12/26: clean-segment remainder, empty-capture retries, deferred compliance, affected-space rebaseline. Apply assessment/attribution fixes before acceptance. | Current shipped routes covered by valid captures, then assessment, packet and operator capability decisions. Recompute IDs; old counts are estimates. |
| P2 | Targeted reasoning selection | Resolve follow-up C1: DeepSeek R1 incumbent versus Qwen3.6 MoE on reasoning tasks with diversity explicitly considered; separately verify deep-lane eviction behavior. | Role-specific decision and co-resident memory result. September judgment scores are not this entire matrix. Cascade-2 rebench remains closed. |
| P2 | CAD replacement run, if model selection still required | Verify whether a later valid result exists; otherwise run the corrected bounded gauntlet with schema validation, intended context tag and geometry sanity gates. | Valid paired model result; superseded MoE-only payloads excluded from promotion evidence. |
| P2 | Coding/manual specialist gaps | Use completed 210-sample MoE run; isolate current-context/tool-flow gaps. For Qwen3.8 and REAP-288, decide whether real IDE evidence suffices or a bounded Laguna comparison is still worth its cost. | Explicit decision; no full repeat merely because a model remains in the catalog. REAP stays restricted/manual per recorded decision. |
| P3 | Storage disposition | After role decisions, calculate exclusive digests for the exact approved removal set across aliases and caches; separately review large media caches. | Exact list with evidence and predicted bytes; subsequent removal verified separately. 259.232 GiB is not an approved reclaim target. |

The [UAT action register](../tests/uat_adaptive/ACTION_ITEMS.md) lists 33 deferred compliance rows, ~26 empty captures, and clean-segment work paused after 3/63 research challenges, plus documents/CAD/media/image/video batches. These are **saved planning counts**, not audited remaining counts as of this moment. Later follow-up documents supersede parts of that register. Read corpus IDs and latest assessment records to calculate the runnable set after the active job; do not schedule all of it as fresh work.

No defensible total GPU-hours estimate follows from “62 models.” A useful estimate must name cases × repetitions × arms × expected generation length for each accepted work item, use comparable measured throughput, and include load/tool time. Separate cheap evidence/decision work from inference and from downloads.

## 5. Evidence and audit limits

The adjacent [machine-readable snapshot](MODEL_LANDSCAPE_AUDIT_20260906.evidence.json) records observed tag/layer mappings, measured totals, all old pending statuses and matched artifact paths, current non-bench configuration references, oMLX filesystem state, and hashes of key source files. It contains no model weights or credentials. It makes this audit reviewable after the active job advances.

The inspected primary store is `/Volumes/data01/ollama/models`, consistent with `.env.example`; the default `~/.ollama/models/manifests` directory was empty. No server query confirmed the active daemon's model directory or currently loaded models. No claims are made about other hosts, uninspected volumes, cloud caches, or actual request routing. Filesystem presence is not cryptographic verification of weights, successful loading, complete test coverage, or production acceptance.

The remaining appendices are generated from these read-only observations. Model IDs remain exact strings; context siblings and case differences are not silently merged for on-disk presence.

## Appendix A. All 62 historical pending entries

“Present” means exact manifest name in the inspected Ollama store. A citation proves an attempt was recorded, not that it succeeded or is fresh enough for promotion. `I` = investigate; `IR` = investigate-refresh; `K` = keep-open, all copied from the old ledger. Absent entries need a disposition reconciliation before any repull is considered. Present entries need an evidence/role decision before any rebench or cleanup.

| Tag | Present | Old verdict | Latest dated exact-tag attempt located | Current non-bench reference |
|---|---|---|---|---|
| `portal5/qwen3.6-27b-mtp:q8_0-drafted` | No | I | [mtp_probe_20260812T110332Z.json](../tests/benchmarks/results/mtp_probe_20260812T110332Z.json) | — |
| `qwen3.6:27b-q8_0` | No | IR | [reasoning_probe_20260812T114518Z.json](../tests/benchmarks/results/reasoning_probe_20260812T114518Z.json) | — |
| `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` | Yes | I | [reasoning_probe_20260813T234949Z.json](../tests/benchmarks/results/reasoning_probe_20260813T234949Z.json) | — |
| `qwen3.6:35b-a3b-q4_K_M` | No | IR | [reasoning_probe_20260812T114518Z.json](../tests/benchmarks/results/reasoning_probe_20260812T114518Z.json) | — |
| `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` | Yes | K | [bench_tps_20260814T014425Z.json](../tests/benchmarks/results/bench_tps_20260814T014425Z.json) | — |
| `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` | Yes | K | [reasoning_probe_20260813T234949Z.json](../tests/benchmarks/results/reasoning_probe_20260813T234949Z.json) | — |
| `hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K` | No | K | [security_exec_probe_20260811T202002Z.json](../tests/benchmarks/results/security_exec_probe_20260811T202002Z.json) | — |
| `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:Q4_K_M` | Yes | K | [refusal_preservation_probe_20260813T235101Z.json](../tests/benchmarks/results/refusal_preservation_probe_20260813T235101Z.json) | — |
| `portal5/xyz-aquila-mini:Q4_K_M` | No | K | [bench_tps_20260811T230905Z.json](../tests/benchmarks/results/bench_tps_20260811T230905Z.json) | — |
| `portal5/xyz-aquila-mini:q4_k_m-ctx16k` | Yes | K | [bench_tps_20260811T172511Z.json](../tests/benchmarks/results/bench_tps_20260811T172511Z.json) | `auto-research.model_hint` |
| `muse-glimmer:30b-mlx` | No | K | [vision_probe_20260812T125539Z.json](../tests/benchmarks/results/vision_probe_20260812T125539Z.json) | — |
| `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit:Q4_K_M` | No | K | [tool_use_probe_20260811T202017Z.json](../tests/benchmarks/results/tool_use_probe_20260811T202017Z.json) | — |
| `portal5/deepwen-3.6:q4.5-moq-ctx32k` | No | I | [cad_probe_20260813T140900Z.json](../tests/benchmarks/results/cad_probe_20260813T140900Z.json) | — |
| `portal5/deepwen-3.6:q4.5-moq` | No | I | [cad_probe_20260813T140900Z.json](../tests/benchmarks/results/cad_probe_20260813T140900Z.json) | — |
| `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf` | No | IR | [bench_tps_20260627T192858Z.json](../tests/benchmarks/results/bench_tps_20260627T192858Z.json) | — |
| `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` | No | IR | [reasoning_probe_20260812T114518Z.json](../tests/benchmarks/results/reasoning_probe_20260812T114518Z.json) | — |
| `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k` | Yes | I | [bench_tps_20260811T220820Z.json](../tests/benchmarks/results/bench_tps_20260811T220820Z.json) | — |
| `deepseek-r1:32b-q4_k_m` | Yes | IR | [reasoning_probe_20260812T114518Z.json](../tests/benchmarks/results/reasoning_probe_20260812T114518Z.json) | — |
| `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf` | No | K | [mtp_probe_20260812T110332Z.json](../tests/benchmarks/results/mtp_probe_20260812T110332Z.json) | — |
| `glm-4.7-flash:Q4_K_M` | Yes | I | [bench_tps_20260811T220820Z.json](../tests/benchmarks/results/bench_tps_20260811T220820Z.json) | — |
| `gemma4:31b-it-qat-ctx8k` | Yes | K | [bench_tps_20260814T032302Z.json](../tests/benchmarks/results/bench_tps_20260814T032302Z.json) | — |
| `gemma4:31b-it-qat` | Yes | K | [bench_tps_20260814T032302Z.json](../tests/benchmarks/results/bench_tps_20260814T032302Z.json) | — |
| `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` | Yes | IR | [bench_tps_gemma_mtp_20260701.json](../tests/benchmarks/results/bench_tps_gemma_mtp_20260701.json) | — |
| `gemma4:26b-a4b-it-q4_K_M` | Yes | K | [vision_probe_20260812T125539Z.json](../tests/benchmarks/results/vision_probe_20260812T125539Z.json) | — |
| `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M` | Yes | I | [mtp_probe_20260812T110332Z.json](../tests/benchmarks/results/mtp_probe_20260812T110332Z.json) | — |
| `qwen3.6:27b-mtp-q4_K_M` | No | K | [mtp_probe_20260812T110332Z.json](../tests/benchmarks/results/mtp_probe_20260812T110332Z.json) | — |
| `hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-heretic-GGUF:gemma-4-26B-A4B-it-uncensored-heretic.Q4_K_M.gguf` | Yes | K | [bench_tps_20260814T072743Z.json](../tests/benchmarks/results/bench_tps_20260814T072743Z.json) | — |
| `sylink/sylink:8b` | No | K | [long_context_probe_20260812T105740Z.json](../tests/benchmarks/results/long_context_probe_20260812T105740Z.json) | — |
| `sylink/sylink:8b-ctx8k` | No | I | [long_context_probe_20260812T105740Z.json](../tests/benchmarks/results/long_context_probe_20260812T105740Z.json) | — |
| `phi4:14b-q8_0` | No | K | [long_context_probe_20260812T105740Z.json](../tests/benchmarks/results/long_context_probe_20260812T105740Z.json) | — |
| `mistral-small3.2:24b` | Yes | K | [bench_tps_20260811T172511Z.json](../tests/benchmarks/results/bench_tps_20260811T172511Z.json) | `auto-security.variants.blueteam-council.council_models.1`; `auto-council.council.members.1.model` |
| `devstral-small-2:latest-ctx8k` | Yes | I | [bench_tps_20260811T220820Z.json](../tests/benchmarks/results/bench_tps_20260811T220820Z.json) | — |
| `devstral-small-2:latest` | Yes | I | [bench_tps_20260811T172511Z.json](../tests/benchmarks/results/bench_tps_20260811T172511Z.json) | — |
| `devstral:24b` | No | I | [bench_tps_20260811T220820Z.json](../tests/benchmarks/results/bench_tps_20260811T220820Z.json) | — |
| `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` | Yes | IR | [judgment_probe_v6_rescored_20260906T224306Z.json](../tests/benchmarks/results/judgment_probe_v6_rescored_20260906T224306Z.json) | — |
| `gpt-oss:20b` | Yes | IR | [reasoning_probe_20260812T114518Z.json](../tests/benchmarks/results/reasoning_probe_20260812T114518Z.json) | — |
| `huihui_ai/qwen3-abliterated:14b-v2` | Yes | I | [refusal_preservation_probe_20260811T200719Z.json](../tests/benchmarks/results/refusal_preservation_probe_20260811T200719Z.json) | — |
| `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0` | Yes | IR | [reasoning_probe_20260812T005010Z.json](../tests/benchmarks/results/reasoning_probe_20260812T005010Z.json) | `auto-security.variants.blueteam-orchestrated.expert_model`; `auto-security.variants.blueteam-council.expert_model` |
| `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M` | No | K | [vision_probe_20260812T125539Z.json](../tests/benchmarks/results/vision_probe_20260812T125539Z.json) | — |
| `portal5/gemma4-12b:q4_K_M-ctx8k` | No | I | [bench_tps_20260811T172511Z.json](../tests/benchmarks/results/bench_tps_20260811T172511Z.json) | — |
| `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M` | Yes | K | [mtp_probe_20260812T110332Z.json](../tests/benchmarks/results/mtp_probe_20260812T110332Z.json) | — |
| `hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF:Q4_K_M` | Yes | I | [reasoning_probe_20260813T234949Z.json](../tests/benchmarks/results/reasoning_probe_20260813T234949Z.json) | — |
| `gemma4:e4b-it-qat-ctx8k` | No | K | [vision_probe_20260812T125539Z.json](../tests/benchmarks/results/vision_probe_20260812T125539Z.json) | — |
| `gemma4:e4b-it-qat` | Yes | K | [vision_probe_20260812T125539Z.json](../tests/benchmarks/results/vision_probe_20260812T125539Z.json) | — |
| `meta-secalign-8b-q4_k_m:latest` | No | I | [bench_tps_20260811T172511Z.json](../tests/benchmarks/results/bench_tps_20260811T172511Z.json) | — |
| `dolphin-llama3:8b` | No | K | [tool_use_probe_20260811T202017Z.json](../tests/benchmarks/results/tool_use_probe_20260811T202017Z.json) | — |
| `hermes3:8b` | Yes | IR | [reasoning_probe_20260812T114518Z.json](../tests/benchmarks/results/reasoning_probe_20260812T114518Z.json) | — |
| `huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k` | No | K | [refusal_preservation_probe_20260811T200719Z.json](../tests/benchmarks/results/refusal_preservation_probe_20260811T200719Z.json) | — |
| `huihui_ai/gemma-4-abliterated:E2b-qat` | Yes | I | [refusal_preservation_probe_20260811T200719Z.json](../tests/benchmarks/results/refusal_preservation_probe_20260811T200719Z.json) | — |
| `hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M` | No | IR | [reasoning_probe_20260812T005010Z.json](../tests/benchmarks/results/reasoning_probe_20260812T005010Z.json) | — |
| `gemma4:e2b-it-qat-ctx8k` | No | K | [vision_probe_20260812T125539Z.json](../tests/benchmarks/results/vision_probe_20260812T125539Z.json) | — |
| `gemma4:e2b-it-qat` | Yes | K | [vision_probe_20260812T125539Z.json](../tests/benchmarks/results/vision_probe_20260812T125539Z.json) | — |
| `hf.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-4B-MTP-GGUF:Q4_K_M` | No | K | [mtp_probe_20260812T110332Z.json](../tests/benchmarks/results/mtp_probe_20260812T110332Z.json) | — |
| `llama3.2:3b-instruct-q8_0-ctx8k` | No | K | [bench_tps_20260811T172511Z.json](../tests/benchmarks/results/bench_tps_20260811T172511Z.json) | — |
| `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M` | No | K | [bench_tps_20260811T220820Z.json](../tests/benchmarks/results/bench_tps_20260811T220820Z.json) | — |
| `cybersecqwen-4b-toolfix:latest` | No | I | [security_exec_probe_20260811T202002Z.json](../tests/benchmarks/results/security_exec_probe_20260811T202002Z.json) | — |
| `llama3.2:3b` | No | K | [bench_tps_20260811T172511Z.json](../tests/benchmarks/results/bench_tps_20260811T172511Z.json) | — |
| `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF:latest` | Yes | K | [refusal_preservation_probe_20260811T200719Z.json](../tests/benchmarks/results/refusal_preservation_probe_20260811T200719Z.json) | — |
| `hf.co/Nguuma/security-slm-unsloth-1.5b:latest` | Yes | IR | [reasoning_probe_20260812T114518Z.json](../tests/benchmarks/results/reasoning_probe_20260812T114518Z.json) | — |
| `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M` | No | I | [bench_tps_20260811T172511Z.json](../tests/benchmarks/results/bench_tps_20260811T172511Z.json) | — |
| `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M` | No | I | [bench_tps_20260811T172511Z.json](../tests/benchmarks/results/bench_tps_20260811T172511Z.json) | — |
| `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M` | No | I | [bench_tps_20260811T172511Z.json](../tests/benchmarks/results/bench_tps_20260811T172511Z.json) | — |

## Appendix B. September 6 rescored judgment results

All rows below are from the same saved rescored file; rates are fractions. No production decision is inferred. These are 30 short judgment cases per model, not long-context or tool-chain acceptance.

| Model | Exact accuracy | F2 violation | False supported | Median t/s | Errors |
|---|---:|---:|---:|---:|---:|
| `command-r:35b-08-2024-q4_K_M` | 0.8 | 0.75 | 4 | 12.4 | 0 |
| `granite4.1:30b-ctx16k` | 0.8 | 0.8434 | 2 | 13.2 | 0 |
| `granite4.2:30b-q4_K_M` | 0.8 | 0.6962 | 3 | 13.2 | 0 |
| `granite4.2:3b-q8_0` | 0.4333 | 0.5128 | 8 | 57.1 | 0 |
| `granite4.2:8b-q8_0` | 0.5667 | 0.7647 | 4 | 26.1 | 0 |
| `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:q4_K_M-ctx8k` | 0.6333 | 0.8523 | 2 | 53.9 | 0 |
| `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` | 0.6 | 0.4 | 3 | 49.4 | 0 |
| `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k` | 0.8333 | 0.8537 | 3 | 45.8 | 0 |
| `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | 0.9 | 0.9524 | 1 | 12.5 | 0 |
| `mistral-small3.2:24b-instruct-2506-q4_K_M` | 0.8333 | 0.8025 | 3 | 16.8 | 0 |
| `phi4:14b-q4_K_M` | 0.0 | 0.0 | 17 | n/a | 30 |
| `qwen3.6:27b-q4_K_M-ctx16k` | 0.9 | 0.9524 | 1 | 12.7 | 0 |

## Appendix C. Installed tags absent from the old full cleanup report

These 41 exact names need inclusion in a refreshed inventory. “Outside the old report” does not mean newly downloaded, never tested, unused, or safe to remove. Different spellings/aliases can share weights. Per-tag GiB is logical referenced size and must not be summed without digest deduplication. The structured scan is bounded as described above; OCR/media/UAT evidence outside it may exist.

| Tag | Logical GiB | Non-bench config reference | Latest dated exact-tag attempt located by bounded scan |
|---|---:|---|---|
| `baronllm:q6_k` | 6.143 | — | [bench_tps_20260621T030634Z.json](../tests/benchmarks/results/bench_tps_20260621T030634Z.json) |
| `bully-ae9fa52b558fbce0:latest` | 0.098 | — | Not established by this scan |
| `bully-bcb0e4b867519350:latest` | 0.098 | — | Not established by this scan |
| `command-r:35b-08-2024-q4_K_M` | 18.441 | — | [judgment_probe_v6_rescored_20260906T224306Z.json](../tests/benchmarks/results/judgment_probe_v6_rescored_20260906T224306Z.json) |
| `deepseek-ocr:latest` | 6.228 | — | Not established by this scan |
| `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx24k` | 20.552 | `auto-security.variants.pentest.model_hint` | Not established by this scan |
| `gemma3:4b-it-q4_K_M` | 3.110 | — | Not established by this scan |
| `glm-ocr:Q8_0` | 1.479 | — | Not established by this scan |
| `granite3.2-vision:2b` | 2.270 | — | Not established by this scan |
| `granite4.2:30b-q4_K_M` | 16.504 | — | [judgment_probe_v6_rescored_20260906T224306Z.json](../tests/benchmarks/results/judgment_probe_v6_rescored_20260906T224306Z.json) |
| `granite4.2:30b-q8_0` | 28.975 | — | [judgment_probe_v6_20260906T210112Z.json](../tests/benchmarks/results/judgment_probe_v6_20260906T210112Z.json) |
| `granite4.2:3b-q8_0` | 3.625 | — | [judgment_probe_v6_rescored_20260906T224306Z.json](../tests/benchmarks/results/judgment_probe_v6_rescored_20260906T224306Z.json) |
| `granite4.2:8b-q8_0` | 8.704 | — | [judgment_probe_v6_rescored_20260906T224306Z.json](../tests/benchmarks/results/judgment_probe_v6_rescored_20260906T224306Z.json) |
| `hf.co/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4_K_M` | 20.551 | — | [BENCH_REPAIR_CHECKPOINT_066355de23d5.json](../tests/benchmarks/results/BENCH_REPAIR_CHECKPOINT_066355de23d5.json) |
| `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:q4_K_M-ctx8k` | 23.728 | `auto-nemotron.model_hint` | [judgment_probe_v6_rescored_20260906T224306Z.json](../tests/benchmarks/results/judgment_probe_v6_rescored_20260906T224306Z.json) |
| `hf.co/ggml-org/dots.ocr-GGUF:Q8_0` | 3.016 | — | Not established by this scan |
| `hf.co/mradermacher/Nanonets-OCR2-3B-GGUF:Q4_K_M` | 2.587 | — | Not established by this scan |
| `hf.co/mradermacher/Ornith-1.5-35B-A3B-Uncensored-GGUF:Q4_K_M` | 20.794 | — | [BENCH_REPAIR_CHECKPOINT_066355de23d5.json](../tests/benchmarks/results/BENCH_REPAIR_CHECKPOINT_066355de23d5.json) |
| `hf.co/mradermacher/gemma-4-26B-A4B-it-heretic-GGUF:Q4_K_M` | 15.643 | — | [BENCH_REPAIR_CHECKPOINT_066355de23d5.json](../tests/benchmarks/results/BENCH_REPAIR_CHECKPOINT_066355de23d5.json) |
| `hf.co/mradermacher/gemma-4-26B-A4B-it-heretic-GGUF:q4_k_m-ctx16k` | 15.643 | — | Not established by this scan |
| `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx32k` | 21.666 | `auto-data.model_hint` | [judgment_probe_v6_rescored_20260906T224306Z.json](../tests/benchmarks/results/judgment_probe_v6_rescored_20260906T224306Z.json) |
| `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` | 16.796 | — | [bench_tps_20260814T152030Z.json](../tests/benchmarks/results/bench_tps_20260814T152030Z.json) |
| `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | 16.796 | `auto-reasoning.variants.deep.model_hint`; `auto-compliance.model_hint` | [judgment_probe_v6_rescored_20260906T224306Z.json](../tests/benchmarks/results/judgment_probe_v6_rescored_20260906T224306Z.json) |
| `minicpm-v4.5:Q4_K_M` | 5.701 | — | Not established by this scan |
| `minicpm-v:8b-2.6-q4_K_M` | 5.332 | — | Not established by this scan |
| `mistral-small3.2:24b-instruct-2506-q4_K_M` | 14.135 | — | [judgment_probe_v6_rescored_20260906T224306Z.json](../tests/benchmarks/results/judgment_probe_v6_rescored_20260906T224306Z.json) |
| `orcarouter/Qwen3.8-27B-Uncensored:Q4_K_M` | 16.523 | — | Not established by this scan |
| `phi4:14b-q4_K_M` | 8.431 | — | [judgment_probe_v6_rescored_20260906T224306Z.json](../tests/benchmarks/results/judgment_probe_v6_rescored_20260906T224306Z.json) |
| `portal5/agentworld-35b:ud-q4_K_XL-ctx256k` | 20.792 | `auto-coding.variants.lite.model_hint` | Not established by this scan |
| `portal5/cadmium:Q4_K_M` | 1.797 | — | Not established by this scan |
| `portal5/gemma4-26b-heretic:q4_K_M-ctx256k` | 15.643 | `auto-uncensored-throwaway.variants.gemma4-heretic.model_hint` | Not established by this scan |
| `portal5/hauhaucs-qwen36-35b:q4_K_M-ctx256k` | 20.551 | `auto-uncensored-throwaway.model_hint` | Not established by this scan |
| `portal5/laguna-xs2:q4_K_M-ctx128k` | 21.512 | `auto-coding.variants.laguna.model_hint` | Not established by this scan |
| `portal5/omnicoder2-9b:q4_K_M-ctx256k` | 5.243 | `auto-coding.variants.uncensored.model_hint` | Not established by this scan |
| `portal5/ornith15-35b:q4_K_M-ctx256k` | 20.794 | `auto-uncensored-throwaway.variants.ornith15.model_hint` | Not established by this scan |
| `portal5/qwen3-coder-next-abliterated:q4_K_M-ctx256k` | 45.222 | `auto-coding.variants.uncensored-agentic.model_hint` | Not established by this scan |
| `portal5/qwen3-coder-next:latest-ctx256k` | 48.188 | `auto-coding.variants.heavy.model_hint` | Not established by this scan |
| `qwen3-coder:30b-a3b-q4_K_M-ctx256k` | 17.282 | `auto-coding.model_hint` | Not established by this scan |
| `qwen3-vl:2b-instruct-q4_K_M` | 1.760 | — | Not established by this scan |
| `qwen3-vl:4b-instruct-q4_K_M` | 3.069 | — | Not established by this scan |
| `qwen3-vl:8b-instruct-q4_K_M` | 5.719 | — | Not established by this scan |

## Appendix D. oMLX filesystem state

Sizes follow symlinks and deduplicate files within each model directory. Presence only; no loading or inference was attempted.

| Directory | Logical GiB | Filesystem state |
|---|---:|---|
| `DeepSeek-R1-0528-Qwen3-8B-4bit` | 4.302 | Populated symlink target |
| `Laguna-XS.2-4bit` | 17.536 | Local directory |
| `MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-8bit` | 0.000 | Dangling symlink |
| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp` | 20.312 | Local directory |
| `Qwen3-Coder-30B-A3B-Instruct-4bit` | 16.016 | Local directory |
| `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit` | 18.193 | Populated symlink target |
| `Qwen3.8-27B-4bit` | 14.977 | Populated symlink target |
| `Qwen3.8-27B-DFlash2` | 3.585 | Populated symlink target |
| `Qwen3.8-27B-oQ4e-mtp` | 15.828 | Local directory |
| `Qwen3.8-Flash-Next-REAP-288-MLX-4bit` | 68.467 | Local directory |
| `SuperQwen3.8-27b-abliterated-MLX-4bit` | 0.000 | Dangling symlink |
| `Tongyi-DeepResearch-30B-A3B-abliterated-4bit` | 16.016 | Populated symlink target |
| `VulnLLM-R-7B-4bit` | 4.005 | Populated symlink target |
| `gemma-4-26b-a4b-it-QAT-4bit` | 14.567 | Populated symlink target |
| `granite-4.1-30b-4bit` | 16.810 | Populated symlink target |
| `granite-4.1-8b-mxfp8` | 8.451 | Populated symlink target |
| `huihui-ai--Huihui-Qwen3.5-9B-abliterated-mlx-4bit` | 4.711 | Populated symlink target |
