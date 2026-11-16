# Fleet review — 2026-11-13

## Decision

There is not enough current, role-matched evidence or usage telemetry to justify deleting a distinct model family. Keep the configured fleet in place while screening the uncertain seats below. The only low-risk simplification visible from source is removing the duplicate `auto-daily::nemotron` selector; it would save **0 bytes and 0 MB resident** because it names the same tag as the default. Treat it as a UI cleanup candidate only, after confirming the selector is not part of an operator workflow.

The stronger efficiency opportunity is to stop treating repeated aliases as separate weights. Three auto-coding selectors resolve to the same oMLX Qwen3.8 MTP checkpoint; compliance Qwen3.8 currently resolves there too, despite the approved matrix requiring plain 4-bit for the JSON council row. Resolve that mismatch in the approved engine evaluation before any seat edit. Context, prompts, role diversity, and fallbacks remain separate until their own screens close.

No workspace or variant was removed or repointed in this lane.

## Scope and route interpretation

This review covers **22 workspaces and 75 populated `(workspace, variant)` model-hint slots** from `config/portal.yaml`. Two `auto-security` variants (`blueteam-orchestrated` and `blueteam-council`) have no `model_hint`; their separately configured tool, reasoning, council, and expert roles are described under the security rows and council inventory below. Wiki fact-unit tools were unavailable in this session, so the review used the named repository documents/configuration and the route-selection source directly.

Routes below are the **configured preferred path**, derived from `config/backends.yaml:workspace_routing`, its backend priorities/aliases, and `portal/platform/inference/cluster_backends.py`. An `o*` route names the preferred oMLX backend and resolved checkpoint. A direct Ollama candidate is listed as a fallback only when the workspace's ordered groups also resolve that hint. `Ollama <group>` means the configured Ollama backend resolves the hint directly. This is not a live observation: the worker contract bars live Portal calls, and `Backend.resolve_model()` can skip an alias when the oMLX server's live model list omits it.

`SCREEN` means keep the incumbent and run a named, real-use screen before changing it. It does not mean remove it. `KEEP` means the on-file role evidence supports the present seat. `CONSOLIDATE-CANDIDATE` and `TRIM-CANDIDATE` are selectors/registrations only unless the savings table says otherwise. Engine-dependent rows wait on the corresponding approved row in `docs/ENGINE_EVAL_MATRIX_20261113.md`.

For evidence dated before 2026-10-13, I mark it **pre-instrument-fix**. Evidence after that date but before the 2026-11-13 engine Stage 0 is marked **pre-Stage-0**. The 2026-11-07 Model Seat Process closures are called out separately: they already set the default action for those named seat questions.

### Evidence key

| Key | Source and measured result | Scope limit |
|---|---|---|
| E1 | `$PORTAL_DATA_ROOT/tests/wfe/results/campaigns/realuse_s5s7s10_20261030b/report.json` (generated 2026-11-01): auto-coding Qwen3.8 15/16 vs Qwen3-Coder 5/16; 11 wins, 0 losses, 5 ties; challenger better. **Post-10/13 audit, pre-Stage-0.** | Broad coding task set; does not settle engine choice, long context, uncensored, CAD, or every variant. |
| E2 | `$PORTAL_DATA_ROOT/tests/wfe/results/campaigns/realuse_mellum_20261104/report.json` (generated 2026-11-05): Kat fast-repair 27/32 vs Mellum 15/32; incumbent better (4W/15L/13T). **Post-audit, pre-Stage-0.** | Supports Kat over this challenger, not every coding specialist. |
| E3 | `$PORTAL_DATA_ROOT/tests/wfe/results/campaigns/realuse_autodaily_postfix_20261106/report.json`: Gemma QAT 26/28, Nemotron 28/28, Qwen3.8 27/28; both challengers not separated at this sample. Median wall times 64.8s, 73.0s, 94.5s, respectively. **Post-audit, pre-Stage-0.** | No quality winner; campaign does not prove which daily engine should serve. |
| E4 | `docs/WFE_DECISION_AUTO_MATH_20261018.md`: Qwen3.8 107/108, GLM-4.7-Flash 104/108, DeepSeek 105/108, Phi-4 Mini 93/108; each challenger separated from Phi-4, but not compared pairwise. **Post-audit, pre-Stage-0.** | Does not establish GLM vs Qwen3.8 or the best live math seat. |
| E5 | `docs/DECISION_AUTO_REASONING_K2_20261019.md` and `docs/WFE_FITNESS_REPORT_wfe_reasoning_hard_20261019b.md`: K2 12/12 (28s median), DeepSeek-R1 8/12 (383s), GLM 10/12 (248s), with a 13/13 K2 stability set. **Post-audit, pre-Stage-0.** | Small, scoped hard-reasoning set; not a general reasoning comparison. |
| E6 | `docs/WFE_DECISION_AUTO_DATA_CFIX_20261016.md`: guarded Qwen3.6 data path 106/108, zero zero-call rows; 12/12 live sales replay. **Post-audit, pre-Stage-0.** | Evidence covers the repaired data/tool-call path, not general research. |
| E7 | `docs/WFE_DECISION_AUTO_COMPLIANCE_CFIX_20261016.md`: exploratory guided screen Qwen3.8 10/11 vs Granite 2/11; no confirm or closed fitness decision. **Post-audit, pre-Stage-0.** | Screen only; looping/tool-call issues remain bounded, not qualified away. |
| E8 | `docs/WFE_DECISION_AUTO_DOCUMENTS_20261017.md` and `docs/GEMMA26B_QAT_CONSOLIDATION_20261106.md`: plain Gemma and Qwen3.8 tied 108/108, Gemma median 3.7s vs Qwen 20.3s; same-engine QAT/plain comparison 30/32 vs 31/32, not separated. **Post-audit, pre-Stage-0.** QAT selected for the 32k documents seat on 2026-11-06. | Separate from 128k compliance reading. |
| E9 | `docs/WFE_DECISION_AUTO_RESEARCH_NEX25_20261018.md`: Nex-N2-mini 103/108 vs Nex-N2.5-mini 87/87 curtailed; 2W/0L/27T, not separated; 4.5s vs 5.7s medians; operator kept N2-mini. **Post-audit, pre-Stage-0.** `docs/MODEL_INTAKE_FRESHNESS_20261113.md` reopened N2.5-mini screening. | Reopened challenger screen is not complete; N2.6 Q4 build is outside the ≤40 GB intake envelope. |
| E10 | `docs/WFE_DECISION_TOOLS_SPECIALIST_20261019.md`: Qwen3.6 76/87, Granite 96/108, Qwen3.8 76/78; not separated. Operator chose Qwen3.6 by lane intent at p90 17.6s vs 339s, without extra memory. **Post-audit, pre-Stage-0.** | Keep the selected tool seat; do not infer equivalent performance in other roles. |
| E11 | `config/portal.yaml` Gate C notes and `docs/MODEL_SEAT_PROCESS.md` (closed 2026-11-07): gemma-fast 6/6 test-fixing bites; Spark shadow is 76 generated-fixture rows and a `Finding:` format check, so it remains unproven and passive. | Gate C supports the fast seat; the Spark result is not real-use quality evidence. |
| E12 | `docs/DECISION_AUTO_COUNCIL_MOE_20261019.md` and its rubric follow-up: 20 fixed cases, Gemma QAT 12/20 correct and 16/20 key issue at 26s median vs old dense roster 12/20 and 16/20 at 225s; rubric v2 13/20, 4/5 clear support, 3/5 clear reject. **Pre-Stage-0.** | Same-model self-consistency result; not a multi-lineage diversity trial. |
| E13 | `docs/MODEL_SEAT_PROCESS.md` (closed 2026-11-07): plain Gemma and QAT tied on four real-corpus OWUI reading questions with full 20–38k documents; blind judges split, so keep plain. The separate vision fallback A/B tied on three live image tasks; keep plain. | Does not qualify the current Qwen3-VL or Gemma-31B vision variants. |
| E14 | `docs/ENGINE_EVAL_MATRIX_20261113.md` and `docs/ENGINE_H2H_RESULTS_20261113.md`: approved Stage 0/1/2 engine questions; H2H results are direct-engine throughput only, without production routes, co-residency, long-context, tools, or quality. | H2H speed is not a seat decision. Matrix path is authoritative for engine-dependent rows. |
| E15 | `docs/WFE_INSTRUMENT_AUDIT_20261013.md` and `docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md`: historical WFE instrument defects; WFE closeout/removals remain held pending completion and reissued v4. | Review flags uncertainty; it does not authorize removal. |
| E16 | `docs/MODEL_FLEET_CLOSEOUT_20260906.CLOSEOUT.md` §11 and `config/MODEL_CATALOG.md`: E4B QAT ctx8k corrected to INTEGRATED for tools-specialist fast; 2026-09-11 WFE measured 9/9 home:coding and 9/9 discovery:research vs Granite 6/9 and 9/9 (small n, not separated). | An earlier historical-absent row is not a current disposition. |
| E17 | `docs/MODEL_INTAKE_FRESHNESS_20261111.md` and `docs/MODEL_INTAKE_FRESHNESS_20261113.md`: dated candidate freshness only; no promotion evidence for current seats. | A newer model/card/quant is a screen candidate, not proof of role coverage. |
| E18 | `$PORTAL_DATA_ROOT/reports/model_cleanup_audit.md` (snapshot mtime 2026-11-13 12:23): 57 integrated, 5 retained, 155 removed-closed; two physical-store exceptions listed; 0 config drift. | Existing report only; this lane did not run its live Ollama audit command. Its exceptions conflict with current source or later reopening and are not deletion instructions. |

## Usage evidence

No current workspace/variant request-usage telemetry was found. `PORTAL_DATA_ROOT` was unset in the worker shell; I inspected the local artifact root `/Users/chris/AI_Output/portal-data` and the repository. The repo contains metric code, a dashboard definition, and router test fixtures. The data root contains WFE result campaigns, `router_bench_20261019.json` (four benchmark results), June router-condition benchmarks, and archived private compliance `live_routes.json` (2026-09-06) / `routed_observations.json` (2026-09-15). These are benchmarks, WFE outcomes, or scoped evaluation receipts; none is current production request-frequency telemetry by workspace/variant. Therefore no slot is classified unused based on actual request counts.

## Slot review

The engine column names the route that source configuration prefers; “fallback” is the directly registered Ollama tag when one exists. “Coverage” means a plausible already-seated overlap only, never equivalence without a matched role screen. `CAT` points to the model's entry in `config/MODEL_CATALOG.md`; where a row says “no matched result,” registration, load/tool probes, or public benchmark claims are not being promoted to seat-quality evidence.

### `auto` — specialist routing seed

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | security group → oMLX-security alias `Huihui-Qwen3.5-9B-abliterated-MLX-4bit`; Ollama fallback | Seeds a broad specialist router. No current route-level quality/traffic evidence found; security, coding, and general seats are plausible coverage, but actual model selection per request needs route receipts. | **SCREEN** — verify real route and selection on actual requests. |

### `auto-general-uncensored` — uncensored general conversation

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Huihui-Qwen3.6-35B-A3B-abliterated GGUF Q4_K_M-ctx8k` | Ollama general direct | General uncensored conversation. Fleet closeout 2026-09-07 records refusal-preservation 1.0 vs 0.75 for incumbent, but that refusal probe is **pre-instrument-fix, pre-Stage-0** and does not cover current long-context/tool quality. | **SCREEN** — newer Qwen3.8/general seats are plausible, not proven uncensored replacements. |
| throwaway · `HauhauCS Qwen3.6-35B ctx256k` | Ollama general direct | Throwaway open-topic alternative; no matched quality result found. | **SCREEN** — does not replace an uncensored or 256k role without a task-matched A/B. |
| throwaway-gemma4-heretic · `Gemma4-26B-Heretic ctx256k` | Ollama general direct | Throwaway Gemma lineage alternative; no matched quality result found. | **SCREEN** — Gemma QAT is plausible but not equivalent to this fine-tune. |
| throwaway-ornith15 · `Ornith15-35B ctx256k` | Ollama general direct | Throwaway model-family alternative; no matched quality result found. | **SCREEN** — no already-seated equivalent demonstrated. |
| creative · `HauhauCS Qwen3.6 aggressive ctx8k` | Ollama general direct (workspace routes only `general`; creative-group MLX alias is not in this path) | Creative/open-topic generation; no matched result found. | **SCREEN** — other Qwen seats do not prove this prompt/intent. |

### `auto-daily` — everyday assistant and speed choices

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Nemotron 3.5 Lightning 30B-A3B Q4_K_M-ctx32k` | Ollama general direct; this is Stage 0 `daily-moe` | Everyday default. E3 has 28/28 vs Gemma QAT 26/28 and Qwen3.8 27/28, but both challengers were not separated and Nemotron was slower than Gemma in that WFE set. E14 makes engine/co-residency the pending decision. | **ENGINE-EVAL-DEPENDENT** — wait for “Daily MoE”; current GGUF is Stage 0 incumbent. |
| gemma-fast · `Gemma-4-26B QAT ctx32k` | oMLX-general alias `gemma-4-26b-a4b-it-QAT-4bit`; Ollama fallback | Fast reasoning/arm seat. E11 Gate C 6/6 supports its seated role; Model Seat Process closed the Spark shadow as unproven. | **ENGINE-EVAL-DEPENDENT** — wait for “Hunt parallel” shared-QAT engine row; keep incumbent if unproven. |
| fast · `Qwen3.6-35B-A3B UD-Q4_K_XL ctx96k` | oMLX-general alias `unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit`; Ollama fallback | Faster daily option. The 10/30b WFE set compared daily Qwen3.6 11/30 with Qwen3.8 12/30, not separated; Qwen3.8 was slower (71.6s vs 22.6s median). **Pre-Stage-0.** | **SCREEN** — no measured daily winner; Qwen3.8 does not show speed coverage. |
| deep · `Qwen3.8-27B GGUF Q4_K_M ctx96k` | oMLX-general alias `Qwen3.8-27B-oQ4e-mtp`; Ollama fallback | Deliberate deeper option. E3 includes a different Qwen3.8 arm, but does not qualify this variant's deep-role quality. | **SCREEN** — dense-coding engine results do not transfer to daily deep work. |
| nemotron · same `Nemotron 3.5 Lightning ... ctx32k` hint as default | Ollama general direct | Duplicate named selector for the exact default tag and same workspace; no unique checkpoint or role evidence. | **TRIM-CANDIDATE** — drop only the duplicate selector after confirming no UI/workflow dependency; 0 bytes/0 MB resident saved. |

### `auto-coding` — coding and specialist alternatives

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Qwen3.8-27B GGUF Q4_K_M ctx96k` | oMLX-general alias `Qwen3.8-27B-oQ4e-mtp`; Ollama fallback | Broad code generation/debugging. E1: Qwen3.8 15/16 vs Qwen3-Coder 5/16, 11W/0L/5T; **post-audit, pre-Stage-0**. The decision is now gated by E14. | **ENGINE-EVAL-DEPENDENT** — wait for “Dense coding, with its speed lever”; it evaluates which engine can keep the quality at lower latency. |
| laguna · `Laguna XS-2.1 Q4_K_M ctx128k` | oMLX-coding alias `Laguna-XS-2.1-4bit`; Ollama fallback | Agentic coding with long context. Fleet closeout §10 (2026-09-25) reports 29/42, including 9/9 coding, but is **pre-instrument-fix, pre-Stage-0** and notes loop behavior under card sampling. | **SCREEN** — Qwen3.8 is plausible for broad coding, not proven for 128k agentic work. |
| northmini · `North-Mini-Code-1.0 QAD NVFP4 ctx8k` | Ollama coding direct | Compact coding variant; no role-matched result found. | **SCREEN** — broad Qwen3.8 may cover ordinary coding only. |
| uncensored · `OmniCoder2-9B Q4_K_M ctx256k` | Ollama coding direct | Small uncensored coding. Catalog/closeout preserve the narrow lane and many persona pins; no current variant WFE found. | **SCREEN** — do not fold into plain Qwen coding without uncensored 256k tasks. |
| uncensored-agentic · `Huihui Qwen3.6-27B abliterated MLX 4bit` | oMLX-coding direct | Uncensored agentic coding; catalog documents 2026-10-22 think-off A/B selection but no post-Stage-0 role screen. | **SCREEN** — newer Qwen3.8 is not an uncensored equivalent. |
| fast-repair · `Kat-Coder v2.5-dev Q4_K_M ctx32k` | Ollama coding direct | Fast repair. E2: Kat 27/32 vs Mellum 15/32, incumbent better. **Post-audit, pre-Stage-0.** | **KEEP** — newer Mellum screen lost; keep Kat pending real-use confirmation. |
| heavy · `Qwen3.8-27B-oQ4e-mtp` | oMLX-coding direct | High-effort coding alias to the same MTP checkpoint as default. E1 supports the Qwen3.8 family on coding; E14's dense-coding row decides engine/speed. | **ENGINE-EVAL-DEPENDENT** — retain separate heavy-role settings until that row and role parity are proved. |
| lite · `AgentWorld-35B UD-Q4_K_XL ctx256k` | Ollama coding direct | Long-context lighter coding alternative. E1 campaign reported 11/16, not separated against Qwen3.8. **Pre-Stage-0.** | **SCREEN** — no quality or memory advantage is proved for the specific 256k role. |
| ornith · `Ornith-1.0-35B Q4_K_M ctx64k` | Ollama coding direct | Agentic coding candidate; no current role-matched result found. | **SCREEN** — no evidence-backed coverage from Qwen3.8 yet. |
| cad · `Qwen3-Coder-30B-A3B Q4_K_M ctx32k` | oMLX-coding alias `Qwen3-Coder-30B-A3B-Instruct-4bit`; Ollama fallback | CAD/coding tool path; no completed role-specific CAD comparison found in reviewed docs. | **SCREEN** — keep its context and `generate_scad` task surface until tested against Qwen3.8. |
| bigfix · same Qwen3-Coder weights, ctx16k | oMLX-coding alias `Qwen3-Coder-30B-A3B-Instruct-4bit`; Ollama fallback | Short-context big-fix coding. No role-specific evidence found. | **SCREEN** — ctx16k and ctx32k tags share weights, but the smaller window is a safety/fit choice, not a duplicate to repoint blindly. |
| devstral_coder · `Devstral Small 2 latest ctx8k` | Ollama coding direct | Small code-generation alternative; no matching result found. | **SCREEN** — Qwen3.8 is plausible broad coverage only. |
| gemma4-heretic-coder · `Gemma4-26B-Heretic ctx256k` | Ollama coding direct | Fine-tuned long-context coding alternative; no matching result found. | **SCREEN** — Gemma QAT does not establish heretic-model equivalence. |
| glm-coder · `GLM-4.7-Flash Q4_K_M ctx64k agentic` | Ollama coding direct | Agentic coding; the math WFE E4 does not measure coding. No coding result found for this exact seat. | **SCREEN** — Qwen3.8 is plausible overlap, not proven. |
| hauhaucs-coder · `HauhauCS Qwen3.6-35B ctx256k` | Ollama coding direct | Uncensored long-context coding; no current task-matched WFE found. | **SCREEN** — keep this separate from plain code coverage. |
| ornith15-coder · `Ornith15-35B ctx256k` | Ollama coding direct | Long-context code exploration; no role-matched result found. | **SCREEN** — no seated equivalent established. |
| qwen38coder · `Qwen3.8-27B GGUF Q4_K_M` (no baked context suffix) | oMLX-coding alias `Qwen3.8-27B-oQ4e-mtp`; Ollama fallback | General Qwen3.8 coding selector; same preferred oMLX checkpoint as default/heavy. | **CONSOLIDATE-CANDIDATE** — target `auto-coding::default` / `Qwen3.8-27B-oQ4e-mtp`; merge the selector only if context and persona settings prove redundant. 0 bytes/0 MB resident saved because the alias already targets the same checkpoint. Wait for dense-coding row. |
| qwen38coder-dflash · `Qwen3.8-27B-4bit` + DFlash2 | oMLX-coding direct `Qwen3.8-27B-4bit` (DFlash2 drafter configured on host) | Speculative-decoding speed option; no GGUF fallback for this exact arm. E14 names this exact checkpoint/drafter and excludes Splash plain because its draft cannot be disabled. | **ENGINE-EVAL-DEPENDENT** — wait for “Dense coding, with its speed lever”; do not substitute a drafter. |

### `auto-spl` — Splunk/detection writing

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Qwen3.8-27B-oQ4e-mtp` | oMLX-coding direct | SPL/YARA and detection writing. E1/E4 do not measure SPL. The October seat prior found no exact-variant SPL/YARA score; `docs/WFE_SEAT_PRIOR_20261018.md` is explicit that general coding benchmarks are proxies only. **Pre-Stage-0.** | **SCREEN** — run exact SPL/YARA tasks; Qwen coding lead is not SPL coverage. |
| nano · `OrcaCyber Nano 1.0 ctx64k` | Ollama coding direct | Compact SPL/detection option. Catalog records 2026-10-23 screen 8/8 vs incumbent 6/8; **post-audit, pre-Stage-0**. | **SCREEN** — keep as a promising, distinct lightweight option and reconfirm with Stage-0-valid real tasks. |

### `auto-security` — security, red/blue/purple and council seats

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `VulnLLM-R-7B Q4_K_M ctx8k` | Ollama security direct; oMLX-security alias exists as fallback candidate | Defensive vulnerability analysis. `TASK_SEAT_VENDOR_FIT_V1.md` (2026-09-25) measured the trained `scan_code` contract at 17/18, 0/3 false positives; the 10/30 real-use security WFE was sparse (0/12 on this chat seat). These are different contracts. **Pre-Stage-0.** | **SCREEN** — keep until a matched CVE/CWE chat or tool-path screen separates model from prompt/tool contract. |
| uncensored · `BaronLLM abliterated ctx8k` | Ollama security direct | Uncensored security conversation; no current role-matched result found. | **SCREEN** — no seated general security model proves uncensored coverage. |
| pentest · `HauhauCS Qwen3.6 aggressive ctx24k` | oMLX-security alias `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit`; no direct Ollama model is registered in this workspace's candidate groups | Offensive/pentest reasoning; no current matched WFE result found for this variant. | **SCREEN** — preserve a distinct offensive role; confirm the out-of-route Ollama creative registration is not assumed to be a fallback. |
| blueteam · `Granite 4.1 8B ctx8k` | Ollama security direct | Defensive blue-team seat. 10/30b security WFE was only 5 rows with an excluded row; no decision-grade result. Tool-call evidence is in catalog, not quality evidence. **Pre-Stage-0.** | **SCREEN** — Granite is also used by reviewer/tool roles, but shared lineage does not prove the blue task. |
| redteam · `Qwen3.5 abliterated 9B ctx8k` | oMLX-security alias `Huihui-Qwen3.5-9B-abliterated-MLX-4bit`; Ollama fallback | Red-team generation. No current exact role-quality result found. | **SCREEN** — preserve the Qwen lineage while red-team evidence is absent. |
| redteam-deep · `SuperGemma4-26B uncensored ctx64k` | oMLX-security alias `Jiunsong--supergemma4-26b-uncensored-mlx-4bit-v2`; Ollama fallback | Deep red-team generation. 2026-09-25 alias probe showed matching reasoning-channel structure and typed calls, not task quality. **Pre-instrument-fix, pre-Stage-0.** | **SCREEN** — retain Gemma-family diversity; no seated Qwen or Granite result covers this role. |
| purpleteam · `Qwen3.5 abliterated 9B ctx8k` | oMLX-security alias `Huihui-Qwen3.5-9B-abliterated-MLX-4bit`; Ollama fallback | Purple-team planning, distinct from the red-team prompt/role. No exact role screen found. | **SCREEN** — keep separate role identity and Qwen lineage. |
| purpleteam-deep · same Qwen3.5 abliterated 9B, ctx64k | oMLX-security alias `Huihui-Qwen3.5-9B-abliterated-MLX-4bit`; Ollama fallback | Long-context purple-team analysis. No exact role screen found. | **SCREEN** — context is a real distinction; no evidence for consolidation. |
| purpleteam-exec · `SuperGemma4-26B uncensored ctx64k` | oMLX-security alias `Jiunsong--supergemma4-26b-uncensored-mlx-4bit-v2`; Ollama fallback | Purple execution role. Same 2026-09-25 behavioral/tool alias probe as redteam-deep, not quality; **pre-instrument-fix, pre-Stage-0**. | **SCREEN** — keep SuperGemma as a second family alongside Qwen, Granite, and other council members. |
| security-council-qwen36-27b · `Qwen3.6-27B Q4_K_M ctx4k` | Ollama security direct | Council analyst seat; catalog records a context-baked tag correction on 2026-10-15, not a council quality decision. | **SCREEN** — keep this Qwen-family member to preserve independent council lineage pending the council holdout. |
| bully-handoff-drafter · `Granite 4.1 30B ctx16k` | oMLX-general alias `granite-4.1-30b-4bit`; Ollama fallback | Drafts analyst handoff; no role-specific quality result found. | **SCREEN** — plausible overlap with Granite council, but the drafting contract is distinct. |
| security-tool-granite41-8b · `Granite 4.1 8B ctx8k` | Ollama security direct | Tool model in blue orchestration/council. Catalog has tool-call probe only; no role score found. | **SCREEN** — shared with `security-reviewer` and blueteam, but preserve its independent tool role. |
| security-council-granite41-30b · `Granite 4.1 30B ctx16k` | oMLX-general alias `granite-4.1-30b-4bit`; Ollama fallback | Blue council/reasoning member; no new task result found. | **SCREEN** — preserve Granite lineage in the blue roster. |
| security-council-mistral-small32-24b · `Mistral Small 3.2 24B ctx16k` | Ollama security direct | Blue council member; catalog documents JSON behavior on the oMLX conversion (2026-09-25), not council quality. **Pre-instrument-fix.** | **SCREEN** — preserve Mistral diversity; no repoint to Granite/Qwen without a council holdout. |
| security-expert-foundation-sec-8b · `Foundation-Sec-8B Reasoning Q8_0 ctx8k` | Ollama security direct | No-tools fed security expert. Independent 2026-10-05 public fresh-CVE/CWE scores are directional and unmatched to VulnLLM; `docs/WFE_SEAT_PRIOR_20261018.md` marks the matchup unknown. | **SCREEN** — keep as a distinct security-specialist family pending the planned matched 20-item screen. |

The two no-hint variants are roles, not two additional model-hint slots: `blueteam-orchestrated` resolves tool `security-tool-granite41-8b`, reasoning `security-council-granite41-30b`, expert `security-expert-foundation-sec-8b`; `blueteam-council` uses that tool/expert with council members Granite 4.1 30B, Mistral Small 3.2 24B, and Qwen3.6 27B. These retain **three council lineages plus a Foundation-Sec expert** after this review.

### `tools-specialist` — function and API calling

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Qwen3.6-35B-A3B UD-Q4_K_XL ctx96k` | oMLX-general alias `unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit`; Ollama fallback | Multi-tool function/API composition. E10 reports Qwen3.6 76/87, Qwen3.8 76/78, Granite 96/108; no separation. Operator kept Qwen3.6 for lane intent and p90 17.6s vs 339s. **Post-audit, pre-Stage-0.** | **KEEP** — evidence-backed incumbent; Qwen3.8 is not a speed or tool-quality replacement here. |
| fast · `Gemma4 E4B QAT ctx8k` | Ollama general direct | Compact tool composition. E16: 9/9 + 9/9 2026-09-11 WFE; fast baseline 12/12 on 2026-10-29; LFM3 lost 90/108 vs incumbent 103/108. **Pre-instrument-fix for September, pre-Stage-0 for October.** | **KEEP** — LFM3 was retired 2026-11-13; Qwen3.6 is not a measured faster replacement. |

### `auto-reasoning` — hard reasoning and specialist variants

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `K2-Horizon-MoVA-36B-A4B Q4_K_M ctx64k` | Ollama reasoning direct | Hard reasoning. E5: 12/12, 28s median; incumbent DeepSeek 8/12 at 383s; GLM 10/12 at 248s; stable 13/13 on the follow-up. **Post-audit, pre-Stage-0.** | **SCREEN** — strong scoped result, but rerun/confirm under Stage 0 before treating as a generally best reasoning seat. |
| deep · `Qwen3.8-27B Q4_K_M ctx32k` | oMLX-reasoning alias `Qwen3.8-27B-oQ4e-mtp`; Ollama fallback | Deep reasoning. E4 supports Qwen3.8 math but is not this role's general reasoning task. | **SCREEN** — no direct evidence that auto-daily or coding results cover deep analysis. |
| math · `GLM-4.7-Flash Q4_K_M ctx64k` | Ollama general direct (reasoning fallback group is second) | Math. E4: 104/108 vs Phi-4 93/108, but no comparison against Qwen3.8 (107/108) or DeepSeek (105/108). **Post-audit, pre-Stage-0.** | **SCREEN** — keep until a direct current math A/B; Qwen3.8 is plausible but not pairwise-tested. |
| glm-thinker · `THUDM GLM-Z1-32B Q4_K_M ctx32k` | Ollama reasoning direct | Think-enabled reasoning variant; no exact seat result found. | **SCREEN** — GLM math seat does not prove this checkpoint/role. |
| magistralstrategist · `Magistral Small 2509 Q8_0 ctx64k` | Ollama general direct | Strategic reasoning alternative; no matching WFE found. | **SCREEN** — no current-model coverage demonstrated. |

### `auto-council` — proposal review council

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Gemma-4-26B-A4B-it QAT 4bit` | oMLX-general direct | Council Evidence Auditor, Challenger, Operator/User Advocate, and synthesizer all use this checkpoint. E12 records the explicit 2026-10-19 self-consistency decision: 26s vs 225s old roster with equal 12/20 and 16/20 key-issue score; rubric v2 13/20, support 4/5, reject 3/5. **Pre-Stage-0.** | **KEEP** — this is an explicit measured speed/quality design, not a new consolidation. **Diversity exception:** member lineage is Gemma-only; do not further fold the separate compliance or blue councils into it. The 2026-11-13 “never collapse a council to one family” rule conflicts with this existing 10/19 single-model design and needs orchestrator/operator interpretation before any roster change. |

### `auto-documents` — office document creation

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Gemma4 26B QAT ctx32k` | oMLX-general alias `gemma-4-26b-a4b-it-QAT-4bit`; Ollama fallback | Document generation. E8: QAT/plain A/B 30/32 vs 31/32, not separated; QAT selected 2026-11-06. Model Seat Process separately found Gemma plain vs Qwen3.8 tied 108/108, Gemma faster. | **KEEP** — selected build with direct seat evidence; Qwen3.8 offers no proven quality gain. |
| extract-uncensored · `LFM2.5-8B-A1B uncensored ctx8k` | Ollama general direct | Uncensored extraction; no role-matched result found. | **SCREEN** — document Gemma QAT is plausible for normal docs, not proven for uncensored extraction. |

### `auto-research` — web research and data variant

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Nex-N2-mini UD-Q4_K_M ctx16k` | Ollama general direct (reasoning group has no alias for this tag) | Web research/synthesis. E9: operator kept N2-mini over N2.5-mini on 103/108 vs 87/87 curtailed, no separation; N2-mini faster. 2026-11-13 intake reopens the N2.5 screen; newer N2.6 Q4 is 200.83 GB and outside the 40 GB envelope. | **KEEP** — retain current seat while the reopened N2.5 screen runs; a newer family number is not proof. |
| data · `Qwen3.6-35B-A3B UD-Q4_K_XL ctx32k` | oMLX-reasoning alias `unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit`; Ollama fallback | Data analysis and tool use. E6 demonstrates the repaired guard/zero-call path and 12/12 replay. | **KEEP** — current evidence is specific and no better qualified replacement is on file. |

### `auto-vision` — image understanding

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Qwen3-VL 32B ctx8k` | Ollama vision direct | Main vision model; no current matched image-turn result found for this exact tag. | **SCREEN** — the 2026-11-07 Gemma26B fallback tie (E13) does not qualify Qwen3-VL. |
| gemma4jangvision · `Gemma4-31B JANG 4M CRACK Q4_K_M ctx8k` | Ollama vision direct | Alternate image model; no role-matched result found. | **SCREEN** — no current coverage from Gemma26B text/document results. |
| gemma_vision · `Gemma4 31B QAT ctx8k` | Ollama vision direct | Alternate image model; no role-matched result found. | **SCREEN** — E13 measures a 26B fallback, not this 31B variant. |

### `security-reviewer` — evidence-grounded telemetry review

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Granite 4.1 8B ctx8k` | Ollama general direct | Read-only analyst review. `docs/WFE_LANDSCAPE_FLEET_20261018.md` says this seat is unmeasured and cites no ExCyTIn per-model scores; catalog records path/tool facts only. **Pre-Stage-0.** | **SCREEN** — no evidence that auto-security or other Granite roles cover telemetry judgement. |

### `hunt-reasoning` — hunt-source interpretation

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Gemma4 26B QAT ctx8k-hunt` | oMLX-general alias `gemma-4-26b-a4b-it-QAT-4bit`; Ollama fallback | Hunt reasoning; same QAT checkpoint as auto-council with baked hunt sampling. E14 names this exact incumbent for the “Hunt parallel” engine row. | **ENGINE-EVAL-DEPENDENT** — wait for the resident Gemma QAT engine/co-residency decision. |

### `auto-compliance` — compliance default and reading variant

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Qwen3.8-27B Q4_K_M ctx32k` | oMLX-reasoning alias `Qwen3.8-27B-oQ4e-mtp`; Ollama fallback | Compliance triage, advisories, framework lookups. E7 is exploratory (10/11 Qwen3.8 vs Granite 2/11), with no confirm; tool-loop repeats remain a guard watch. **Post-audit, pre-Stage-0.** | **SCREEN** — keep Qwen3.8 pending a decision-grade live compliance screen; Gemma reading is not equivalent to this triage role. |
| reading · `Gemma4 26B plain Q4_K_M ctx128k` | oMLX-general alias `mlx-community--gemma-4-26b-a4b-it-4bit`; Ollama fallback | Long-document reading. E13 is the 2026-11-07 seat-process close: plain/QAT tied on four real documents/questions at 20–38k, judges split, so plain stays. | **KEEP** — Qwen3.8 is slower on documented reading and no better; retain plain for its 128k role. |

### `compliance-mapping` — internal map/reduce reader

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Gemma4 26B plain Q4_K_M ctx128k` | oMLX-general alias `mlx-community--gemma-4-26b-a4b-it-4bit`; Ollama fallback | Machine calls for sweep mapping, standard reduction, and batch reading; shares the proven plain-reading checkpoint. No separate map/reduce comparison located. | **SCREEN** — keep same checkpoint/window pending a role-specific map/reduce check; no smaller resident effect is demonstrated. |

### Compliance council seats

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| `compliance-council-qwen38` · `Qwen3.8-27B Q4_K_M ctx32k` | **Configured** oMLX-general alias → `Qwen3.8-27B-oQ4e-mtp`; Ollama fallback | JSON council seat. E14 specifically requires **plain Qwen3.8-27B-4bit** for this row and says not to use oQ4e-MTP. Current preferred alias is therefore a source-level preflight mismatch; no row result can resolve it. | **ENGINE-EVAL-DEPENDENT** — pause this cell until the orchestrator reconciles the alias against the approved plain-checkpoint matrix. Do not edit config here. |
| `compliance-council-granite41` · `Granite 4.1 30B ctx16k` | oMLX-general alias `granite-4.1-30b-4bit`; Ollama fallback | Council member. `config/compliance/council.yaml` retains Granite as one of three lineages; no current independent holdout closure found. | **SCREEN** — preserve Granite lineage; do not consolidate with Qwen or Gemma. |
| `compliance-council-deepseek-r1` · `DeepSeek-R1-0528-Qwen3-8B Q4_K_XL ctx64k` | oMLX-reasoning alias `DeepSeek-R1-0528-Qwen3-8B-4bit`; Ollama fallback | Council member explicitly retained for diagnosis and architectural diversity. Prior P3B holdout failed schema/citation gates (20/21 then 21/21 schema; citation 14/21 then 7/21), per `config/compliance/council.yaml`; that does not prove a global model limitation. | **SCREEN** — keep as the third lineage pending prompt/contract diagnosis and holdout; no seat family is removed. |

The compliance council lineage mix after every proposal in this review remains **Qwen3.8 + IBM Granite + DeepSeek-R1/Qwen3 distill**. The Qwen JSON checkpoint/engine mismatch is unresolved; it is not a reason to remove that member.

### `compliance-reading-overflow` — 64k overflow reader

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Gemma4 26B QAT ctx64k` | oMLX-general alias `gemma-4-26b-a4b-it-QAT-4bit`; Ollama fallback | Reading overflow. QAT moved into this seat on 2026-11-06 (backend/catalog notes and closeout), while plain ctx64k remains registered. | **KEEP** — it is an explicit operator seat decision; retain plain 128k reader separately under E13. |

### `auto-audio` — audio plus image/video/music variants

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Gemma4 12B QAT ctx8k` | Ollama vision direct | Audio transcription/understanding; no real audio-turn evidence found in reviewed seat docs. | **SCREEN** — vision and text seats are not audio coverage. |
| image · `Granite 4.1 8B ctx16k` | Ollama general direct; no matching model in this workspace's vision backend and no oMLX alias | Image handling through this workspace's media route; no role-matched result found. | **SCREEN** — distinct from auto-vision and the Gemma4-31B variants. |
| video · same `Granite 4.1 8B ctx16k` | Ollama general direct; no matching model in this workspace's vision backend and no oMLX alias | Video analysis; no role-matched result found. | **SCREEN** — same weights as image slot, but different input modality; do not drop either role based on absent telemetry. |
| music · `LFM2.5 8B ctx8k` | Ollama general direct | Music understanding; no role-matched result found. | **SCREEN** — no seated model has demonstrated this task coverage. |

### `task-router` — Open WebUI titles/tags/follow-ups

| Slot / model hint | Configured preferred path | Role; dated evidence and coverage | Review |
|---|---|---|---|
| default · `Gemma4 E4B OBLITERATED Q4_K_M ctx2k` | Ollama general direct | Shares the resident tag with `LLM_ROUTER_MODEL`. Catalog records a six-conversation comparison: less-specific titles than General Fast, comparable tags/follow-ups/queries, and 3–4× faster idle. E14 names this exact router-residency cell. | **ENGINE-EVAL-DEPENDENT** — keep the 2k resident tag while the “Task router” co-residency row runs; do not substitute another Gemma build. |

## Diversity and consolidation proposal

### Target fleet

The smallest **safe** target supported today is the current seated portfolio with duplicate aliases treated as one artifact where the route resolves to one checkpoint. This review does not have enough evidence to name a smaller distinct-weight fleet without sacrificing an untested role. The potential reuse that is already real in source is:

- Qwen3.8 MTP is the preferred oMLX checkpoint for auto-coding default/heavy/qwen38coder, auto-spl default, auto-daily deep, auto-reasoning deep, auto-compliance default, and the current compliance-council Qwen row. These are multiple role/context selectors, not multiple oMLX weight copies. The compliance-council JSON seat is the exception: the approved matrix expects plain 4-bit, so do not count it as valid MTP coverage.
- Gemma QAT 26B is shared by auto-council, documents, hunt, daily Gemma-fast, and 64k overflow, with distinct windows/settings. Keep plain Gemma 26B for 128k compliance reading; the 2026-11-07 process found a tie, not a basis to fold that seat.
- Granite 4.1 roles share model families between reviewer/tool and blue/council work; role prompts and tool contracts remain separate. Keep the Mistral, Qwen3.6, DeepSeek-R1, and Foundation-Sec council/expert members so the blue/security roster does not converge on Granite.
- Red/purple roles retain Qwen3.5 and SuperGemma families alongside Granite blue roles. Same-family red/purple selectors are different role/context assignments, not evidence of removable traffic.

The current `auto-council` roster is a **pre-existing one-family exception**: its three members and synthesizer all use Gemma QAT. The 2026-10-19 decision measured a faster same-model design with equivalent aggregate scores on its 20-case set. Because the present task says never collapse a council to one family, no new reduction may use that design as precedent. The orchestrator should resolve whether that rule is intended to reopen this explicit prior decision before changing its roster. This review does not touch it.

### Savings by proposed action

| Proposal | Prerequisite / target | Disk freed | RAM / resident-set effect |
|---|---|---:|---:|
| Remove duplicate `auto-daily::nemotron` selector, retaining default `Nemotron 3.5 Lightning ... ctx32k` | Verify no operator/UI contract depends on the duplicate name. | **0 bytes**; exact same registered tag remains. | **0 MB**; the model and resident path are unchanged. UI selector only. |
| Canonicalize `auto-coding::qwen38coder` to the existing default seat, `Qwen3.8-27B-oQ4e-mtp` | After the dense-coding engine row, compare both hints' effective context, settings, fallback, persona pins, and usage before a config proposal. | **0 weight bytes** on preferred oMLX path; current aliases resolve to same checkpoint. GGUF base/ctx tags are derived tags sharing weights. | **0 MB** if the same alias is reused; no extra preferred oMLX checkpoint is loaded today. |
| Any family-level trim: old coding alternatives, vision/audio models, or security/council members | Requires role-specific real use, persona/council/pipeline reference audit, and WFE closeout v4. No usage logs were found. | **Unknown**: exact exclusive blob bytes were not measured in this review. | **Unknown**: do not infer resident overlap from a catalog size or a model tag. |
| Any engine replacement among daily MoE, dense coding, Gemma QAT, council/JSON, or task router | E14's exact engine row must pass quality, speed noise floor, router+seat co-residency, and swap gate. | **Unknown before the artifact/engine winner**; same-bytes and different-byte arms must not be mixed in estimates. | **Unknown until the row's co-residency receipt**; do not sum isolated model RSS. |

The inventory's September 2026 closeout storage totals are not current storage measurements and are intentionally not used here. The existing cleanup audit is a disposition snapshot, not an exclusive-byte accounting for proposed changes.

### Ordered live queue (one seat question at a time)

Run one item to a decision under `docs/MODEL_SEAT_PROCESS.md` before starting the next. For each: freeze the incumbent, candidate, action-on-win, live setup proof, real task set, budget, valid rows, blind judge packet, and default “unproven — keep incumbent.” Nothing in this list authorizes removing a seat.

1. **Resolve preflight, then Stage 0: `compliance-council-qwen38` and “Council / JSON.”** Reconcile the configured oMLX alias to MTP with E14's plain Qwen3.8 checkpoint requirement before any scored rows. A mismatch/invalid arm is not a quality result. If corrected in an authorized follow-up, verify the exact 32k hint, JSON format, sampling, and production tool-less call first.
2. **“Daily MoE.”** Compare the approved same-byte engine cells with the production auto-daily Nemotron incumbent; record router and other seated model co-residency, 16k and long-context cells separately, quality, noise floor, and swap gate. Ollama GGUF vs oMLX oQ4e are different artifacts; do not score them as same bytes.
3. **“Dense coding, with its speed lever.”** Test the exact plain Qwen3.8 4-bit, MTP sidecar, and named DFlash2 pairings in E14; exclude Splash plain when it still drafts and do not replace the drafter. Use a real coding task set and test default/heavy/qwen38coder role parity before canonicalizing those aliases.
4. **“Hunt parallel” (shared Gemma QAT).** With the named QAT checkpoint and Stage 0 oMLX baseline, test each approved same-byte engine under router/seat co-residency. A win moves only the engine path, not the seat's role or Gemma lineage.
5. **“Task router.”** Test the exact E4B OBLITERATED GGUF with the intent-router seat resident alongside the selected production seat. Keep the 2k cap and confirm the task-model behavior separately from user chat.
6. **Remaining SCREEN seats in role blocks, each as its own bounded decision:** (a) Kat/laguna/coding variants and CAD contexts; (b) auto-spl default vs Nano on real SPL/YARA tasks; (c) auto-security defensive, red/purple and blue council on actual authorized workflow tasks; (d) vision/audio/video/music input tasks; (e) K2/Qwen deep/math/GLM thinker reasoning; (f) research N2.5 reopened screen; (g) map/reduce and uncensored document extraction. Do not parallelize model trials on the shared host.
7. **After all seat decisions only:** verify active references in `config/portal.yaml`, personas, councils, router, code, and request logs; measure exclusive bytes/resident set for the exact artifacts; complete WFE's held closeout/reissued v4. Only then can the operator consider a physical trim.

E14 rows are prerequisites for the rows that share their checkpoint/engine decision: auto-daily default → Daily MoE; auto-coding default/heavy/qwen38coder/qwen38coder-dflash → Dense coding; auto-daily gemma-fast and hunt-reasoning → Hunt parallel; compliance-council-qwen38 → Council/JSON; task-router → Task router. General role screens do not substitute for those engine gates.

## Audit conflicts and limits

- The checked-in closeout register's historical `gemma4:e4b-it-qat-ctx8k` row says REMOVED_CLOSED, but §11 of `docs/MODEL_FLEET_CLOSEOUT_20260906.CLOSEOUT.md` corrects it to INTEGRATED and current config names it in `tools-specialist::fast`. The audit snapshot lists it among “REMOVED_CLOSED still on disk”; this is not permission to delete. Config/catalog and closeout correction are the independent source checks.
- The same audit snapshot lists `hf.co/bartowski/nex-agi_Nex-N2.5-mini-GGUF:Q4_K_M` as a cleanup exception. `docs/MODEL_INTAKE_FRESHNESS_20261113.md` explicitly reopens the N2.5-mini screen and says its local tag stays on disk. The intake freshness update postdates the audit snapshot; keep it available for that screen.
- The audit snapshot reports zero config drift, but the two exception lines conflict with present source state for the E4B tag and the reopened N2.5 screen. No live store check was run to establish the current physical state.
- `docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md` still holds removals until a completed WFE closeout reissues v4. This review therefore recommends no family deletion.
- The approved engine matrix's council/JSON plain-Qwen requirement does not match the current preferred oMLX alias. This is a preflight issue to resolve before that cell; this report does not edit config.
- The `auto-council` single-family roster predates the current diversity constraint. Its prior reason and measured tradeoff are recorded above; its current acceptability is an orchestrator/operator decision.

## Decision summary

**Keep:** evidence-backed tools-specialist Qwen3.6 and Gemma fast, Kat fast-repair, Gemma QAT documents/council/hunt/overflow seats under their existing role limits, plain Gemma 128k reading, Qwen3.6 guarded data, Nex-N2-mini pending reopened screen, and the multi-lineage councils/security roles.

**Wait on engine evaluation:** auto-daily Nemotron, auto-daily Gemma fast, auto-coding Qwen3.8 default/heavy/DFlash2, hunt Gemma QAT, compliance-council Qwen3.8, and task-router E4B. The compliance Qwen row has a matrix/alias mismatch that must be resolved first.

**Consolidate or trim only as selectors:** auto-coding qwen38coder → default Qwen3.8 MTP (conditional, zero resource savings) and auto-daily nemotron → default (duplicate selector, zero resource savings). No distinct model removal is evidence-backed by this inventory because usage telemetry is absent and the WFE removal gate remains open.
