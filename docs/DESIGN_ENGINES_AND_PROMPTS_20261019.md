# Design: engines and prompts — consolidating workspaces and personas (draft, 2026-10-19)

**Status:** draft for operator markup. Nothing changes until this is approved.

**Operator:** "the workspaces are vast… could also be simplified and with the personas"; personas
are "excessive… we could build a lot of those into a workspace that is prompt injection as that's
really the main difference". No lane is being cut for lack of use; this is a re-shaping.

## The model

- **Engine** (a workspace): model + tools + context window + sampling + thinking. The thing
  that is screened, audited and kept conformant. About **11 user-facing engines**, from 34
  production workspaces.
- **Variant**: an engine with a different model or tool set (`coding::cad`, `chat::deep`).
  Variants already exist (`auto-coding` has 10, `auto-security` 16) and the pipeline resolves
  `engine::variant` ids today.
- **Prompt**: a role. It changes only the instructions, so it is not a model entry. Delivered as
  an Open WebUI prompt-library entry, seeded by `openwebui_init.py` (no Open WebUI source change,
  Rule 2). The user picks an engine, then types `/role`.
- **Persona** stays only where it changes behaviour beyond the prompt (tool allow/deny lists,
  forced tool choice).

| Today | After |
|---|---|
| 58 workspaces (34 production + 24 bench), 30 variants | ~11 engines + variants; internals hidden; bench in its own config |
| 112 personas, each an Open WebUI model entry | 86 prompts, 11 engine variants, 15 personas |
| 13 bench workspaces visible in the Open WebUI model list | none |

## Engines

| Engine | Built from | Notes |
|---|---|---|
| `auto` | `auto` | the router; its label set shrinks to the engines below |
| `chat` | `auto-daily`, `general-fast`, `general-deep`, `auto-nemotron` | fast / deep / nemotron become variants |
| `coding` | `auto-coding` (+10 variants), `auto-bigfix`, `auto-cad`, `auto-spl` | CAD keeps its tools as a variant; SPL keeps its model as a variant |
| `reasoning` | `auto-reasoning`, `auto-math` | K2-Horizon covers both; math becomes a variant only if a screen says it needs its own model |
| `research` | `auto-research`, `auto-data` | data keeps its DuckDB tools as a variant |
| `documents` | `auto-documents`, `auto-extract-uncensored` | |
| `compliance` | `auto-compliance`, `compliance-reading` | the council seats, mapping and reading-overflow are internal and already hidden |
| `vision` | `auto-vision` | |
| `media` | `auto-image`, `auto-video`, `auto-music`, `auto-audio` | one tool-dispatcher model routes to the image / video / music / audio tools; today four models do this. Needs a small screen to pick the dispatcher |
| `uncensored` | `auto-general-uncensored`, `auto-uncensored-throwaway`, `auto-creative` | creative writing becomes prompts on this engine |
| `security` | `auto-security` (+16), `security-reviewer` | unchanged; security is out of scope |

Utilities and internals: `auto-council` (decide whether it stays in the dropdown), and hidden:
`tools-specialist`, `task-router`, `compliance-mapping`, `compliance-reading-overflow` and the
three `compliance-council-*` seats.

## What has to change (mechanics)

1. **Back-compat aliases.** Old workspace ids keep resolving: the pipeline maps `general-deep`
   → `chat::deep`, `auto-math` → `reasoning::math`, and so on, so API callers, opencode
   providers, Open WebUI chat history and scripts keep working. Aliases are listed in
   `config/portal.yaml`; `sync-config` derives the rest.
2. **Prompts.** `openwebui_init.py` seeds each PROMPT persona's `system_prompt` as an Open WebUI
   prompt (`/slug`). The persona YAML stays the source of truth (Rule 5); a field says how it is
   delivered (`delivery: prompt | persona`).
3. **Router.** The classifier prompt lists engines, not 20 workspaces. Re-run
   `scripts/router_bench.py` on the production corpus and re-bless `tests/routing/baseline.json`.
4. **Bench.** The 24 `bench-*` workspaces move to a bench config that the bench harness reads;
   they are no longer seeded to Open WebUI. Bench runs keep working unchanged.
5. **Audits.** `settings_audit` / conformance check engines and variants; fewer lanes to keep
   card-conformant.
6. **Docs and fact-units** regenerate from config (Rule 12).

## Order of work (each step ships green)

1. Aliases + hide internals + bench out of the Open WebUI seed (no behaviour change).
2. Prompts: seed the 55 plain PROMPT personas as Open WebUI prompts; remove their model entries.
3. Merge engines one family at a time (`chat`, `reasoning`, `research`, `documents`,
   `uncensored`, `coding`, `compliance`), each with its router re-bless.
4. `media`: screen the dispatcher candidates, then merge.
5. The 31 PROMPT-on-variant and 11 model-pin personas, once their variants exist.

## Open decisions for the operator

- `auto-council` in the dropdown or utility-only?
- `media` dispatcher: one of the four current models, or screen a fresh one?
- `uncensored`: fold `auto-creative` in (proposed) or keep creative separate?
- Persona names that become prompts keep their slugs (`/proofreader`)? Proposed: yes.

The appendices are generated from `config/portal.yaml` and `config/personas/` (2026-10-19). Mark
any row's destination you disagree with.

## Appendix A — every workspace

| Today | Module | Model | Exposed | Personas | Variants | → Engine | Role |
|---|---|---|---|---|---|---|---|
| `auto` | general | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | yes | 3 | 0 | **auto** | router |
| `auto-extract-uncensored` | documents | `hf.co/gaston-parravicini/LFM2.5-8B-A1B-U` | yes | 0 | 0 | **documents** | variant extract-uncensored |
| `auto-general-uncensored` | general | `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3` | yes | 0 | 0 | **uncensored** | engine |
| `auto-uncensored-throwaway` | general | `portal5/hauhaucs-qwen36-35b:q4_K_M-ctx25` | yes | 0 | 2 | **uncensored** | variant throwaway |
| `auto-daily` | general | `gemma4:26b-a4b-it-qat-ctx16k` | yes | 4 | 0 | **chat** | engine |
| `general-fast` | general | `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4` | yes | 0 | 0 | **chat** | variant fast |
| `general-deep` | general | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ct` | yes | 0 | 0 | **chat** | variant deep |
| `auto-nemotron` | general | `hf.co/bartowski/NVIDIA-Nemotron-3.5-Ligh` | yes | 1 | 0 | **chat** | variant nemotron |
| `auto-coding` | coding | `qwen3-coder:30b-a3b-q4_K_M-ctx256k` | yes | 40 | 10 | **coding** | engine |
| `auto-spl` | general | `hf.co/bartowski/huihui-ai_Qwen3-Coder-Ne` | yes | 2 | 0 | **coding** | variant spl |
| `auto-security` | security | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_` | yes | 10 | 16 | **security** | unchanged (out of scope) |
| `auto-bigfix` | general | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | yes | 0 | 0 | **coding** | variant bigfix |
| `tools-specialist` | general | `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4` | yes | 1 | 1 | **internal** | hidden |
| `auto-creative` | media | `fredrezones55/Qwen3.6-35B-A3B-Uncensored` | yes | 4 | 0 | **uncensored** | variant creative |
| `auto-reasoning` | general | `hf.co/bartowski/K2-Horizon-MoVA-36B-A4B-` | yes | 9 | 1 | **reasoning** | engine |
| `auto-council` | general | `gemma-4-26b-a4b-it-QAT-4bit` | yes | 0 | 0 | **utility** | kept, decide exposure |
| `auto-documents` | documents | `gemma4:26b-a4b-it-q4_K_M-ctx32k` | yes | 3 | 0 | **documents** | engine |
| `auto-video` | video | `granite4.1:8b-ctx16k` | yes | 0 | 0 | **media** | tool route |
| `auto-image` | image | `granite4.1:8b-ctx16k` | yes | 0 | 0 | **media** | engine (one tool dispatcher) |
| `auto-music` | media | `lfm2.5:8b-ctx8k` | yes | 0 | 0 | **media** | tool route |
| `auto-research` | research | `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M-` | yes | 8 | 0 | **research** | engine |
| `auto-vision` | general | `qwen3-vl:32b-ctx8k` | yes | 8 | 0 | **vision** | engine |
| `auto-data` | research | `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4` | yes | 7 | 0 | **research** | variant data (DuckDB tools) |
| `security-reviewer` | security | `granite4.1:8b-ctx8k` | yes | 1 | 0 | **security** | unchanged (out of scope) |
| `auto-compliance` | compliance | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ct` | yes | 7 | 0 | **compliance** | engine |
| `compliance-mapping` | compliance | `gemma4:26b-a4b-it-q4_K_M-ctx128k` | no | 0 | 0 | **internal** | hidden |
| `compliance-reading` | compliance | `gemma4:26b-a4b-it-q4_K_M-ctx128k` | yes | 0 | 0 | **compliance** | variant reading |
| `compliance-council-qwen38` | compliance | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ct` | no | 0 | 0 | **internal** | hidden |
| `compliance-council-granite41` | compliance | `granite4.1:30b-ctx16k` | no | 0 | 0 | **internal** | hidden |
| `compliance-council-deepseek-r1` | compliance | `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-` | no | 0 | 0 | **internal** | hidden |
| `compliance-reading-overflow` | compliance | `gemma4:26b-a4b-it-q4_K_M-ctx64k` | no | 0 | 0 | **internal** | hidden |
| `auto-math` | general | `glm-4.7-flash:Q4_K_M-ctx64k` | yes | 1 | 0 | **reasoning** | variant math |
| `auto-audio` | media | `gemma4:12b-it-qat-ctx8k` | yes | 0 | 0 | **media** | tool route |
| `bench-qwen3-coder-30b` | eval | `qwen3-coder:30b-a3b-q4_K_M` | yes | 0 | 0 | **bench** | bench config, not seeded |
| `bench-granite41-8b` | eval | `granite4.1:8b-ctx8k` | yes | 0 | 0 | **bench** | bench config, not seeded |
| `bench-granite41-30b` | eval | `granite4.1:30b-ctx16k` | yes | 0 | 0 | **bench** | bench config, not seeded |
| `bench-granite41-30b-ctx98k` | eval | `granite4.1:30b-ctx96k` | yes | 0 | 0 | **bench** | bench config, not seeded |
| `bench-foundation-sec-8b-reasoning` | eval | `hf.co/fdtn-ai/Foundation-Sec-8B-Reasonin` | yes | 0 | 0 | **bench** | bench config, not seeded |
| `bench-qwen35-abliterated` | eval | `huihui_ai/qwen3.5-abliterated:9b` | yes | 0 | 0 | **bench** | bench config, not seeded |
| `bench-omnicoder2` | eval | `omnicoder2:9b-q4_k_m` | yes | 0 | 0 | **bench** | bench config, not seeded |
| `bench-qwen38-27b` | eval | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` | yes | 0 | 0 | **bench** | bench config, not seeded |
| `bench-qwen38-flash-next-reap288` | eval | `Qwen3.8-Flash-Next-REAP-288-MLX-4bit` | no | 0 | 0 | **bench** | bench config, not seeded |
| `bench-nex-n25-mini-uncensored` | eval | `Nex-N2.5-mini-Uncensored-MLX-4bit` | no | 0 | 0 | **bench** | bench config, not seeded |
| `bench-gemma4-26b-optiq` | eval | `gemma4:26b-a4b-it-q4_K_M` | yes | 0 | 0 | **bench** | bench config, not seeded |
| `bench-huihui-qwen36-27b` | eval | `huihui_ai/Qwen3.6-abliterated:27b` | yes | 1 | 0 | **bench** | bench config, not seeded |
| `task-router` | eval | `hf.co/mradermacher/gemma-4-E4B-it-OBLITE` | no | 0 | 0 | **internal** | hidden |
| `bench-gemma4-e4b-qat` | eval | `gemma4:e4b-it-qat` | no | 0 | 0 | **bench** | bench config, not seeded |
| `bench-nex-n2-mini` | eval | `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` | no | 0 | 0 | **bench** | bench config, not seeded |
| `bench-e2b-pentest` | eval | `huihui_ai/gemma-4-abliterated:E2b-qat` | no | 0 | 0 | **bench** | bench config, not seeded |
| `bench-glm` | eval | `glm-4.7-flash:Q4_K_M-ctx64k` | yes | 0 | 0 | **bench** | bench config, not seeded |
| `auto-cad` | cad | `qwen3-coder:30b-a3b-q4_K_M-ctx32k` | yes | 2 | 0 | **coding** | variant cad (CAD tools) |
| `bench-qwen38-cad` | eval | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ct` | yes | 0 | 0 | **bench** | bench config, not seeded |
| `bench-qwen36-cad` | eval | `qwen3.6:27b-q4_K_M-ctx16k` | no | 0 | 0 | **bench** | bench config, not seeded |
| `bench-huihui-qwen36-35b-a3b` | eval | `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3` | yes | 0 | 0 | **bench** | bench config, not seeded |
| `bench-exec-reasoning` | eval | `huihui_ai/gemma-4-abliterated:E2b-qat` | no | 0 | 0 | **bench** | bench config, not seeded |
| `bench-hermes3` | eval | `hermes3:8b` | no | 0 | 0 | **bench** | bench config, not seeded |
| `bench-mistral-small-3-2` | eval | `mistral-small3.2:24b` | no | 0 | 0 | **bench** | bench config, not seeded |
| `bench-magistral-small` | eval | `hf.co/unsloth/Magistral-Small-2509-GGUF:` | no | 0 | 0 | **bench** | bench config, not seeded |

## Appendix B — every persona

| Persona | Today's workspace | Behaviour beyond the prompt | → Engine | Destination |
|---|---|---|---|---|
| `itexpert` | `auto` | workspace=3 | auto | PROMPT on variant (workspace=3) |
| `techreviewer` | `auto` | — | auto | PROMPT |
| `webnavigator` | `auto` | — | auto | PROMPT |
| `dailydriver` | `auto-daily` | tools_allow=8 | chat | KEEP persona (tool surface: tools_allow) |
| `gemma_e4b` | `auto-daily` | — | chat | PROMPT |
| `gemma_fast` | `auto-daily` | — | chat | PROMPT |
| `nemotronlightning` | `auto-nemotron` | tools_allow=8 | chat | KEEP persona (tool surface: tools_allow) |
| `personalassistant` | `auto-daily` | tools_allow=6, tool_choice=required | chat | KEEP persona (tool surface: tools_allow, tool_choice) |
| `agenticheavy` | `auto-coding` | variant=heavy | coding | PROMPT on variant (variant=heavy) |
| `agenticlite` | `auto-coding` | variant=lite | coding | PROMPT on variant (variant=lite) |
| `agentorchestrator` | `auto-coding` | tools_allow=14, variant=heavy | coding | KEEP persona (tool surface: tools_allow) |
| `bugdiscoverycodeassistant` | `auto-coding` | tools_allow=6, workspace=3 | coding | KEEP persona (tool surface: tools_allow) |
| `caddesigner` | `auto-cad` | — | coding | PROMPT |
| `codebasewikidocumentationskill` | `auto-coding` | variant=heavy, workspace=3 | coding | PROMPT on variant (variant=heavy, workspace=3) |
| `codereviewassistant` | `auto-coding` | — | coding | PROMPT |
| `codereviewer` | `auto-coding` | — | coding | PROMPT |
| `codingagentic` | `auto-coding` | variant=laguna | coding | PROMPT on variant (variant=laguna) |
| `codingreap288` | `auto-coding` | variant=reap288 | coding | PROMPT on variant (variant=reap288) |
| `codinguncensored` | `auto-coding` | variant=uncensored | coding | PROMPT on variant (variant=uncensored) |
| `codinguncensoredagentic` | `auto-coding` | variant=uncensored-agentic | coding | PROMPT on variant (variant=uncensored-agentic) |
| `creativecoder` | `auto-coding` | — | coding | PROMPT |
| `devopsautomator` | `auto-coding` | — | coding | PROMPT |
| `devstral_coder` | `auto-coding` | model_pin=devstral-small-2:latest-ctx8k | coding | VARIANT (model pin) + PROMPT |
| `e2edebugger` | `auto-coding` | tools_allow=6 | coding | KEEP persona (tool surface: tools_allow) |
| `e2etestauthor` | `auto-coding` | tools_deny=4 | coding | KEEP persona (tool surface: tools_deny) |
| `ethereumdeveloper` | `auto-coding` | tools_deny=4, workspace=3 | coding | KEEP persona (tool surface: tools_deny) |
| `excelsheet` | `auto-coding` | — | coding | PROMPT |
| `formfiller` | `auto-coding` | — | coding | PROMPT |
| `fullstacksoftwaredeveloper` | `auto-coding` | workspace=3 | coding | PROMPT on variant (workspace=3) |
| `gemma4-heretic-coder` | `auto-coding` | model_pin=portal5/gemma4-26b-heretic:q4_K_M-ctx256k | coding | VARIANT (model pin) + PROMPT |
| `githubexpert` | `auto-coding` | workspace=3 | coding | PROMPT on variant (workspace=3) |
| `glm-coder` | `auto-coding` | model_pin=glm-4.7-flash:Q4_K_M-ctx64k | coding | VARIANT (model pin) + PROMPT |
| `goengineer` | `auto-coding` | — | coding | PROMPT |
| `hauhaucs-coder` | `auto-coding` | model_pin=portal5/hauhaucs-qwen36-35b:q4_K_M-ctx256k | coding | VARIANT (model pin) + PROMPT |
| `javascriptconsole` | `auto-coding` | — | coding | PROMPT |
| `kubernetesdockerrpglearningengine` | `auto-coding` | — | coding | PROMPT |
| `linuxterminal` | `auto-coding` | — | coding | PROMPT |
| `ornith15-coder` | `auto-coding` | model_pin=portal5/ornith15-35b:q4_K_M-ctx256k | coding | VARIANT (model pin) + PROMPT |
| `printabilityengineer` | `auto-cad` | — | coding | PROMPT |
| `pythoncodegeneratorcleanoptimizedproduction-ready` | `auto-coding` | workspace=3 | coding | PROMPT on variant (workspace=3) |
| `pythoninterpreter` | `auto-coding` | — | coding | PROMPT |
| `qwen38coder` | `auto-coding` | model_pin=hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M | coding | VARIANT (model pin) + PROMPT |
| `qwen38coder-dflash` | `auto-coding` | model_pin=Qwen3.8-27B-4bit | coding | VARIANT (model pin) + PROMPT |
| `rustengineer` | `auto-coding` | — | coding | PROMPT |
| `seniorfrontenddeveloper` | `auto-coding` | workspace=3 | coding | PROMPT on variant (workspace=3) |
| `softwarequalityassurancetester` | `auto-coding` | workspace=3 | coding | PROMPT on variant (workspace=3) |
| `splunkdetectionauthor` | `auto-spl` | — | coding | PROMPT |
| `splunksplgineer` | `auto-spl` | — | coding | PROMPT |
| `sqlterminal` | `auto-coding` | workspace=3 | coding | PROMPT on variant (workspace=3) |
| `terraformwriter` | `auto-coding` | — | coding | PROMPT |
| `typescriptengineer` | `auto-coding` | — | coding | PROMPT |
| `ux-uideveloper` | `auto-coding` | workspace=3 | coding | PROMPT on variant (workspace=3) |
| `cippolicywriter` | `auto-compliance` | — | compliance | PROMPT |
| `complianceanalyst` | `auto-compliance` | — | compliance | PROMPT |
| `gdprdpoadvisor` | `auto-compliance` | — | compliance | PROMPT |
| `hipaaprivacyofficer` | `auto-compliance` | — | compliance | PROMPT |
| `nerccipcomplianceanalyst` | `auto-compliance` | — | compliance | PROMPT |
| `pcidssassessor` | `auto-compliance` | — | compliance | PROMPT |
| `soc2auditor` | `auto-compliance` | — | compliance | PROMPT |
| `documentationarchitect` | `auto-documents` | — | documents | PROMPT |
| `phi4specialist` | `auto-documents` | — | documents | PROMPT |
| `techwriter` | `auto-documents` | workspace=3 | documents | PROMPT on variant (workspace=3) |
| `toolcomposer` | `tools-specialist` | tool_choice=required | internal | KEEP persona (tool surface: tool_choice) |
| `businessanalyst` | `auto-reasoning` | — | reasoning | PROMPT |
| `devopsengineer` | `auto-reasoning` | — | reasoning | PROMPT |
| `glm-thinker` | `auto-reasoning` | model_pin=hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k | reasoning | VARIANT (model pin) + PROMPT |
| `gptossanalyst` | `auto-reasoning` | — | reasoning | PROMPT |
| `itarchitect` | `auto-reasoning` | workspace=3 | reasoning | PROMPT on variant (workspace=3) |
| `magistralstrategist` | `auto-reasoning` | model_pin=hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k | reasoning | VARIANT (model pin) + PROMPT |
| `mathreasoner` | `auto-math` | — | reasoning | PROMPT |
| `phi4stemanalyst` | `auto-reasoning` | — | reasoning | PROMPT |
| `productmanager` | `auto-reasoning` | — | reasoning | PROMPT |
| `seniorsoftwareengineersoftwarearchitectrules` | `auto-reasoning` | workspace=3 | reasoning | PROMPT on variant (workspace=3) |
| `dashboardarchitect` | `auto-data` | — | research | PROMPT |
| `dataanalyst` | `auto-data` | workspace=3 | research | PROMPT on variant (workspace=3) |
| `databasearchitect` | `auto-data` | — | research | PROMPT |
| `dataextractor` | `auto-data` | — | research | PROMPT |
| `datascientist` | `auto-data` | workspace=3 | research | PROMPT on variant (workspace=3) |
| `factchecker` | `auto-research` | tools_allow=5 | research | KEEP persona (tool surface: tools_allow) |
| `gemmaresearchanalyst` | `auto-research` | tool_choice=required | research | KEEP persona (tool surface: tool_choice) |
| `kbnavigator` | `auto-research` | tools_allow=4, tool_choice=required | research | KEEP persona (tool surface: tools_allow, tool_choice) |
| `machinelearningengineer` | `auto-data` | workspace=3 | research | PROMPT on variant (workspace=3) |
| `marketanalyst` | `auto-research` | tools_allow=4 | research | KEEP persona (tool surface: tools_allow) |
| `paywalledresearcher` | `auto-research` | tool_choice=required | research | KEEP persona (tool surface: tool_choice) |
| `researchanalyst` | `auto-research` | — | research | PROMPT |
| `statistician` | `auto-data` | workspace=3 | research | PROMPT on variant (workspace=3) |
| `supergemma4researcher` | `auto-research` | — | research | PROMPT |
| `webresearcher` | `auto-research` | tools_allow=5 | research | KEEP persona (tool surface: tools_allow) |
| `adversarysimulator` | `auto-security` | — | security | PROMPT |
| `blueteamdefender` | `auto-security` | variant=blueteam | security | PROMPT on variant (variant=blueteam) |
| `cybersecurityspecialist` | `auto-security` | workspace=3 | security | PROMPT on variant (workspace=3) |
| `networkengineer` | `auto-security` | workspace=3 | security | PROMPT on variant (workspace=3) |
| `pentester` | `auto-security` | variant=redteam | security | PROMPT on variant (variant=redteam) |
| `pentestlead` | `auto-security` | variant=pentest | security | PROMPT on variant (variant=pentest) |
| `purpleteamexec` | `auto-security` | variant=purpleteam-exec | security | PROMPT on variant (variant=purpleteam-exec) |
| `purpleteamlead` | `auto-security` | variant=purpleteam | security | PROMPT on variant (variant=purpleteam) |
| `redteamoperator` | `auto-security` | variant=redteam | security | PROMPT on variant (variant=redteam) |
| `securityreviewer` | `security-reviewer` | — | security | PROMPT |
| `securityuncensored` | `auto-security` | variant=uncensored | security | PROMPT on variant (variant=uncensored) |
| `creativewriter` | `auto-creative` | — | uncensored | PROMPT |
| `hermes3writer` | `auto-creative` | — | uncensored | PROMPT |
| `interviewcoach` | `auto-creative` | — | uncensored | PROMPT |
| `proofreader` | `auto-creative` | — | uncensored | PROMPT |
| `chartanalyst` | `auto-vision` | — | vision | PROMPT |
| `codescreenshotreader` | `auto-vision` | — | vision | PROMPT |
| `diagramreader` | `auto-vision` | — | vision | PROMPT |
| `gemma4e4bvision` | `auto-vision` | — | vision | PROMPT |
| `gemma4jangvision` | `auto-vision` | model_pin=hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf | vision | VARIANT (model pin) + PROMPT |
| `gemma_vision` | `auto-vision` | model_pin=gemma4:31b-it-qat-ctx8k | vision | VARIANT (model pin) + PROMPT |
| `ocrspecialist` | `auto-vision` | — | vision | PROMPT |
| `whiteboardconverter` | `auto-vision` | — | vision | PROMPT |
| `bench-qwen36-abl-27b` | `bench-huihui-qwen36-27b` | — | bench | PROMPT |

**Totals:** PROMPT 55, PROMPT on variant 31, KEEP persona 15, VARIANT 11
