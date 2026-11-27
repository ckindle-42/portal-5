# Portal 5 Feature ↔ QAT Traceability Matrix

Audit of HEAD `4bc77731b` (lane/audit-feature-traceability-matrix). Read-only walkdown: every
workspace, variant, persona, MCP tool, pipeline endpoint, GUI control and channel adapter
compared against what `tests/qat/` (Stages 0–5) actually exercises today. Counts are derived
from the live repo files, never hardcoded prose; the companion unit test
`tests/unit/test_feature_traceability_completeness.py` re-derives them and fails on drift.

## 1. Executive Summary

| metric | count | source of truth |
|---|---|---|
| total_tools (tracked tool rows) | 227 | 226 native `@mcp.tool` definitions + 1 REST-only dispatch tool (`browser_get_markdown`) |
| unique tool names | 225 | `transcribe_audio` / `transcribe_with_speakers` are each defined on two servers (whisper :8915 and mlx-transcribe :8924) |
| active_tested | 34 | wired AND exercised by a named QAT scenario (definition rows) |
| active_untested | 191 | live production surface, no QAT scenario exercises the tool itself |
| broken_or_unwired | 2 | `browser_get_markdown` (phantom native ref), `link` (graph write tool never granted) |
| stale_dead | 0 | zero dead tool definitions at HEAD; 2 dead non-tool artifacts in the Purge List (§12) |
| workspaces | 22 | config/portal.yaml `workspaces` (13 exposed / 9 internal) |
| variants | 57 | `workspaces.*.variants` (11 exposed as OWUI presets) |
| personas | 110 | config/personas/*.yaml (bench/ excluded: 2 bench personas) |
| endpoints | 23 | portal/platform/inference/router/app.py route bindings |
| gui_controls | 15 | §9 enumeration; 5 exercised by the browser QAT layer |
| owui_presets | 24 | imports/openwebui/workspaces/workspaces_all.json |
| external_unifi_tools | 210 | pinned unifi-network-mcp 0.40.0 manifest; 14 wired into Portal workspaces |

External IDE-only stdio MCPs (filesystem, fetch, docker, context7, git-ide) are
`expose_to_pipeline: false` — outside the production chat surface; enumerated in §7.3.

## 2. Method & Classification Rules

**Ground truth read:** `config/portal.yaml`, `config/personas/*.yaml`,
`config/owui_tool_servers.yaml`, `config/orchestration_arm.yaml`,
`config/inference/tools_manifest_*.json`, `imports/openwebui/workspaces/workspaces_all.json`,
every `@mcp.tool` definition under `portal/`, `portal_wiki/` and `scripts/mlx-transcribe.py`,
`portal/platform/inference/router/app.py`, `portal_channels/`, and `tests/qat/` in full.
The external unifi surface was read from the uvx cache of the exact pinned version
(`unifi-network-mcp 0.40.0`, `~/mcp/unifi-network/run.sh` pin).

**Wiring surfaces** — a tool is *wired* when granted by any of:

- W1/W2: `config/portal.yaml` `workspaces.*.tools` / `workspaces.*.variants.*.tools`
- W3: `config/personas/*.yaml` `tools_allow` (replaces the workspace set; `tools_deny` subtracts)
- W4: `config/owui_tool_servers.yaml` `servers.*` / `pipeline_native` (OWUI tool-server registration)
- W5: `orchestration_arm.*.tool_allowlist` in portal.yaml / config/orchestration_arm.yaml (Jarvis disciplines)
- W6: `portal/modules/orchestration/personal_tools.py` `LOCAL_TOOLS` (Jarvis personal reads)
  and `portal/modules/orchestration/owui_entry.py` (jarvis_submit / arm_queue_task, module-gated)
- W7: external stdio bridge (fleet `unifi`, :8949) for the 14 wired `unifi_*` names

**QAT coverage** — a tool is *tested* only when a scenario's `expected_tools` names it or the
scenario prompt instructs the model to call it by name (Stage 4 `_STAGE4_TOOL_ACTIONS`,
Stage 5 UAT `expected_tools`, Stage 1 hardening REST probes). Server `/health` infra scenarios
(s2-p3-data-mcp, s2-p3-proxmox-readonly, s2-p3-unifi-readonly, s2-p7-pipeline-mcp,
s3-hunt-mcp-{mitre,vulnintel,icsot,netforensics}) probe liveness only — they do NOT make a
tool tested. Stage 4 generic `tools` dimensions without a named action assert no specific tool.

**Buckets (exactly one per tracked tool row):**

- `ACTIVE_TESTED` — wired ∧ tested (scenario IDs cited per row).
- `ACTIVE_UNTESTED` — defined and served; wired, or a documented operator/agent/eval surface
  with active callers; no QAT scenario exercises the tool itself. Each row carries a Stage 5
  journey target (§13).
- `BROKEN_OR_UNWIRED` — referenced in a workspace/persona but missing a native definition,
  or defined-and-served with a documented sibling contract but never granted (see §11).
- `STALE_DEAD` — retired/unused with zero active callers. Zero tool definitions qualify at
  HEAD; two dead non-tool artifacts are listed in §12. The brief's example ("retired compliance
  coverage engine tools") does NOT hold at HEAD — see §14 honest negatives.

## 3. Workspaces (22)

Options legend: `think` = reasoning toggle; `ews` = enable_web_search; `rp` = repeat_penalty;
`hops/calls` = max_tool_hops/max_tool_calls. Full sampling vectors live in config/portal.yaml;
this table carries the audit-relevant fields. `tools` counts the granted tool list.

| workspace | module | expose | model_hint | think | ews | tools | variants | QAT coverage |
|---|---|---|---|---|---|---|---|---|
| `auto` | general | yes | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | False | True | 0 | 0 | s2-p1-auto; s4-auto-{core,continuity,edge}; s5-route-kubernetes-rbac, s5-route-tls-firewall, s5-route-math-integral (router seat); s3-injection-1..3, s3-refusal-preservation target lanes |
| `auto-general-uncensored` | general | yes | `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-ablit…` | False | False | 6 | 4 | s2-p1-auto-general-uncensored; s4-auto-general-uncensored-{core,tools,continuity,edge}; s2-p4-auto-general-uncensored; s3-refusal-preservation; s4-auto-general-uncensored-tools (web_search) |
| `auto-daily` | general | yes | `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-3…` | True | True | 14 | 5 | s2-p1-auto-daily; s4-auto-daily-{core,tools,continuity,edge}; s2-p4-auto-daily; s2-p4-memory-roundtrip; s2-p4-omlx-tool-calling; s5-memory-cross-session; s5-daily-out-of-lane; s2-p7-personal-intake |
| `auto-coding` | coding | yes | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` | True | False | 72 | 17 | s2-p1-auto-coding; s4-auto-coding-{core,tools,continuity,edge}; s2-p3-auto-coding; s2-p3-obscura-browser; s5-sandbox-python-bash-network-isolation; s5-route-kubernetes-rbac target |
| `auto-spl` | general | yes | `Qwen3.8-27B-oQ4e-mtp` | False | False | 26 | 1 | s2-p1-auto-spl; s4-auto-spl-{core,tools,continuity,edge}; s3-hunt-windows, s3-hunt-sysmon, s3-hunt-fortigate (query_splunk) |
| `auto-security` | security | yes | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx…` | False | True | 18 | 16 | s2-p1-auto-security; s4-auto-security-{core,tools,continuity,edge}; s3-canonical-auto-security (base); s4-auto-security-tools (lookup_cve); s3-canonical-auto-security-<variant> per variant |
| `tools-specialist` | general | no | `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-c…` | True | False | 3 | 1 | internal; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-reasoning` | general | yes | `hf.co/bartowski/K2-Horizon-MoVA-36B-A4B-GGUF:Q4…` | True | True | 0 | 4 | s2-p1-auto-reasoning; s4-auto-reasoning-{core,continuity,edge}; s2-p2-auto-reasoning |
| `auto-council` | general | no | `gemma-4-26b-a4b-it-QAT-4bit` | False | False | 0 | 0 | s2-p2-auto-council is gated on preset presence; auto-council has no OWUI preset at HEAD, so the scenario is NOT emitted |
| `auto-documents` | documents | yes | `gemma4:26b-a4b-it-qat-ctx32k` | None | False | 7 | 1 | s2-p1-auto-documents; s4-auto-documents-{core,tools,continuity,edge}; s2-p3-auto-documents; s2-p3-auto-documents-pdf-read; s5-documents-office-content; s5-documents-upload-readback-rag; s4-auto-documents-tools |
| `auto-research` | research | yes | `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M-ctx16k` | None | True | 11 | 1 | s2-p1-auto-research; s4-auto-research-{core,tools,continuity,edge}; s2-p2-auto-research; s2-p3-rag-roundtrip; s5-rag-followup |
| `auto-vision` | general | yes | `qwen3-vl:32b-ctx8k` | None | False | 5 | 2 | s2-p1-auto-vision; s4-auto-vision-{core,tools,continuity,edge}; s2-p1-auto-vision (inline PNG); s2-p2-auto-vision; s4-auto-vision-tools (generate_image) |
| `security-reviewer` | security | yes | `granite4.1:8b-ctx8k` | None | False | 13 | 0 | s2-p1-security-reviewer; s4-security-reviewer-{core,tools,continuity,edge}; s3-security-reviewer; s5-security-hunt-workflow (hunt_sources/start/status/leads) |
| `hunt-reasoning` | security | no | `gemma4:26b-a4b-it-qat-ctx8k-hunt` | None | False | 0 | 0 | internal hunt judge seat (review service); no direct QAT scenario |
| `auto-compliance` | compliance | yes | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | False | True | 46 | 1 | s2-p1-auto-compliance; s4-auto-compliance-{core,tools,continuity,edge}; s2-p8-auto-compliance (IN_SERVICE=False annotation); s5-compliance-multiframework (compliance_ask); s5-compliance-abstention |
| `compliance-mapping` | compliance | no | `gemma4:26b-a4b-it-q4_K_M-ctx128k` | False | False | 0 | 0 | internal engine/council seat; no dedicated QAT scenario |
| `compliance-council-qwen38` | compliance | no | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | False | False | 0 | 0 | internal engine/council seat; no dedicated QAT scenario |
| `compliance-council-granite41` | compliance | no | `granite4.1:30b-ctx16k` | False | False | 0 | 0 | internal engine/council seat; no dedicated QAT scenario |
| `compliance-council-deepseek-r1` | compliance | no | `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4…` | True | False | 0 | 0 | internal engine/council seat; no dedicated QAT scenario |
| `compliance-reading-overflow` | compliance | no | `gemma4:26b-a4b-it-qat-ctx64k` | False | False | 0 | 0 | internal engine/council seat; no dedicated QAT scenario |
| `auto-audio` | media | yes | `gemma4:12b-it-qat-ctx8k` | None | False | 2 | 3 | s2-p1-auto-audio; s4-auto-audio-{core,tools,continuity,edge}; s2-p6-auto-audio-stt (transcribe_with_speakers); s2-p6-auto-audio-tts (HTTP /api/v1/audio/speech); s5-media-stt-accuracy; s4-auto-audio-tools |
| `task-router` | eval | no | `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-G…` | False | False | 0 | 0 | eval classifier; p0-routing-baseline exercises routing offline; no chat scenario |

## 4. Variants (56)

| variant | model_hint | think | ews | rp | hops/calls | tools | expose | QAT coverage |
|---|---|---|---|---|---|---|---|---|
| `auto-general-uncensored::throwaway` | `portal5/hauhaucs-qwen36-35b:q4_K_M-ctx256k` | False | True | 1.0 | —/— | 7 | no | no OWUI preset; internal seat; no dedicated QAT scenario |
| `auto-general-uncensored::throwaway-gemma4-heretic` | `portal5/gemma4-26b-heretic:q4_K_M-ctx256k` | False | True | 1.0 | —/— | 7 | no | no OWUI preset; internal seat; no dedicated QAT scenario |
| `auto-general-uncensored::throwaway-ornith15` | `portal5/ornith15-35b:q4_K_M-ctx256k` | False | True | 1.05 | —/— | 7 | no | no OWUI preset; internal seat; no dedicated QAT scenario |
| `auto-general-uncensored::creative` | `fredrezones55/Qwen3.6-35B-A3B-Uncensored-Ha…` | False | False | None | —/— | 0 | no | no OWUI preset; persona-bound (4 persona(s)); no dedicated QAT scenario |
| `auto-daily::gemma-fast` | `gemma4:26b-a4b-it-qat-ctx32k` | False | True | 1.0 | —/— | inherit(14) | no | no OWUI preset; internal seat; no dedicated QAT scenario |
| `auto-daily::fast` | `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_…` | False | True | 1.0 | —/— | 82 | yes | s2-p1-auto-daily::fast; s4-auto-daily-fast-{core,tools,continuity,edge}; s2-p4-auto-daily::fast |
| `auto-daily::deep` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` | False | True | 1.0 | —/— | 13 | yes | s2-p1-auto-daily::deep; s4-auto-daily-deep-{core,tools,continuity,edge}; s2-p4-auto-daily::deep |
| `auto-daily::nemotron` | `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightni…` | False | True | 1.0 | —/— | 8 | yes | s2-p1-auto-daily::nemotron; s4-auto-daily-nemotron-{core,tools,continuity,edge}; s2-p4-auto-daily::nemotron; s4-auto-daily-nemotron-tools (remember) |
| `auto-daily::inkling` | `inkling-2-mini:ctx256k` | True | True | 1.0 | —/— | inherit(14) | yes | s2-p1-auto-daily::inkling; s4-auto-daily-inkling-{core,tools,continuity,edge} |
| `auto-coding::laguna` | `portal5/laguna-xs21:q4_K_M-ctx128k` | None | False | 1.05 | 6/10 | 13 | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-coding::northmini` | `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF…` | None | False | 1.05 | 6/10 | 8 | no | no OWUI preset; internal seat; no dedicated QAT scenario |
| `auto-coding::uncensored` | `portal5/omnicoder2-9b:q4_K_M-ctx256k` | None | False | 1.05 | 6/10 | 8 | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-coding::uncensored-agentic` | `Huihui-Qwen3.6-27B-abliterated-MLX-4bit` | False | False | 1.0 | 6/10 | 9 | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-coding::fast-repair` | `kat-coder-v2.5-dev:Q4_K_M-ctx32k` | None | False | 1.05 | 6/10 | 9 | no | no OWUI preset; internal seat; no dedicated QAT scenario |
| `auto-coding::heavy` | `Qwen3.8-27B-oQ4e-mtp` | False | False | 1.0 | 6/10 | 15 | no | no OWUI preset; persona-bound (3 persona(s)); no dedicated QAT scenario |
| `auto-coding::lite` | `portal5/agentworld-35b:ud-q4_K_XL-ctx256k` | None | False | 1.05 | 6/10 | 15 | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-coding::ornith` | `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:…` | None | False | 1.05 | 6/10 | 15 | no | no OWUI preset; internal seat; no dedicated QAT scenario |
| `auto-coding::cad` | `qwen3-coder:30b-a3b-q4_K_M-ctx32k` | None | False | 1.05 | None/None | 20 | yes | s2-p1-auto-coding::cad; s4-auto-coding-cad-{core,tools,continuity,edge}; s2-p3-auto-coding::cad; s5-cad-stl-render (cad_build + cad_render/cad_finalize) |
| `auto-coding::bigfix` | `qwen3-coder:30b-a3b-q4_K_M-ctx16k` | None | False | 1.05 | 6/10 | 3 | yes | s2-p1-auto-coding::bigfix; s4-auto-coding-bigfix-{core,tools,continuity,edge}; s2-p3-auto-coding::bigfix |
| `auto-coding::devstral_coder` | `devstral-small-2:latest-ctx8k` | None | False | 1.05 | 6/10 | 8 | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-coding::gemma4-heretic-coder` | `portal5/gemma4-26b-heretic:q4_K_M-ctx256k` | None | False | 1.05 | 6/10 | inherit(72) | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-coding::glm-coder` | `glm-4.7-flash:Q4_K_M-ctx24k-agentic` | True | False | 1.05 | 6/10 | inherit(72) | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-coding::hauhaucs-coder` | `portal5/hauhaucs-qwen36-35b:q4_K_M-ctx256k` | None | False | 1.05 | 6/10 | inherit(72) | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-coding::ornith15-coder` | `portal5/ornith15-35b:q4_K_M-ctx256k` | None | False | 1.05 | 6/10 | inherit(72) | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-coding::qwen38coder` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` | False | False | 1.0 | 6/10 | inherit(72) | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-coding::qwen38coder-dflash` | `Qwen3.8-27B-4bit` | False | False | 1.0 | 6/10 | inherit(72) | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-spl::nano` | `orcacyber-nano-1.0:ctx64k` | False | False | 1.0 | —/— | inherit(26) | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-security::uncensored` | `huihui_ai/baronllm-abliterated:latest-ctx8k` | False | True | 1.1 | —/— | 4 | no | s3-canonical-auto-security-uncensored (pipeline-addressed) |
| `auto-security::pentest` | `fredrezones55/Qwen3.6-35B-A3B-Uncensored-Ha…` | True | True | 1.0 | —/— | 7 | no | s3-canonical-auto-security-pentest (pipeline-addressed) |
| `auto-security::blueteam` | `granite4.1:8b-ctx8k` | False | True | 1.1 | —/— | 13 | no | s3-canonical-auto-security-blueteam (pipeline-addressed) |
| `auto-security::redteam` | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | False | True | 1.0 | —/— | 0 | no | s3-canonical-auto-security-redteam (disabled-annotated (security_redteam off)) |
| `auto-security::redteam-deep` | `supergemma4-26b-uncensored:Q4_K_M-ctx64k` | False | True | 1.1 | —/— | 0 | no | s3-canonical-auto-security-redteam-deep (disabled-annotated (security_redteam off)) |
| `auto-security::purpleteam` | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | False | True | 1.0 | —/— | 0 | no | s3-canonical-auto-security-purpleteam (pipeline-addressed) |
| `auto-security::purpleteam-deep` | `huihui_ai/qwen3.5-abliterated:9b-ctx64k` | False | True | 1.0 | —/— | 0 | no | s3-canonical-auto-security-purpleteam-deep (pipeline-addressed) |
| `auto-security::purpleteam-exec` | `supergemma4-26b-uncensored:Q4_K_M-ctx64k` | False | True | 1.1 | —/— | 3 | no | s3-canonical-auto-security-purpleteam-exec (disabled-annotated (security_redteam off)) |
| `auto-security::blueteam-orchestrated` | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M…` | False | True | 1.05 | —/— | 1 | no | CLI_ONLY_PRESETS: excluded from QAT preset scenarios (pipeline/CLI seat) |
| `auto-security::blueteam-council` | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M…` | False | True | 1.05 | —/— | 1 | no | s3-canonical-auto-security-blueteam-council (pipeline-addressed) |
| `auto-security::security-council-qwen36-27b` | `qwen3.6:27b-q4_K_M-ctx4k` | False | True | 1.0 | —/— | 0 | no | s3-canonical-auto-security-security-council-qwen36-27b (pipeline-addressed) |
| `auto-security::bully-handoff-drafter` | `granite4.1:30b-ctx16k` | False | True | 1.1 | —/— | 0 | no | s3-canonical-auto-security-bully-handoff-drafter (pipeline-addressed) |
| `auto-security::security-tool-granite41-8b` | `granite4.1:8b-ctx8k` | False | True | 1.0 | —/— | 0 | no | s3-canonical-auto-security-security-tool-granite41-8b (pipeline-addressed) |
| `auto-security::security-council-granite41-30b` | `granite4.1:30b-ctx16k` | False | True | 1.05 | —/— | 0 | no | s3-canonical-auto-security-security-council-granite41-30b (pipeline-addressed) |
| `auto-security::security-council-mistral-small32-24b` | `mistral-small3.2:24b-ctx16k` | False | True | 1.05 | —/— | 0 | no | s3-canonical-auto-security-security-council-mistral-small32-24b (pipeline-addressed) |
| `auto-security::security-expert-foundation-sec-8b` | `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q…` | False | True | 1.1 | —/— | 0 | no | s3-canonical-auto-security-security-expert-foundation-sec-8b (pipeline-addressed) |
| `tools-specialist::fast` | `gemma4:e4b-it-qat-ctx8k` | True | False | 1.0 | —/— | 3 | no | no OWUI preset; internal seat; no dedicated QAT scenario |
| `auto-reasoning::deep` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | True | True | 1.0 | —/— | 0 | no | no OWUI preset; internal seat; no dedicated QAT scenario |
| `auto-reasoning::math` | `glm-4.7-flash:Q4_K_M-ctx24k` | True | False | None | —/— | 0 | yes | s2-p1-auto-reasoning::math; s4-auto-reasoning-math-{core,continuity,edge}; s2-p2-auto-reasoning::math; s5-route-math-integral target |
| `auto-reasoning::glm-thinker` | `hf.co/bartowski/THUDM_GLM-Z1-32B-0414-GGUF:…` | True | True | None | —/— | inherit(0) | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-reasoning::magistralstrategist` | `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_…` | True | True | None | —/— | inherit(0) | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-documents::extract-uncensored` | `hf.co/gaston-parravicini/LFM2.5-8B-A1B-Unce…` | None | False | 1.05 | —/— | 0 | no | no OWUI preset; internal seat; no dedicated QAT scenario |
| `auto-research::data` | `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_…` | False | True | 1.0 | None/None | 7 | no | no OWUI preset; persona-bound (7 persona(s)); no dedicated QAT scenario |
| `auto-vision::gemma4jangvision` | `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGU…` | None | False | 1.0 | —/— | inherit(5) | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-vision::gemma_vision` | `gemma4:31b-it-qat-ctx8k` | None | False | 1.0 | —/— | inherit(5) | no | no OWUI preset; persona-bound (1 persona(s)); no dedicated QAT scenario |
| `auto-compliance::reading` | `gemma4:26b-a4b-it-q4_K_M-ctx128k` | False | False | 1.0 | 5/8 | 19 | yes | s2-p1-auto-compliance::reading; s4-auto-compliance-reading-{core,continuity,edge}; s2-p8-auto-compliance::reading (IN_SERVICE=False annotation) |
| `auto-audio::image` | `granite4.1:8b-ctx16k` | None | False | 1.0 | —/— | 4 | yes | s2-p1-auto-audio::image; s4-auto-audio-image-{core,tools,continuity,edge}; s2-p6-auto-audio::image; s5-media-image-quality; s4-auto-audio-image-tools (generate_image) |
| `auto-audio::video` | `granite4.1:8b-ctx16k` | None | False | 1.0 | —/— | 3 | yes | s2-p1-auto-audio::video; s4-auto-audio-video-{core,tools,continuity,edge}; s2-p6-auto-audio::video; s5-media-video-duration (video_start) |
| `auto-audio::music` | `lfm2.5:8b-ctx8k` | None | False | 1.05 | —/— | 8 | yes | s2-p1-auto-audio::music; s4-auto-audio-music-{core,tools,continuity,edge}; s2-p6-auto-audio::music; s5-media-music-audio; s5-media-tts-speech; s5-media-voice-clone; s2-p6-voice-clone |

Variant tool lists: every variant that declares `tools` replaces the base list; variants
without `tools` inherit the base workspace list (effective_workspace semantics). The
per-tool wiring columns in §6 cite the exact granting seats.

## 5. Personas (110)

**Resolution audit (all verified against HEAD):**

- All 110 `workspace_model` values resolve to a real `config/portal.yaml` workspace. Zero phantoms.
- All 41 persona `variant` bindings (27 distinct variants) resolve to a real variant of their workspace. Zero phantoms.
- All 25 distinct `tools_allow` names and every `tools_deny` name resolve to a real tool
  (native definition or wired external). Zero phantom tool references in personas.
- No duplicate slugs; no identical system prompts (no redundant/dead personas detected).
- 3 personas bind `security_redteam` variants that are disabled at HEAD (`pentester`,
  `purpleteamexec`, `redteamoperator`) — seeded but annotated-disabled, mirroring the QAT
  redteam annotation; not dead, gated by the module toggle.
- 20 personas carry a `workspace:` metadata block (enabled/description/suggested_model) —
  a schema variant, not a workspace binding; the binding is `workspace_model`.
- QAT covers 18/110 personas with dedicated scenarios: 12 in the s2-p5 sweep (first persona
  per workspace_model, PERSONA_SWEEP_MAX=12, no model_pin personas exist) + 6 unique in the
  s5 policy-contract cases. The other 92 have no dedicated scenario (journey s5-gui-persona-roster).

| persona | workspace_model | variant | tools_allow | QAT scenario |
|---|---|---|---|---|
| `itexpert` | `auto` | — | inherit | s2-p5-itexpert |
| `techreviewer` | `auto` | — | inherit | — (no dedicated scenario) |
| `webnavigator` | `auto` | — | inherit | — (no dedicated scenario) |
| `agenticheavy` | `auto-coding` | heavy | inherit | s2-p5-agenticheavy |
| `agenticlite` | `auto-coding` | lite | inherit | — (no dedicated scenario) |
| `agentorchestrator` | `auto-coding` | heavy | execute_python, execute_bash, execute_nodejs, create_word_document, c… | s5-persona-clarify-agentorchestrator; s5-persona-destructive-agentorchestrator |
| `bugdiscoverycodeassistant` | `auto-coding` | — | execute_python, execute_nodejs, execute_bash, sandbox_status, read_wo… | — (no dedicated scenario) |
| `caddesigner` | `auto-coding` | cad | inherit | — (no dedicated scenario) |
| `codebasewikidocumentationskill` | `auto-coding` | heavy | inherit | — (no dedicated scenario) |
| `codereviewassistant` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `codereviewer` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `codingagentic` | `auto-coding` | laguna | inherit | — (no dedicated scenario) |
| `codinguncensored` | `auto-coding` | uncensored | inherit | — (no dedicated scenario) |
| `codinguncensoredagentic` | `auto-coding` | uncensored-agentic | inherit | — (no dedicated scenario) |
| `creativecoder` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `devopsautomator` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `devstral_coder` | `auto-coding` | devstral_coder | inherit | — (no dedicated scenario) |
| `e2edebugger` | `auto-coding` | — | execute_python, execute_nodejs, execute_bash, sandbox_status, read_wo… | — (no dedicated scenario) |
| `e2etestauthor` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `ethereumdeveloper` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `excelsheet` | `auto-coding` | — | inherit | s5-persona-spreadsheet-excelsheet |
| `formfiller` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `fullstacksoftwaredeveloper` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `gemma4-heretic-coder` | `auto-coding` | gemma4-heretic-coder | inherit | — (no dedicated scenario) |
| `githubexpert` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `glm-coder` | `auto-coding` | glm-coder | inherit | — (no dedicated scenario) |
| `goengineer` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `hauhaucs-coder` | `auto-coding` | hauhaucs-coder | inherit | — (no dedicated scenario) |
| `javascriptconsole` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `kubernetesdockerrpglearningengine` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `linuxterminal` | `auto-coding` | — | inherit | s5-persona-terminal-linuxterminal |
| `ornith15-coder` | `auto-coding` | ornith15-coder | inherit | — (no dedicated scenario) |
| `printabilityengineer` | `auto-coding` | cad | inherit | — (no dedicated scenario) |
| `pythoncodegeneratorcleanoptimizedproduction-ready` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `pythoninterpreter` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `qwen38coder` | `auto-coding` | qwen38coder | inherit | — (no dedicated scenario) |
| `qwen38coder-dflash` | `auto-coding` | qwen38coder-dflash | inherit | — (no dedicated scenario) |
| `rustengineer` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `seniorfrontenddeveloper` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `softwarequalityassurancetester` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `sqlterminal` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `terraformwriter` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `typescriptengineer` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `ux-uideveloper` | `auto-coding` | — | inherit | — (no dedicated scenario) |
| `cippolicywriter` | `auto-compliance` | — | inherit | s2-p5-cippolicywriter |
| `complianceanalyst` | `auto-compliance` | — | inherit | s5-persona-compliance-complianceanalyst |
| `hipaaprivacyofficer` | `auto-compliance` | — | inherit | — (no dedicated scenario) |
| `nerccipcomplianceanalyst` | `auto-compliance` | — | inherit | — (no dedicated scenario) |
| `pcidssassessor` | `auto-compliance` | — | inherit | — (no dedicated scenario) |
| `soc2auditor` | `auto-compliance` | — | inherit | — (no dedicated scenario) |
| `dailydriver` | `auto-daily` | — | web_search, web_fetch, kb_search, kb_list, read_pdf, read_word_docume… | s2-p5-dailydriver |
| `gemma_e4b` | `auto-daily` | — | inherit | — (no dedicated scenario) |
| `gemma_fast` | `auto-daily` | — | inherit | — (no dedicated scenario) |
| `nemotronlightning` | `auto-daily` | nemotron | web_search, web_fetch, kb_search, kb_list, read_pdf, read_word_docume… | — (no dedicated scenario) |
| `personalassistant` | `auto-daily` | — | remember, recall, forget, list_memories, kb_search, web_search | — (no dedicated scenario) |
| `documentationarchitect` | `auto-documents` | — | inherit | s2-p5-documentationarchitect |
| `phi4specialist` | `auto-documents` | — | inherit | — (no dedicated scenario) |
| `techwriter` | `auto-documents` | — | inherit | — (no dedicated scenario) |
| `creativewriter` | `auto-general-uncensored` | creative | inherit | s2-p5-creativewriter |
| `hermes3writer` | `auto-general-uncensored` | creative | inherit | — (no dedicated scenario) |
| `interviewcoach` | `auto-general-uncensored` | creative | inherit | — (no dedicated scenario) |
| `proofreader` | `auto-general-uncensored` | creative | inherit | — (no dedicated scenario) |
| `businessanalyst` | `auto-reasoning` | — | inherit | s2-p5-businessanalyst |
| `devopsengineer` | `auto-reasoning` | — | inherit | — (no dedicated scenario) |
| `glm-thinker` | `auto-reasoning` | glm-thinker | inherit | — (no dedicated scenario) |
| `gptossanalyst` | `auto-reasoning` | — | inherit | — (no dedicated scenario) |
| `itarchitect` | `auto-reasoning` | — | inherit | — (no dedicated scenario) |
| `magistralstrategist` | `auto-reasoning` | magistralstrategist | inherit | — (no dedicated scenario) |
| `mathreasoner` | `auto-reasoning` | math | inherit | — (no dedicated scenario) |
| `phi4stemanalyst` | `auto-reasoning` | — | inherit | — (no dedicated scenario) |
| `productmanager` | `auto-reasoning` | — | inherit | — (no dedicated scenario) |
| `seniorsoftwareengineersoftwarearchitectrules` | `auto-reasoning` | — | inherit | — (no dedicated scenario) |
| `dashboardarchitect` | `auto-research` | data | inherit | s2-p5-dashboardarchitect |
| `dataanalyst` | `auto-research` | data | inherit | s5-persona-correlation-dataanalyst |
| `databasearchitect` | `auto-research` | data | inherit | — (no dedicated scenario) |
| `dataextractor` | `auto-research` | data | inherit | — (no dedicated scenario) |
| `datascientist` | `auto-research` | data | inherit | s5-persona-imbalance-datascientist |
| `factchecker` | `auto-research` | — | web_search, web_fetch, news_search, kb_search, kb_search_all | — (no dedicated scenario) |
| `gemmaresearchanalyst` | `auto-research` | — | inherit | — (no dedicated scenario) |
| `kbnavigator` | `auto-research` | — | kb_list, kb_search, kb_search_all, recall | — (no dedicated scenario) |
| `machinelearningengineer` | `auto-research` | data | inherit | — (no dedicated scenario) |
| `marketanalyst` | `auto-research` | — | web_search, news_search, web_fetch, kb_search | — (no dedicated scenario) |
| `paywalledresearcher` | `auto-research` | — | inherit | — (no dedicated scenario) |
| `researchanalyst` | `auto-research` | — | inherit | — (no dedicated scenario) |
| `statistician` | `auto-research` | data | inherit | — (no dedicated scenario) |
| `supergemma4researcher` | `auto-research` | — | inherit | — (no dedicated scenario) |
| `webresearcher` | `auto-research` | — | web_search, web_fetch, news_search, remember, recall | — (no dedicated scenario) |
| `adversarysimulator` | `auto-security` | — | inherit | s2-p5-adversarysimulator |
| `blueteamdefender` | `auto-security` | blueteam | inherit | — (no dedicated scenario) |
| `cybersecurityspecialist` | `auto-security` | — | inherit | — (no dedicated scenario) |
| `networkengineer` | `auto-security` | — | inherit | — (no dedicated scenario) |
| `pentester` | `auto-security` | redteam | inherit | — (no dedicated scenario) |
| `pentestlead` | `auto-security` | pentest | inherit | — (no dedicated scenario) |
| `purpleteamexec` | `auto-security` | purpleteam-exec | inherit | — (no dedicated scenario) |
| `purpleteamlead` | `auto-security` | purpleteam | inherit | — (no dedicated scenario) |
| `redteamoperator` | `auto-security` | redteam | inherit | — (no dedicated scenario) |
| `securityuncensored` | `auto-security` | uncensored | inherit | — (no dedicated scenario) |
| `splunkdetectionauthor` | `auto-spl` | nano | inherit | s2-p5-splunkdetectionauthor |
| `splunksplgineer` | `auto-spl` | — | inherit | — (no dedicated scenario) |
| `chartanalyst` | `auto-vision` | — | inherit | s2-p5-chartanalyst |
| `codescreenshotreader` | `auto-vision` | — | inherit | — (no dedicated scenario) |
| `diagramreader` | `auto-vision` | — | inherit | — (no dedicated scenario) |
| `gemma4e4bvision` | `auto-vision` | — | inherit | — (no dedicated scenario) |
| `gemma4jangvision` | `auto-vision` | gemma4jangvision | inherit | — (no dedicated scenario) |
| `gemma_vision` | `auto-vision` | gemma_vision | inherit | — (no dedicated scenario) |
| `ocrspecialist` | `auto-vision` | — | inherit | — (no dedicated scenario) |
| `whiteboardconverter` | `auto-vision` | — | inherit | — (no dedicated scenario) |
| `securityreviewer` | `security-reviewer` | — | inherit | s2-p5-securityreviewer |
| `toolcomposer` | `tools-specialist` | — | inherit | — (no dedicated scenario) |

## 6. MCP Tools — Per-Module Traceability (227 tracked rows)

Every `@mcp.tool` definition in the repo, plus the REST-only `browser_get_markdown`.
`file:line` is the decorator line. Wiring cites the granting surface (W1–W7 legend in §2;
`owui:` = W4, `arm:` = W5, `jarvis:` = W6). QAT column cites exact scenario IDs; `—` means
no scenario exercises the tool itself (server /health probes do not count).

### 6.1 Binary Research MCP (:8930, IDE-only)

`portal/modules/binary_research/tools/binresearch_mcp.py` — 3 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `re_exec` | `portal/modules/binary_research/tools/binresearch_mcp.py:144` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-binresearch-ide |
| `re_python` | `portal/modules/binary_research/tools/binresearch_mcp.py:157` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-binresearch-ide |
| `re_tools` | `portal/modules/binary_research/tools/binresearch_mcp.py:170` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-binresearch-ide |

### 6.2 CAD Render MCP (:8926)

`portal/modules/cad/tools/cad_render_mcp.py` — 11 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `render_mesh` | `portal/modules/cad/tools/cad_render_mcp.py:275` | ACTIVE_UNTESTED | `auto-coding::cad`, `owui:portal_cad` | — → s5-cad-openscad-fallback |
| `render_openscad` | `portal/modules/cad/tools/cad_render_mcp.py:338` | ACTIVE_UNTESTED | `auto-coding::cad`, `owui:portal_cad` | — → s5-cad-openscad-fallback |
| `convert_cad` | `portal/modules/cad/tools/cad_render_mcp.py:371` | ACTIVE_UNTESTED | `auto-coding::cad`, `owui:portal_cad` | — → s5-cad-openscad-fallback |
| `generate_scad` | `portal/modules/cad/tools/cad_render_mcp.py:560` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-cad-openscad-fallback |
| `generate_part` | `portal/modules/cad/tools/cad_render_mcp.py:662` | ACTIVE_UNTESTED | `auto-coding::cad` | — → s5-cad-openscad-fallback |
| `cad_build` | `portal/modules/cad/tools/cad_render_mcp.py:709` | ACTIVE_TESTED | `auto-coding::cad` | s5-cad-stl-render |
| `cad_execute` | `portal/modules/cad/tools/cad_render_mcp.py:714` | ACTIVE_UNTESTED | `auto-coding::cad` | — → s5-cad-openscad-fallback |
| `cad_measure` | `portal/modules/cad/tools/cad_render_mcp.py:719` | ACTIVE_UNTESTED | `auto-coding::cad` | — → s5-cad-openscad-fallback |
| `cad_find_holes` | `portal/modules/cad/tools/cad_render_mcp.py:724` | ACTIVE_UNTESTED | `auto-coding::cad` | — → s5-cad-openscad-fallback |
| `cad_render` | `portal/modules/cad/tools/cad_render_mcp.py:729` | ACTIVE_TESTED | `auto-coding::cad` | s5-cad-stl-render |
| `cad_finalize` | `portal/modules/cad/tools/cad_render_mcp.py:736` | ACTIVE_TESTED | `auto-coding::cad` | s5-cad-stl-render |

### 6.3 Code Sandbox MCP (:8914)

`portal/modules/coding/tools/code_sandbox_mcp.py` — 7 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `execute_python` | `portal/modules/coding/tools/code_sandbox_mcp.py:822` | ACTIVE_TESTED | `auto-general-uncensored`, `auto-general-uncensored::throwaway`, `auto-general-uncensored::throwaway-gemma4-heretic`, `auto-general-uncensored::throwaway-ornith15`, `auto-daily` (+25) | s5-sandbox-python-bash-network-isolation |
| `execute_nodejs` | `portal/modules/coding/tools/code_sandbox_mcp.py:877` | ACTIVE_UNTESTED | `auto-coding`, `auto-coding::laguna`, `auto-coding::northmini`, `auto-coding::uncensored`, `auto-coding::uncensored-agentic` (+9) | — → s5-sandbox-lifecycle |
| `execute_bash` | `portal/modules/coding/tools/code_sandbox_mcp.py:925` | ACTIVE_TESTED | `auto-general-uncensored`, `auto-general-uncensored::throwaway`, `auto-general-uncensored::throwaway-gemma4-heretic`, `auto-general-uncensored::throwaway-ornith15`, `auto-coding` (+19) | s5-sandbox-python-bash-network-isolation |
| `list_sessions` | `portal/modules/coding/tools/code_sandbox_mcp.py:961` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-sandbox-lifecycle |
| `reset_session` | `portal/modules/coding/tools/code_sandbox_mcp.py:967` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-sandbox-lifecycle |
| `execute_powershell` | `portal/modules/coding/tools/code_sandbox_mcp.py:973` | ACTIVE_UNTESTED | `owui:portal_code` | — → s5-sandbox-lifecycle |
| `sandbox_status` | `portal/modules/coding/tools/code_sandbox_mcp.py:1006` | ACTIVE_UNTESTED | `auto-coding`, `auto-coding::laguna`, `auto-coding::northmini`, `auto-coding::uncensored`, `auto-coding::uncensored-agentic` (+9) | — → s5-sandbox-lifecycle |

### 6.4 Compliance MCP (:8937)

`portal/modules/compliance/tools/compliance_mcp.py` — 43 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `lookup_control` | `portal/modules/compliance/tools/compliance_mcp.py:110` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `search_controls` | `portal/modules/compliance/tools/compliance_mcp.py:131` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `compliance_requirement` | `portal/modules/compliance/tools/compliance_mcp.py:227` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `nerc_cip_requirement` | `portal/modules/compliance/tools/compliance_mcp.py:371` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `map_frameworks` | `portal/modules/compliance/tools/compliance_mcp.py:405` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `patch_evidence` | `portal/modules/compliance/tools/compliance_mcp.py:439` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `refresh_catalogs` | `portal/modules/compliance/tools/compliance_mcp.py:528` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `nerc_cip_currency` | `portal/modules/compliance/tools/compliance_mcp.py:560` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_ingest` | `portal/modules/compliance/tools/compliance_mcp.py:585` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `compliance_kb_search` | `portal/modules/compliance/tools/compliance_mcp.py:603` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-compliance-register |
| `compliance_gaps` | `portal/modules/compliance/tools/compliance_mcp.py:908` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-compliance-register |
| `compliance_orphans` | `portal/modules/compliance/tools/compliance_mcp.py:1131` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `compliance_change_impact` | `portal/modules/compliance/tools/compliance_mcp.py:1204` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-compliance-register |
| `compliance_scenario` | `portal/modules/compliance/tools/compliance_mcp.py:1231` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-compliance-register |
| `compliance_prospective` | `portal/modules/compliance/tools/compliance_mcp.py:1358` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-compliance-register |
| `compliance_draft_revisions` | `portal/modules/compliance/tools/compliance_mcp.py:1382` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `compliance_mappings` | `portal/modules/compliance/tools/compliance_mcp.py:1461` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `compliance_scope` | `portal/modules/compliance/tools/compliance_mcp.py:1482` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `compliance_route` | `portal/modules/compliance/tools/compliance_mcp.py:1504` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `compliance_review_list` | `portal/modules/compliance/tools/compliance_mcp.py:1519` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_review_decide_batch` | `portal/modules/compliance/tools/compliance_mcp.py:1552` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_review_decide` | `portal/modules/compliance/tools/compliance_mcp.py:1583` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_sources` | `portal/modules/compliance/tools/compliance_mcp.py:1757` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_trace` | `portal/modules/compliance/tools/compliance_mcp.py:1834` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `compliance_intentionality` | `portal/modules/compliance/tools/compliance_mcp.py:1879` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `compliance_flexibility` | `portal/modules/compliance/tools/compliance_mcp.py:1935` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `compliance_analyze` | `portal/modules/compliance/tools/compliance_mcp.py:1961` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-compliance-register |
| `compliance_compare` | `portal/modules/compliance/tools/compliance_mcp.py:2071` | ACTIVE_UNTESTED | `auto-compliance` | — → s5-compliance-register |
| `compliance_impact` | `portal/modules/compliance/tools/compliance_mcp.py:2100` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-compliance-register |
| `compliance_bundle` | `portal/modules/compliance/tools/compliance_mcp.py:2112` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-compliance-register |
| `compliance_search` | `portal/modules/compliance/tools/compliance_mcp.py:2213` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_read` | `portal/modules/compliance/tools/compliance_mcp.py:2263` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_conflicts` | `portal/modules/compliance/tools/compliance_mcp.py:2329` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_links` | `portal/modules/compliance/tools/compliance_mcp.py:2361` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_timeline` | `portal/modules/compliance/tools/compliance_mcp.py:2388` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_coverage` | `portal/modules/compliance/tools/compliance_mcp.py:2411` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_note` | `portal/modules/compliance/tools/compliance_mcp.py:2527` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_notes` | `portal/modules/compliance/tools/compliance_mcp.py:2544` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_context` | `portal/modules/compliance/tools/compliance_mcp.py:2608` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_ask` | `portal/modules/compliance/tools/compliance_mcp.py:2754` | ACTIVE_TESTED | `auto-compliance` | s5-compliance-multiframework |
| `compliance_answers` | `portal/modules/compliance/tools/compliance_mcp.py:2817` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_correct` | `portal/modules/compliance/tools/compliance_mcp.py:2844` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |
| `compliance_standing_questions` | `portal/modules/compliance/tools/compliance_mcp.py:2859` | ACTIVE_UNTESTED | `auto-compliance`, `auto-compliance::reading` | — → s5-compliance-register |

### 6.5 Data MCP (:8939)

`portal/modules/data/tools/data_mcp.py` — 4 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `attach_source` | `portal/modules/data/tools/data_mcp.py:202` | ACTIVE_UNTESTED | `auto-research::data` | — → s5-data-sql |
| `run_sql` | `portal/modules/data/tools/data_mcp.py:266` | ACTIVE_UNTESTED | `auto-research::data` | — → s5-data-sql |
| `profile_table` | `portal/modules/data/tools/data_mcp.py:297` | ACTIVE_UNTESTED | `auto-research::data` | — → s5-data-sql |
| `list_session` | `portal/modules/data/tools/data_mcp.py:322` | ACTIVE_UNTESTED | `auto-research::data` | — → s5-data-sql |

### 6.6 Detection MCP (:8938)

`portal/modules/detection/tools/detection_mcp.py` — 6 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `convert_sigma` | `portal/modules/detection/tools/detection_mcp.py:56` | ACTIVE_UNTESTED | `auto-spl`, `auto-security::blueteam`, `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | — → s5-security-toolbelt |
| `validate_sigma` | `portal/modules/detection/tools/detection_mcp.py:81` | ACTIVE_UNTESTED | `auto-spl`, `auto-security::blueteam`, `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | — → s5-security-toolbelt |
| `compile_yara` | `portal/modules/detection/tools/detection_mcp.py:97` | ACTIVE_UNTESTED | `auto-spl`, `auto-security::blueteam`, `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | — → s5-security-toolbelt |
| `scan_yara` | `portal/modules/detection/tools/detection_mcp.py:109` | ACTIVE_UNTESTED | `auto-spl` | — → s5-security-toolbelt |
| `query_splunk` | `portal/modules/detection/tools/detection_mcp.py:135` | ACTIVE_TESTED | `auto-spl`, `auto-security::blueteam`, `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | s3-hunt-windows; s3-hunt-sysmon; s3-hunt-fortigate |
| `query_windows_events` | `portal/modules/detection/tools/detection_mcp.py:175` | ACTIVE_UNTESTED | `auto-spl`, `auto-security::blueteam`, `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | — → s5-security-toolbelt |

### 6.7 Documents MCP (:8913)

`portal/modules/documents/tools/document_mcp.py` — 11 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `create_word_document` | `portal/modules/documents/tools/document_mcp.py:406` | ACTIVE_TESTED | `auto-daily`, `auto-daily::fast`, `auto-daily::deep`, `auto-documents`, `auto-compliance` (+2) | s2-p3-auto-documents-pdf-read; s4-auto-documents-tools; s5-documents-office-content; s5-documents-upload-readback-rag |
| `create_powerpoint` | `portal/modules/documents/tools/document_mcp.py:496` | ACTIVE_TESTED | `auto-daily`, `auto-daily::fast`, `auto-daily::deep`, `auto-documents`, `agentorchestrator` (+1) | s5-documents-office-content |
| `create_excel` | `portal/modules/documents/tools/document_mcp.py:651` | ACTIVE_TESTED | `auto-daily`, `auto-daily::fast`, `auto-daily::deep`, `auto-documents`, `auto-research::data` (+2) | s5-documents-office-content |
| `convert_document` | `portal/modules/documents/tools/document_mcp.py:785` | ACTIVE_UNTESTED | `owui:portal_documents` | — → s5-documents-full-lifecycle |
| `export_pdf` | `portal/modules/documents/tools/document_mcp.py:881` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-documents-full-lifecycle |
| `prepare_embed_image` | `portal/modules/documents/tools/document_mcp.py:891` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-documents-full-lifecycle |
| `list_generated_files` | `portal/modules/documents/tools/document_mcp.py:901` | ACTIVE_UNTESTED | `owui:portal_documents` | — → s5-documents-full-lifecycle |
| `read_word_document` | `portal/modules/documents/tools/document_mcp.py:918` | ACTIVE_TESTED | `auto-general-uncensored`, `auto-daily`, `auto-daily::fast`, `auto-daily::deep`, `auto-daily::nemotron` (+18) | s5-documents-upload-readback-rag |
| `read_excel` | `portal/modules/documents/tools/document_mcp.py:985` | ACTIVE_UNTESTED | `auto-daily`, `auto-daily::fast`, `auto-daily::deep`, `auto-coding::heavy`, `auto-coding::lite` (+4) | — → s5-documents-full-lifecycle |
| `read_powerpoint` | `portal/modules/documents/tools/document_mcp.py:1046` | ACTIVE_UNTESTED | `auto-coding::heavy`, `auto-coding::lite`, `auto-coding::ornith`, `auto-documents`, `agentorchestrator` (+1) | — → s5-documents-full-lifecycle |
| `read_pdf` | `portal/modules/documents/tools/document_mcp.py:1121` | ACTIVE_TESTED | `auto-general-uncensored`, `auto-daily`, `auto-daily::fast`, `auto-daily::deep`, `auto-daily::nemotron` (+19) | s2-p3-auto-documents-pdf-read |

### 6.8 ICS/OT MCP (:8936)

`portal/modules/icsot/tools/icsot_mcp.py` — 4 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `list_ics_protocols` | `portal/modules/icsot/tools/icsot_mcp.py:87` | ACTIVE_UNTESTED | `auto-spl`, `auto-security` | — → s5-security-toolbelt |
| `dissect_pcap` | `portal/modules/icsot/tools/icsot_mcp.py:97` | ACTIVE_UNTESTED | `auto-spl`, `auto-security` | — → s5-security-toolbelt |
| `asset_inventory` | `portal/modules/icsot/tools/icsot_mcp.py:163` | ACTIVE_UNTESTED | `auto-spl`, `auto-security` | — → s5-security-toolbelt |
| `correlate_advisories` | `portal/modules/icsot/tools/icsot_mcp.py:216` | ACTIVE_UNTESTED | `auto-spl`, `auto-security` | — → s5-security-toolbelt |

### 6.9 MFLUX Image MCP (:8933)

`portal/modules/media/tools/mflux_mcp.py` — 4 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `generate_image` | `portal/modules/media/tools/mflux_mcp.py:260` | ACTIVE_TESTED | `auto-vision`, `auto-audio::image`, `agentorchestrator`, `owui:portal_mflux` | s4-auto-audio-image-tools; s4-auto-vision-tools; s5-media-image-quality |
| `edit_image` | `portal/modules/media/tools/mflux_mcp.py:287` | ACTIVE_UNTESTED | `auto-vision`, `auto-audio::image`, `owui:portal_mflux` | — → s5-media-async-poll |
| `image_start` | `portal/modules/media/tools/mflux_mcp.py:323` | ACTIVE_UNTESTED | `auto-vision`, `auto-audio::image`, `owui:portal_mflux` | — → s5-media-async-poll |
| `image_status` | `portal/modules/media/tools/mflux_mcp.py:369` | ACTIVE_UNTESTED | `auto-vision`, `auto-audio::image`, `owui:portal_mflux` | — → s5-media-async-poll |

### 6.10 Music MCP (:8912)

`portal/modules/media/tools/music_mcp.py` — 3 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `music_start` | `portal/modules/media/tools/music_mcp.py:209` | ACTIVE_TESTED | `auto-audio::music`, `owui:portal_music` | s5-media-music-audio |
| `music_status` | `portal/modules/media/tools/music_mcp.py:265` | ACTIVE_UNTESTED | `auto-audio::music`, `owui:portal_music` | — → s5-media-async-poll |
| `music_models` | `portal/modules/media/tools/music_mcp.py:271` | ACTIVE_UNTESTED | `auto-audio::music`, `owui:portal_music` | — → s5-media-async-poll |

### 6.11 TTS MCP (:8916)

`portal/modules/media/tools/tts_mcp.py` — 4 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `speak` | `portal/modules/media/tools/tts_mcp.py:222` | ACTIVE_TESTED | `auto-audio::music`, `agentorchestrator`, `owui:portal_tts` | s5-media-tts-speech |
| `clone_voice` | `portal/modules/media/tools/tts_mcp.py:238` | ACTIVE_TESTED | `auto-audio::music`, `owui:portal_tts` | s2-p6-voice-clone; s5-media-voice-clone |
| `register_voice` | `portal/modules/media/tools/tts_mcp.py:264` | ACTIVE_UNTESTED | `auto-audio::music`, `owui:portal_tts` | — → s5-media-async-poll |
| `list_voices` | `portal/modules/media/tools/tts_mcp.py:287` | ACTIVE_UNTESTED | `auto-audio::music`, `owui:portal_tts` | — → s5-media-async-poll |

### 6.12 Video MLX MCP (:8935)

`portal/modules/media/tools/video_mlx_mcp.py` — 3 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `video_start` | `portal/modules/media/tools/video_mlx_mcp.py:317` | ACTIVE_TESTED | `auto-audio::video`, `owui:portal_video_mlx` | s5-media-video-duration |
| `video_status` | `portal/modules/media/tools/video_mlx_mcp.py:383` | ACTIVE_UNTESTED | `auto-audio::video`, `owui:portal_video_mlx` | — → s5-media-async-poll |
| `video_models` | `portal/modules/media/tools/video_mlx_mcp.py:389` | ACTIVE_UNTESTED | `auto-audio::video`, `owui:portal_video_mlx` | — → s5-media-async-poll |

### 6.13 Whisper MCP (:8915)

`portal/modules/media/tools/whisper_mcp.py` — 2 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `transcribe_audio` | `portal/modules/media/tools/whisper_mcp.py:178` | ACTIVE_TESTED | `auto-daily`, `auto-vision`, `auto-audio`, `auto-audio::music`, `agentorchestrator` (+1) | s5-media-tts-speech |
| `transcribe_with_speakers` | `portal/modules/media/tools/whisper_mcp.py:256` | ACTIVE_TESTED | `auto-audio`, `owui:portal_whisper` | s2-p6-auto-audio-stt; s4-auto-audio-tools; s5-media-stt-accuracy |

### 6.14 Netforensics MCP (:8941)

`portal/modules/netforensics/tools/netforensics_mcp.py` — 4 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `protocol_hierarchy` | `portal/modules/netforensics/tools/netforensics_mcp.py:98` | ACTIVE_UNTESTED | `auto-spl`, `auto-security::pentest`, `auto-security::blueteam` | — → s5-security-toolbelt |
| `extract_fields` | `portal/modules/netforensics/tools/netforensics_mcp.py:133` | ACTIVE_UNTESTED | `auto-spl`, `auto-security::pentest`, `auto-security::blueteam` | — → s5-security-toolbelt |
| `conversations` | `portal/modules/netforensics/tools/netforensics_mcp.py:154` | ACTIVE_UNTESTED | `auto-spl`, `auto-security::pentest`, `auto-security::blueteam` | — → s5-security-toolbelt |
| `recon_scan` | `portal/modules/netforensics/tools/netforensics_mcp.py:172` | ACTIVE_UNTESTED | `auto-security::pentest` | — → s5-security-toolbelt |

### 6.15 Git MCP (:8950, host-native)

`portal/modules/orchestration/mcp/git_mcp.py` — 5 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `git_status` | `portal/modules/orchestration/mcp/git_mcp.py:125` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-jarvis-introspection |
| `git_log` | `portal/modules/orchestration/mcp/git_mcp.py:138` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-jarvis-introspection |
| `git_diff` | `portal/modules/orchestration/mcp/git_mcp.py:169` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-jarvis-introspection |
| `git_commit` | `portal/modules/orchestration/mcp/git_mcp.py:183` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-jarvis-introspection |
| `git_push` | `portal/modules/orchestration/mcp/git_mcp.py:210` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-jarvis-introspection |

### 6.16 Browser MCP / Obscura (:8923)

`portal/modules/research/tools/browser_mcp.py` — 9 tracked rows (8 native defs + 1 REST-only dispatch tool).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `browser_get_markdown` | `portal/modules/research/tools/browser_mcp.py:555` | BROKEN_OR_UNWIRED | `auto-daily::fast`, `auto-coding` | s1-browser-ssrf (REST only) |
| `browser_navigate` | `portal/modules/research/tools/browser_mcp.py:651` | ACTIVE_TESTED | `auto-daily::fast`, `auto-coding`, `owui:portal_browser` | s2-p3-obscura-browser |
| `browser_snapshot` | `portal/modules/research/tools/browser_mcp.py:671` | ACTIVE_TESTED | `auto-daily::fast`, `auto-coding`, `owui:portal_browser` | s2-p3-obscura-browser |
| `browser_click` | `portal/modules/research/tools/browser_mcp.py:682` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding`, `owui:portal_browser` | — → s5-browser-web-research |
| `browser_fill` | `portal/modules/research/tools/browser_mcp.py:696` | ACTIVE_TESTED | `auto-daily::fast`, `auto-coding`, `owui:portal_browser` | s1-browser-redaction (REST) |
| `browser_screenshot` | `portal/modules/research/tools/browser_mcp.py:711` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding`, `owui:portal_browser` | — → s5-browser-web-research |
| `browser_evaluate` | `portal/modules/research/tools/browser_mcp.py:725` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding`, `owui:portal_browser` | — → s5-browser-web-research |
| `browser_close` | `portal/modules/research/tools/browser_mcp.py:739` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding`, `owui:portal_browser` | — → s5-browser-web-research |
| `browser_list_profiles` | `portal/modules/research/tools/browser_mcp.py:754` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding`, `owui:portal_browser` | — → s5-browser-web-research |

### 6.17 RAG MCP (:8921)

`portal/modules/research/tools/rag_mcp.py` — 7 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `kb_ingest` | `portal/modules/research/tools/rag_mcp.py:340` | ACTIVE_UNTESTED | `owui:portal_rag` | — → s5-rag-lifecycle |
| `kb_search` | `portal/modules/research/tools/rag_mcp.py:350` | ACTIVE_TESTED | `auto-daily`, `auto-daily::fast`, `auto-daily::deep`, `auto-daily::nemotron`, `auto-coding::heavy` (+16) | s2-p3-rag-roundtrip; s5-rag-followup |
| `kb_search_all` | `portal/modules/research/tools/rag_mcp.py:360` | ACTIVE_UNTESTED | `auto-research`, `factchecker`, `kbnavigator`, `owui:portal_rag` | — → s5-browser-web-research |
| `kb_list` | `portal/modules/research/tools/rag_mcp.py:368` | ACTIVE_TESTED | `auto-daily`, `auto-daily::fast`, `auto-daily::deep`, `auto-daily::nemotron`, `auto-coding::heavy` (+11) | s2-p3-rag-roundtrip; s5-rag-followup |
| `kb_optimize` | `portal/modules/research/tools/rag_mcp.py:374` | ACTIVE_UNTESTED | `owui:portal_rag` | — → s5-rag-lifecycle |
| `kb_versions` | `portal/modules/research/tools/rag_mcp.py:380` | ACTIVE_UNTESTED | `owui:portal_rag` | — → s5-rag-lifecycle |
| `kb_restore` | `portal/modules/research/tools/rag_mcp.py:386` | ACTIVE_UNTESTED | `owui:portal_rag` | — → s5-rag-lifecycle |

### 6.18 Research / Web Search MCP (:8922)

`portal/modules/research/tools/web_search_mcp.py` — 3 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `web_search` | `portal/modules/research/tools/web_search_mcp.py:441` | ACTIVE_TESTED | `auto-general-uncensored::throwaway`, `auto-general-uncensored::throwaway-gemma4-heretic`, `auto-general-uncensored::throwaway-ornith15`, `auto-daily`, `auto-daily::fast` (+20) | s4-auto-general-uncensored-tools |
| `news_search` | `portal/modules/research/tools/web_search_mcp.py:450` | ACTIVE_UNTESTED | `auto-general-uncensored::throwaway`, `auto-general-uncensored::throwaway-gemma4-heretic`, `auto-general-uncensored::throwaway-ornith15`, `auto-research`, `factchecker` (+3) | — → s5-browser-web-research |
| `web_fetch` | `portal/modules/research/tools/web_search_mcp.py:456` | ACTIVE_UNTESTED | `auto-general-uncensored::throwaway`, `auto-general-uncensored::throwaway-gemma4-heretic`, `auto-general-uncensored::throwaway-ornith15`, `auto-daily`, `auto-daily::fast` (+15) | — → s5-browser-web-research |

### 6.19 Detections MCP (:8932)

`portal/modules/security/tools/detections_mcp.py` — 5 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `spl_search_library` | `portal/modules/security/tools/detections_mcp.py:75` | ACTIVE_UNTESTED | `auto-spl`, `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | — → s5-security-toolbelt |
| `spl_validate_syntax` | `portal/modules/security/tools/detections_mcp.py:128` | ACTIVE_UNTESTED | `auto-spl`, `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | — → s5-security-toolbelt |
| `spl_explain_detection` | `portal/modules/security/tools/detections_mcp.py:165` | ACTIVE_UNTESTED | `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | — → s5-security-toolbelt |
| `spl_techniques_covered` | `portal/modules/security/tools/detections_mcp.py:194` | ACTIVE_UNTESTED | `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | — → s5-security-toolbelt |
| `spl_diff_hypothesis` | `portal/modules/security/tools/detections_mcp.py:211` | ACTIVE_UNTESTED | `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | — → s5-security-toolbelt |

### 6.20 MITRE MCP (:8929)

`portal/modules/security/tools/mitre_mcp.py` — 4 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `mitre_technique_lookup` | `portal/modules/security/tools/mitre_mcp.py:299` | ACTIVE_UNTESTED | `auto-spl`, `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | — → s5-security-toolbelt |
| `mitre_data_sources_for_technique` | `portal/modules/security/tools/mitre_mcp.py:329` | ACTIVE_UNTESTED | `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | — → s5-security-toolbelt |
| `mitre_detections_for_technique` | `portal/modules/security/tools/mitre_mcp.py:392` | ACTIVE_UNTESTED | `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | — → s5-security-toolbelt |
| `mitre_techniques_list` | `portal/modules/security/tools/mitre_mcp.py:425` | ACTIVE_UNTESTED | `arm:portal.yaml.disciplines.detection-engineering`, `arm:orchestration_arm.yaml.disciplines.detection-engineering` | — → s5-security-toolbelt |

### 6.21 Proxmox MCP (:8927)

`portal/modules/security/tools/proxmox_mcp.py` — 36 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `proxmox_list_nodes` | `portal/modules/security/tools/proxmox_mcp.py:150` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_node_status` | `portal/modules/security/tools/proxmox_mcp.py:160` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_cluster_status` | `portal/modules/security/tools/proxmox_mcp.py:176` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_list_vms` | `portal/modules/security/tools/proxmox_mcp.py:191` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_vm_status` | `portal/modules/security/tools/proxmox_mcp.py:207` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_vm_config` | `portal/modules/security/tools/proxmox_mcp.py:224` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_vm_start` | `portal/modules/security/tools/proxmox_mcp.py:241` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_vm_shutdown` | `portal/modules/security/tools/proxmox_mcp.py:263` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_vm_stop` | `portal/modules/security/tools/proxmox_mcp.py:288` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_vm_reset` | `portal/modules/security/tools/proxmox_mcp.py:310` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_vm_reboot` | `portal/modules/security/tools/proxmox_mcp.py:332` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_vm_suspend` | `portal/modules/security/tools/proxmox_mcp.py:357` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_vm_resume` | `portal/modules/security/tools/proxmox_mcp.py:379` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_clone_vm` | `portal/modules/security/tools/proxmox_mcp.py:401` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_delete_vm` | `portal/modules/security/tools/proxmox_mcp.py:439` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_list_snapshots` | `portal/modules/security/tools/proxmox_mcp.py:472` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_create_snapshot` | `portal/modules/security/tools/proxmox_mcp.py:489` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_rollback_snapshot` | `portal/modules/security/tools/proxmox_mcp.py:527` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_delete_snapshot` | `portal/modules/security/tools/proxmox_mcp.py:555` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_exec_vm` | `portal/modules/security/tools/proxmox_mcp.py:588` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_vm_agent_info` | `portal/modules/security/tools/proxmox_mcp.py:635` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_list_containers` | `portal/modules/security/tools/proxmox_mcp.py:660` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_container_status` | `portal/modules/security/tools/proxmox_mcp.py:676` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_container_start` | `portal/modules/security/tools/proxmox_mcp.py:693` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_container_stop` | `portal/modules/security/tools/proxmox_mcp.py:708` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_container_shutdown` | `portal/modules/security/tools/proxmox_mcp.py:723` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_container_exec` | `portal/modules/security/tools/proxmox_mcp.py:740` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_list_storage` | `portal/modules/security/tools/proxmox_mcp.py:768` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_list_storage_content` | `portal/modules/security/tools/proxmox_mcp.py:784` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_list_networks` | `portal/modules/security/tools/proxmox_mcp.py:806` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_task_status` | `portal/modules/security/tools/proxmox_mcp.py:827` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_list_tasks` | `portal/modules/security/tools/proxmox_mcp.py:845` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_list_all_vms` | `portal/modules/security/tools/proxmox_mcp.py:871` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_find_vm` | `portal/modules/security/tools/proxmox_mcp.py:884` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_node_exec` | `portal/modules/security/tools/proxmox_mcp.py:952` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |
| `proxmox_deploy_ctf_lab` | `portal/modules/security/tools/proxmox_mcp.py:966` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding` | — → s5-proxmox-readonly |

### 6.22 Security Review MCP (:8943)

`portal/modules/security/tools/review_mcp.py` — 13 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `review_start` | `portal/modules/security/tools/review_mcp.py:101` | ACTIVE_UNTESTED | `security-reviewer`, `owui:portal_review` | — → s5-review-queue |
| `review_status` | `portal/modules/security/tools/review_mcp.py:132` | ACTIVE_UNTESTED | `security-reviewer`, `owui:portal_review` | — → s5-review-queue |
| `review_result` | `portal/modules/security/tools/review_mcp.py:143` | ACTIVE_UNTESTED | `security-reviewer`, `owui:portal_review` | — → s5-review-queue |
| `review_cancel` | `portal/modules/security/tools/review_mcp.py:159` | ACTIVE_UNTESTED | `security-reviewer`, `owui:portal_review` | — → s5-review-queue |
| `review_verdict` | `portal/modules/security/tools/review_mcp.py:167` | ACTIVE_UNTESTED | `security-reviewer`, `owui:portal_review` | — → s5-review-queue |
| `review_queue` | `portal/modules/security/tools/review_mcp.py:183` | ACTIVE_UNTESTED | `security-reviewer`, `owui:portal_review` | — → s5-review-queue |
| `review_explain` | `portal/modules/security/tools/review_mcp.py:195` | ACTIVE_UNTESTED | `security-reviewer`, `owui:portal_review` | — → s5-review-queue |
| `review_doctor` | `portal/modules/security/tools/review_mcp.py:201` | ACTIVE_UNTESTED | `security-reviewer`, `owui:portal_review` | — → s5-review-queue |
| `hunt_sources` | `portal/modules/security/tools/review_mcp.py:213` | ACTIVE_TESTED | `security-reviewer`, `owui:portal_review` | s5-security-hunt-workflow |
| `hunt_start` | `portal/modules/security/tools/review_mcp.py:248` | ACTIVE_TESTED | `security-reviewer`, `owui:portal_review` | s5-security-hunt-workflow |
| `hunt_status` | `portal/modules/security/tools/review_mcp.py:298` | ACTIVE_TESTED | `security-reviewer`, `owui:portal_review` | s5-security-hunt-workflow |
| `hunt_leads` | `portal/modules/security/tools/review_mcp.py:305` | ACTIVE_TESTED | `security-reviewer`, `owui:portal_review` | s5-security-hunt-workflow |
| `hunt_case` | `portal/modules/security/tools/review_mcp.py:330` | ACTIVE_UNTESTED | `security-reviewer`, `owui:portal_review` | — → s5-review-queue |

### 6.23 Security MCP (:8919)

`portal/modules/security/tools/security_mcp.py` — 2 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `classify_vulnerability` | `portal/modules/security/tools/security_mcp.py:86` | ACTIVE_UNTESTED | `auto-coding::heavy`, `auto-coding::lite`, `auto-coding::ornith`, `auto-spl`, `auto-security` (+5) | — → s5-security-toolbelt |
| `lab_perception` | `portal/modules/security/tools/security_mcp.py:126` | ACTIVE_UNTESTED | `owui:portal_security` | — → s5-security-toolbelt |

### 6.24 Vulnintel MCP (:8934)

`portal/modules/vulnintel/tools/vulnintel_mcp.py` — 7 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `lookup_cve` | `portal/modules/vulnintel/tools/vulnintel_mcp.py:132` | ACTIVE_TESTED | `auto-spl`, `auto-security`, `auto-compliance` | s4-auto-security-tools |
| `get_epss` | `portal/modules/vulnintel/tools/vulnintel_mcp.py:182` | ACTIVE_UNTESTED | `auto-spl`, `auto-security`, `auto-compliance` | — → s5-security-toolbelt |
| `check_kev` | `portal/modules/vulnintel/tools/vulnintel_mcp.py:207` | ACTIVE_UNTESTED | `auto-spl`, `auto-security`, `auto-compliance` | — → s5-security-toolbelt |
| `scan_dependencies` | `portal/modules/vulnintel/tools/vulnintel_mcp.py:221` | ACTIVE_UNTESTED | `auto-spl`, `auto-security`, `auto-compliance` | — → s5-security-toolbelt |
| `ics_advisories` | `portal/modules/vulnintel/tools/vulnintel_mcp.py:258` | ACTIVE_UNTESTED | `auto-spl`, `auto-security`, `auto-compliance` | — → s5-security-toolbelt |
| `lookup_ioc` | `portal/modules/vulnintel/tools/vulnintel_mcp.py:302` | ACTIVE_UNTESTED | `auto-spl`, `auto-security` | — → s5-security-toolbelt |
| `triage_cve` | `portal/modules/vulnintel/tools/vulnintel_mcp.py:341` | ACTIVE_UNTESTED | `auto-spl`, `auto-security`, `auto-compliance` | — → s5-security-toolbelt |

### 6.25 Pipeline MCP (:8928)

`portal/platform/mcp_host/pipeline_mcp.py` — 13 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `get_pipeline_status` | `portal/platform/mcp_host/pipeline_mcp.py:103` | ACTIVE_UNTESTED | `auto-daily::fast` | — → s5-jarvis-introspection |
| `list_workspaces` | `portal/platform/mcp_host/pipeline_mcp.py:135` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-jarvis-introspection |
| `get_loaded_models` | `portal/platform/mcp_host/pipeline_mcp.py:167` | ACTIVE_UNTESTED | `auto-daily::fast` | — → s5-jarvis-introspection |
| `get_metrics_summary` | `portal/platform/mcp_host/pipeline_mcp.py:200` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-jarvis-introspection |
| `get_workspace_recommendation` | `portal/platform/mcp_host/pipeline_mcp.py:302` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-jarvis-introspection |
| `explore_repository` | `portal/platform/mcp_host/pipeline_mcp.py:450` | ACTIVE_UNTESTED | `auto-coding::laguna`, `auto-coding::uncensored-agentic`, `auto-coding::fast-repair`, `owui:pipeline_native` | — → s5-jarvis-introspection |
| `trigger_backend_warmup` | `portal/platform/mcp_host/pipeline_mcp.py:487` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-jarvis-introspection |
| `jarvis_submit` | `portal/platform/mcp_host/pipeline_mcp.py:509` | ACTIVE_UNTESTED | `orchestration:owui_entry` | — → s5-jarvis-introspection |
| `arm_queue_task` | `portal/platform/mcp_host/pipeline_mcp.py:547` | ACTIVE_UNTESTED | `orchestration:owui_entry` | — → s5-jarvis-introspection |
| `read_text_file` | `portal/platform/mcp_host/pipeline_mcp.py:612` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding::laguna`, `owui:pipeline_native` | — → s5-jarvis-introspection |
| `list_directory` | `portal/platform/mcp_host/pipeline_mcp.py:647` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding::laguna`, `owui:pipeline_native` | — → s5-jarvis-introspection |
| `search_files` | `portal/platform/mcp_host/pipeline_mcp.py:694` | ACTIVE_UNTESTED | `auto-daily::fast`, `auto-coding::laguna`, `owui:pipeline_native` | — → s5-jarvis-introspection |
| `write_file` | `portal/platform/mcp_host/pipeline_mcp.py:724` | ACTIVE_UNTESTED | `auto-coding::laguna`, `owui:pipeline_native` | — → s5-jarvis-introspection |

### 6.26 Memory MCP (:8920)

`portal/platform/memory/memory_mcp.py` — 9 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `remember` | `portal/platform/memory/memory_mcp.py:105` | ACTIVE_TESTED | `auto-general-uncensored`, `auto-general-uncensored::throwaway`, `auto-general-uncensored::throwaway-gemma4-heretic`, `auto-general-uncensored::throwaway-ornith15`, `auto-daily` (+23) | s2-p4-memory-roundtrip; s4-auto-daily-tools; s4-auto-daily-nemotron-tools; s5-memory-cross-session |
| `recall` | `portal/platform/memory/memory_mcp.py:116` | ACTIVE_TESTED | `auto-general-uncensored`, `auto-general-uncensored::throwaway`, `auto-general-uncensored::throwaway-gemma4-heretic`, `auto-general-uncensored::throwaway-ornith15`, `auto-daily` (+24) | s2-p4-memory-roundtrip; s5-memory-cross-session |
| `graph_recall` | `portal/platform/memory/memory_mcp.py:133` | ACTIVE_UNTESTED | `auto-research` | — → s5-memory-graph-admin |
| `link` | `portal/platform/memory/memory_mcp.py:139` | BROKEN_OR_UNWIRED | none (operator/agent surface) | see §11 |
| `neighbors` | `portal/platform/memory/memory_mcp.py:149` | ACTIVE_UNTESTED | `auto-research` | — → s5-memory-graph-admin |
| `entity_timeline` | `portal/platform/memory/memory_mcp.py:155` | ACTIVE_UNTESTED | `auto-research` | — → s5-memory-graph-admin |
| `forget` | `portal/platform/memory/memory_mcp.py:161` | ACTIVE_UNTESTED | `personalassistant`, `owui:portal_memory` | — → s5-memory-graph-admin |
| `list_memories` | `portal/platform/memory/memory_mcp.py:167` | ACTIVE_UNTESTED | `personalassistant`, `owui:portal_memory` | — → s5-memory-graph-admin |
| `clear_memories` | `portal/platform/memory/memory_mcp.py:180` | ACTIVE_UNTESTED | `owui:portal_memory` | — → s5-memory-graph-admin |

### 6.27 Wiki MCP (:8931)

`portal_wiki/wiki_mcp.py` — 3 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `wiki_search` | `portal_wiki/wiki_mcp.py:56` | ACTIVE_UNTESTED | `jarvis:personal_tools` | — → s5-jarvis-introspection |
| `wiki_get_unit` | `portal_wiki/wiki_mcp.py:73` | ACTIVE_UNTESTED | `jarvis:personal_tools` | — → s5-jarvis-introspection |
| `wiki_explain` | `portal_wiki/wiki_mcp.py:89` | ACTIVE_UNTESTED | none (operator/agent surface) | — → s5-jarvis-introspection |

### 6.28 MLX Transcribe MCP (:8924, host-native)

`scripts/mlx-transcribe.py` — 2 tool(s).

| tool | file:line | bucket | wiring | QAT scenario / Stage 5 target |
|---|---|---|---|---|
| `transcribe_audio` | `scripts/mlx-transcribe.py:1106` | ACTIVE_TESTED | `auto-daily`, `auto-vision`, `auto-audio`, `auto-audio::music`, `agentorchestrator` (+1) | s5-media-tts-speech |
| `transcribe_with_speakers` | `scripts/mlx-transcribe.py:1137` | ACTIVE_TESTED | `auto-audio`, `owui:portal_whisper` | s2-p6-auto-audio-stt; s4-auto-audio-tools; s5-media-stt-accuracy |

### 6.29 Module notes

- **Compliance (43 defs):** 35 wired into `auto-compliance` / `::reading`; 8 served but
  ungranted (`compliance_analyze`, `compliance_bundle`, `compliance_change_impact`,
  `compliance_gaps`, `compliance_impact`, `compliance_kb_search`, `compliance_prospective`,
  `compliance_scenario`) — all remain in the discovery manifest and `_DISPATCH`, with active
  eval/script callers (§14). `compliance_gaps` is the retiring coverage path, deliberately
  retained for the acceptance comparison (`scripts/compliance_acceptance.py:279`).
- **Duplicate names:** `transcribe_audio` / `transcribe_with_speakers` exist on both whisper
  (:8915, compose) and mlx-transcribe (:8924, host). The registry's `_resolve_duplicates`
  picks one server per name; both definitions are tracked and both are ACTIVE_TESTED via
  s5-media-tts-speech / s5-media-stt-accuracy.
- **Memory:** `register_memory_routes` (graph_memory.py:727) also publishes REST
  `/tools/*` routes; the native `@mcp.tool` surface (9 tools) is what the Pipeline dispatches.
- **Pipeline MCP:** `jarvis_submit` / `arm_queue_task` delegate to the orchestration module
  (`portal/modules/orchestration/owui_entry.py:41,79`, registered in plugin.py:24-25); they
  are live while the orchestration module is enabled (it is at HEAD) and return a build
  error when it is not. The introspection tools (list_workspaces, get_metrics_summary,
  get_workspace_recommendation, trigger_backend_warmup) are agent/operator surface.
- **Sandbox / documents / rag / cad / compliance / mlx-transcribe** call `align_native_tools`,
  which republishes manifest metadata only for already-registered native tools — a manifest
  entry without a native def is silently dropped (this is how `browser_get_markdown` stays
  invisible to the native registry while sitting in the browser manifest).

## 7. External MCP Surfaces

### 7.1 UniFi Network MCP (external, bridged :8949)

The operator's `sirkirby unifi-network-mcp` pinned **0.40.0** (`~/mcp/unifi-network/run.sh`)
declares **210 tools** in its own `tools_manifest.json` (read from the uvx cache of
the exact pinned version). Portal wires **14** of them into `auto-coding` and
`auto-daily::fast` (config/portal.yaml:1118-1131, 1313-1326): the 3 lazy-mode meta-tools
(`unifi_tool_index`, `unifi_load_tools`, `unifi_execute`) plus 11 read-only domain tools.
Every `unifi_*` call is confirm-gated for Jarvis (personal_policy). The remaining ~196
package tools are reachable through `unifi_execute` lazy loading but are not individually
granted; they are external package surface, not Portal definitions. QAT:
s2-p3-unifi-readonly probes /health only → all 14 wired tools are ACTIVE_UNTESTED
(journey s5-jarvis-introspection). The full 210-name list is preserved in the audit scratch
(`coding_task/scratch/unifi_manifest_tools.json`, gitignored) and summarized here:

| wired unifi tool | granting seats | bucket | QAT |
|---|---|---|---|
| `unifi_execute` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |
| `unifi_get_client_details` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |
| `unifi_get_dashboard` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |
| `unifi_get_device_details` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |
| `unifi_get_network_health` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |
| `unifi_get_system_info` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |
| `unifi_get_wlan_details` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |
| `unifi_list_alarms` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |
| `unifi_list_clients` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |
| `unifi_list_devices` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |
| `unifi_list_networks` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |
| `unifi_list_wlans` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |
| `unifi_load_tools` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |
| `unifi_tool_index` | `auto-coding`, `auto-daily::fast` | ACTIVE_UNTESTED | — → s5-jarvis-introspection |

### 7.2 Browser MCP REST-only surface

`browser_get_markdown` — tracked in §6.16 as BROKEN_OR_UNWIRED. It exists only as a REST
dispatch branch (browser_mcp.py:555) and in `config/inference/tools_manifest_browser_mcp.json`
(9 entries vs 8 native defs). Internal caller: `web_search_mcp.py:70` (`web_fetch` A2 fallback).
QAT covers the REST branch (s1-browser-ssrf); the workspace grants are phantom (§11).

### 7.3 IDE-only stdio MCPs (expose_to_pipeline: false)

Not model-callable from the Pipeline; available to Claude Code / opencode via `.mcp.json`.
Tool surfaces verified from the local package caches where available:

| fleet id | package | tools (verified) | QAT |
|---|---|---|---|
| filesystem | @modelcontextprotocol/server-filesystem@2.4.0 | 13: read_file, read_text_file, read_media_file, read_multiple_files, write_file, edit_file, create_directory, list_directory, directory_tree, move_file, search_files, get_file_info, list_allowed_directories | out of pipeline scope |
| fetch | mcp-fetch (uvx) | 1: fetch | out of pipeline scope |
| git (IDE arm) | mcp-server-git (uvx) | 12: git_status, git_diff_unstaged, git_diff_staged, git_diff, git_commit, git_add, git_reset, git_log, git_create_branch, git_checkout, git_show, git_branch | out of pipeline scope (host git MCP :8950 is the Pipeline arm, §6.15) |
| docker | mcp-docker-server@1.0.1 | list_images verified; full surface unverified (minified dist) | out of pipeline scope |
| context7 | @upstash/context7-mcp@4.7.3 | get-library-docs verified; resolve-library-docs unverified in cached build | out of pipeline scope |

## 8. Pipeline HTTP Endpoints (23)

All routes bound in `portal/platform/inference/router/app.py:55-77`. SSE streaming is the
`stream=true` arm of `/v1/chat/completions` (live gate: `scripts/smoke_stream.sh`).

| method | path | binding | QAT coverage | bucket |
|---|---|---|---|---|
| GET | `/health` | app.py:55 | gate-pipeline (Stage 0 cold-start gate) | ACTIVE_TESTED |
| GET | `/health/all` | app.py:56 | s1-health-all | ACTIVE_TESTED |
| POST | `/admin/refresh-tools` | app.py:57 | — (unit: test_pipeline_hardening et al.) | ACTIVE_UNTESTED |
| POST | `/admin/load-plan` | app.py:58 | — (unit-covered) | ACTIVE_UNTESTED |
| POST | `/admin/seat-fit` | app.py:59 | — (unit-covered) | ACTIVE_UNTESTED |
| POST | `/admin/reclaim-idle` | app.py:60 | — (unit: test_admin_reclaim_idle.py) | ACTIVE_UNTESTED |
| POST | `/ollama/api/chat` | app.py:61 | — (passthrough; unit-covered) | ACTIVE_UNTESTED |
| POST | `/ollama/api/generate` | app.py:62 | — (passthrough; unit-covered) | ACTIVE_UNTESTED |
| POST | `/ollama/api/embed` | app.py:63 | — (passthrough; unit-covered) | ACTIVE_UNTESTED |
| GET | `/ollama/api/ps` | app.py:64 | — (passthrough; unit-covered) | ACTIVE_UNTESTED |
| GET | `/ollama/api/tags` | app.py:65 | — (passthrough; unit-covered) | ACTIVE_UNTESTED |
| POST | `/ollama/api/show` | app.py:66 | — (passthrough; unit-covered) | ACTIVE_UNTESTED |
| POST | `/notifications/test` | app.py:67 | — | ACTIVE_UNTESTED |
| POST | `/admin/notifications/daily-summary` | app.py:68 | — | ACTIVE_UNTESTED |
| GET | `/metrics` | app.py:69 | s1-metrics (power+energy gauges) | ACTIVE_TESTED |
| GET | `/v1/models` | app.py:70 | — (QAT reads OWUI /api/v1/models, not this route) | ACTIVE_UNTESTED |
| GET | `/v1/tools` | app.py:71 | — | ACTIVE_UNTESTED |
| GET | `/v1/backends` | app.py:72 | — | ACTIVE_UNTESTED |
| POST | `/v1/chat/completions` | app.py:73 | s1-auth; s1-neg-{empty-prompt,oversized-prompt,invalid-slug,malformed-json}; s3-canonical pipeline seats; every OWUI turn indirectly; smoke_stream.sh | ACTIVE_TESTED |
| POST | `/v1/embeddings` | app.py:74 | — (unit: test_embeddings_route.py) | ACTIVE_UNTESTED |
| POST | `/v1/messages` | app.py:75 | — (Anthropic compat; unit-covered) | ACTIVE_UNTESTED |
| GET | `/v1/trace` | app.py:76 | owui_client.lookup_trace — grading evidence for chat scenarios | ACTIVE_TESTED |
| GET | `/v1/trace/{correlation_id}` | app.py:77 | owui_client._trace_detail — tool-span grading | ACTIVE_TESTED |

6/23 endpoints are QAT-exercised; 17 are ACTIVE_UNTESTED (most are unit-covered; the QAT
gap is the live HTTP contract). Host-service HTTP surfaces (not Pipeline routes):
mlx-speech :8918 (`/health`, `/v1/audio/speech`, `/v1/audio/transcriptions`, `/v1/models`,
`/v1/voices` GET/POST/DELETE — scripts/mlx-speech.py:480-840; speech is QAT-exercised via
s2-p6-auto-audio-tts and s5-media-tts-speech), mlx-transcribe :8924 (`/health`, `/tools`,
`/tools/{name}`, `/files/{name}`, `/v1/audio/transcriptions`, `/v1/audio/transcribe-with-speakers`
— scripts/mlx-transcribe.py:846-1053), vl-retrieval :8942 and eg2-embedding :8946
(platform embedder/reranker, consumed internally).

## 9. Open WebUI GUI Controls (15)

Browser layer: `tests/qat/browser_ui.py` + `runner._run_browser` (only s2-p1-ui-roster is a
browser scenario today). API layer: `tests/qat/owui_client.py`. "Browser-covered" means a
real Playwright interaction; API-covered means the OWUI REST contract is exercised.

| # | control | implementation anchor | coverage | bucket |
|---|---|---|---|---|
| 1 | Login / auth | BrowserUI.login (browser_ui.py:85) | browser-covered (every _run_browser) | ACTIVE_TESTED |
| 2 | Release-notes overlay dismissal | BrowserUI.dismiss_overlays (browser_ui.py:93) | browser-covered | ACTIVE_TESTED |
| 3 | Model/workspace selector roster | BrowserUI.workspace_roster (browser_ui.py:122) | s2-p1-ui-roster (24 presets asserted) | ACTIVE_TESTED |
| 4 | Chat input send + Stop control | BrowserUI.send_turn (browser_ui.py:170) | browser-covered (stop-circle wait) | ACTIVE_TESTED |
| 5 | Reasoning <details> toggle | BrowserUI.toggle_details (browser_ui.py:212) | exercised in _run_browser; result NOT asserted (runner.py:1058,1068) | ACTIVE_TESTED (weak) |
| 6 | File upload / RAG attachment via GUI input | BrowserUI.send_turn upload_path (browser_ui.py:175) | GUI path never passed by _run_browser; API upload covered (attachments in s2-p3/s5); kb_list/kb_search API-tested, GUI knowledge attachment untested | ACTIVE_UNTESTED (GUI) |
| 7 | Web search toggle | owui_client.send_turn features.web_search (owui_client.py:218) | always False in QAT; no scenario enables it | ACTIVE_UNTESTED |
| 8 | Tool toggles / integrations menu | tool_ids per scenario (API) | API tool_ids granted per preset; GUI menu never opened | ACTIVE_UNTESTED (GUI) |
| 9 | TTS playback / speech control | runner._run_tts (runner.py:842) | API /api/v1/audio/speech covered (s2-p6-auto-audio-tts); GUI button untested | ACTIVE_UNTESTED (GUI) |
| 10 | STT mic / audio capture | chat attachments (API) | transcribe tools covered via uploaded WAV; GUI mic untested | ACTIVE_UNTESTED (GUI) |
| 11 | Artifact download link click | owui_client.download_artifact (owui_client.py:309) | API download + byte validation covered; GUI link click untested | ACTIVE_UNTESTED (GUI) |
| 12 | Multi-turn history persistence (reload) | s4-*-continuity (API) | API continuity + s5 cross-session memory; GUI reload persistence untested | ACTIVE_UNTESTED (GUI) |
| 13 | Persona selector | persona slugs as OWUI models | API persona turns (s2-p5, s5-persona-*); GUI selection untested | ACTIVE_UNTESTED (GUI) |
| 14 | Chat management (rename/archive/delete/folders) | owui_client.py:483-543 | exercised for run hygiene (_archive_chat), not graded | ACTIVE_UNTESTED |
| 15 | Admin settings / seeding panel | scripts/openwebui_init.py | p0-exposure-gap audits roster parity; GUI admin panel untested | ACTIVE_UNTESTED |

## 10. Channel Adapters (portal_channels/)

No QAT scenario exercises either adapter (zero telegram/slack references in tests/qat/).
Unit coverage: tests/unit/test_channels.py, test_telegram_jarvis_control.py,
test_thinking_channels.py. All channel features below are ACTIVE_UNTESTED in QAT
(journey s5-channels-telegram-slack).

| adapter | feature | anchor | QAT |
|---|---|---|---|
| Telegram | /start help | bot.py:132 | — |
| Telegram | /clear history | bot.py:151 | — |
| Telegram | /workspace <name> switch | bot.py:166 | — |
| Telegram | /workspaces list | bot.py:159 | — |
| Telegram | /jarvis verbs (status, digest, pause, resume, requeue, cancel, canary, held, merge, keep, escalate, do, help) | jarvis_control.py:35-51 | — |
| Telegram | plain-text chat w/ 20-msg/24h history | bot.py:203 | — |
| Telegram | arm Approve/Deny inline callback | bot.py:58,309 | — |
| Telegram | jarvis confirm callback (jv:) | bot.py:310 | — |
| Telegram | user allowlist | bot.py:48-55 | — |
| Slack | @mention → channel→workspace routing | slack/bot.py:94 | — |
| Slack | DM handling | slack/bot.py:116 | — |
| Slack | thread replies | slack/bot.py:107 | — |
| Slack | CHANNEL_WORKSPACE_MAP (13 channels) | slack/bot.py:33-47 | — |
| shared | dispatcher retry/backoff, sync+async | dispatcher.py:127,186 | — |

**Channel findings (report-only; Lane B fixes):**

1. `dispatcher.py:31-111` `VALID_WORKSPACES` is a hardcoded 50-name roster that has drifted:
   10 entries are aliases expiring 2026-12-31 (`auto-video`, `auto-image`, `auto-music`,
   `auto-math`, `general-fast`, `general-deep`, `auto-nemotron`, `auto-bigfix`, `auto-cad`,
   `compliance-reading`), 13 are bench ids, 6 are variant ids; `task-router` is absent
   (intentional, eval). Current variants without aliases (e.g. `auto-coding::laguna`,
   `auto-coding::cad`) are rejected by Telegram `/workspace` (`is_valid_workspace`).
2. `slack/bot.py:38,44` routes `video`→`auto-video` and `music`→`auto-music` with no variant —
   these resolve only through the expiring aliases; after 2026-12-31 those Slack channels
   break unless repointed to `auto-audio::video` / `auto-audio::music`.
3. `telegram/bot.py:139-145` /start help text lists a stale workspace/variant subset.

## 11. Actionable Fix List (BROKEN_OR_UNWIRED)

| # | item | exact location | defect | recommended fix |
|---|---|---|---|---|
| F1 | `browser_get_markdown` phantom native reference | grants: config/portal.yaml:1074 (`auto-daily::fast`), config/portal.yaml:1269 (`auto-coding`); manifest: config/inference/tools_manifest_browser_mcp.json (9th entry); REST-only handler: portal/modules/research/tools/browser_mcp.py:555; internal caller: portal/modules/research/tools/web_search_mcp.py:70 | Listed in two workspace tool lists and the discovery manifest, but has NO `@mcp.tool` definition. The Pipeline registry discovers/dispatches native MCP only (tool_registry.py:65,625), and `align_native_tools` drops manifest entries without a native def (tool_support.py:46) — a model calling it gets a registry miss. The REST branch itself is live (web_fetch fallback, s1-browser-ssrf). | Either add `@mcp.tool() async def browser_get_markdown(url: str)` wrapping the existing REST logic (obscura_fetch_markdown + the same URL gate), or remove the name from both workspace tool lists and the manifest and document it as internal-only. Lane B decision; do not silently keep the phantom. |
| F2 | `link` graph write tool never granted | def: portal/platform/memory/memory_mcp.py:139-140; REST route: portal/platform/memory/graph_memory.py:734; sibling grants: config/portal.yaml `auto-research.tools` grants `graph_recall`, `neighbors`, `entity_timeline` but not `link`; docstring contract: memory_mcp.py:11 groups all four as the graph surface | Defined, served, manifest-listed, but absent from every workspace/persona/OWUI/arm grant. No document records an intentional exclusion (contrast `generate_scad`, which is documented as deliberately unseated). The graph read tools are granted to auto-research; the write counterpart is unreachable from chat. | Grant `link` to `auto-research` (write-side of the graph surface) or document it as operator-only in unit-capability-memory. Confirm intent before wiring — flagged for Lane B / orchestrator judgement. |

Adjacent wiring observations (not bucketed as broken because intent is documented or the
surface is operator-facing): `generate_scad` deliberately unseated since
TASK_CAD_ARM_REDEVELOP_V1 (unit-module-cad.md:104-108); `list_sessions`/`reset_session`
documented sandbox lifecycle tools with no chat grant; `prepare_embed_image` has zero
callers anywhere (purge candidate, §12 watch).

## 12. Actionable Purge List (STALE_DEAD)

Zero tool definitions are stale-dead at HEAD. Two non-tool artifacts have zero callers:

| # | artifact | exact location | caller analysis | safe-to-purge verdict |
|---|---|---|---|---|
| P1 | Scrapling MCP launcher | portal_mcp/scrapling/launch_scrapling.sh (whole file, 33 lines) | 0 callers repo-wide (grep across *.py/*.sh/*.yaml/*.json/*.toml; only self-reference + a directory mention in docs/BREAKER_V1_MIGRATION_PLAN.md:112). No mcp_fleet entry, no compose service, no launchd plist in deploy/launchd/, no launch.sh hook. Launches on :8900 — outside the reserved port roster. The browser stack migrated to Obscura (TASK_BROWSER_OBSCURA_MIGRATION_V1); scrapling is not in any Dockerfile or dependency. | YES — dead launcher for an unwired server. Purge before the BREAKER rename so the dead file is not carried into breaker_mcp/. Lane B confirms. |
| P2 | Filesystem MCP config fragment | portal_mcp/filesystem/config.toml (whole file, 1 line) | 0 references repo-wide. The fleet `filesystem` entry launches `npx @modelcontextprotocol/server-filesystem@2.4.0 ${HOME}/projects /tmp` with explicit directory args (config/portal.yaml:363-365); nothing reads this config.toml (allowedDirectories=["/tmp"]). | YES — orphaned config fragment. Lane B confirms; keep the fleet entry itself (live IDE surface). |

**Purge watch (not safe-to-purge today):** `prepare_embed_image`
(portal/modules/documents/tools/document_mcp.py:891) — zero callers, but documented in
unit-capability-documents.md:37 and advertised in the manifest; needs an operator decision,
not a silent delete. `scripts/_archive/` is intentional archived history, not purge-listed.

## 13. Stage 5 Browser-GUI UAT Expansion Blueprint

Every ACTIVE_UNTESTED tool is assigned to exactly one primary journey below (the `→` target
in §6). Journeys are multi-turn, browser-GUI where the feature is user-facing, and graded
by real artifact/trace evidence — never format-only. Operator-only surfaces (RAG lifecycle,
compliance engine, proxmox writes, git/unifi confirm gates) run as API/CLI journeys with
explicit confirm-gate assertions, not chat prompts against production state.

### s5-gui-persona-roster — GUI login → persona selector → roster parity

Browser journey: login, dismiss overlays, open the model selector, verify all 24 presets plus the seeded persona models, select 3 untested personas (e.g. networkengineer, statistician, techwriter) and run a role-fit turn each. Closes the 92-persona dedicated-coverage gap incrementally.

### s5-browser-web-research — Research toolbelt beyond navigate/snapshot

auto-research / auto-coding: web_fetch on a bot-challenged page (exercises the browser_get_markdown REST fallback internally), news_search, kb_search_all; then Obscura browser_click, browser_fill, browser_screenshot, browser_evaluate, browser_close, browser_list_profiles on a local fixture page.

Covers (9): `web_fetch`, `news_search`, `kb_search_all`, `browser_click`, `browser_fill`, `browser_screenshot`, `browser_evaluate`, `browser_close`, `browser_list_profiles`.

### s5-sandbox-lifecycle — Sandbox session lifecycle + polyglot execution

auto-coding: execute_nodejs and execute_powershell markers, sandbox_status, then list_sessions / reset_session (operator surface — assert session reset clears state).

Covers (5): `execute_nodejs`, `execute_powershell`, `sandbox_status`, `list_sessions`, `reset_session`.

### s5-documents-full-lifecycle — Documents: read-back, conversion, PDF export, file listing

auto-documents: create_excel + create_powerpoint then read_excel / read_powerpoint quote-back; convert_document DOCX→PDF; export_pdf direct; list_generated_files; prepare_embed_image spec into a Word image embed. GUI: click the rendered download links and upload the produced file back through the chat input.

Covers (6): `read_excel`, `read_powerpoint`, `convert_document`, `export_pdf`, `list_generated_files`, `prepare_embed_image`.

### s5-memory-graph-admin — Memory graph reads + admin lifecycle

auto-research: graph_recall, neighbors, entity_timeline over a seeded entity; link (after Lane B wires it) then verify the edge via neighbors; auto-daily: forget / list_memories / clear_memories with the confirm token on a QAT-scoped store.

Covers (7): `graph_recall`, `neighbors`, `entity_timeline`, `link`, `forget`, `list_memories`, `clear_memories`.

### s5-rag-lifecycle — RAG operator lifecycle

Operator journey on portal-rag: kb_ingest a fixture corpus, kb_optimize, kb_versions, kb_restore to the prior version, then kb_search proves the rollback. Never runs against the production KB root.

Covers (4): `kb_ingest`, `kb_optimize`, `kb_versions`, `kb_restore`.

### s5-media-async-poll — Media async start/status + voice profile management

auto-audio::image: image_start then poll image_status to completion; edit_image on the result. auto-audio::video: video_status / video_models. auto-audio::music: music_status / music_models; register_voice then list_voices shows the profile, speak with it, then delete via the host API.

Covers (9): `image_start`, `image_status`, `edit_image`, `video_status`, `video_models`, `music_status`, `music_models`, `register_voice`, `list_voices`.

### s5-cad-openscad-fallback — CAD: BREP primary + OpenSCAD fallback + measurement

auto-coding::cad: generate_part then cad_execute / cad_measure / cad_find_holes on the solid; render_mesh, render_openscad, convert_cad round-trip; generate_scad via the registered fallback surface (REST or after wiring decision).

Covers (8): `generate_part`, `cad_execute`, `cad_measure`, `cad_find_holes`, `render_mesh`, `render_openscad`, `convert_cad`, `generate_scad`.

### s5-security-toolbelt — Security analyst toolbelt sweep

auto-security / auto-spl: classify_vulnerability on a fixture finding; lookup_cve / get_epss / check_kev / triage_cve / scan_dependencies / lookup_ioc on CVE-2021-44228; ics_advisories / list_ics_protocols / dissect_pcap / asset_inventory / correlate_advisories on the lab pcap; mitre_technique_lookup / mitre_data_sources_for_technique / mitre_detections_for_technique / mitre_techniques_list; spl_search_library / spl_validate_syntax / spl_explain_detection / spl_techniques_covered / spl_diff_hypothesis; query_windows_events; lab_perception on the lab CIDR; netforensics protocol_hierarchy / extract_fields / conversations on the lab pcap and recon_scan (read-only) against the lab CIDR; detection convert_sigma / validate_sigma / compile_yara / scan_yara on a fixture Sigma rule and YARA scan of a lab sample.

Covers (30): `classify_vulnerability`, `get_epss`, `check_kev`, `triage_cve`, `scan_dependencies`, `lookup_ioc`, `ics_advisories`, `list_ics_protocols`, `dissect_pcap`, `asset_inventory`, `correlate_advisories`, `mitre_technique_lookup`, `mitre_data_sources_for_technique`, `mitre_detections_for_technique`, `mitre_techniques_list`, `spl_search_library`, `spl_validate_syntax`, `spl_explain_detection`, `spl_techniques_covered`, `spl_diff_hypothesis`, `query_windows_events`, `lab_perception`, `protocol_hierarchy`, `extract_fields`, `conversations`, `recon_scan`, `convert_sigma`, `validate_sigma`, `compile_yara`, `scan_yara`.

### s5-review-queue — Security review queue end-to-end

security-reviewer: review_start on a real lab finding → review_status → review_result / review_verdict / review_explain; review_queue then review_cancel on a second finding; review_doctor health; hunt_case on a terminal hunt.

Covers (9): `review_start`, `review_status`, `review_result`, `review_cancel`, `review_verdict`, `review_queue`, `review_explain`, `review_doctor`, `hunt_case`.

### s5-compliance-register — Compliance register + review workflow

auto-compliance::reading: nerc_cip_requirement / compliance_requirement / nerc_cip_currency exact-text turns; compliance_search / compliance_read / compliance_links / compliance_timeline; compliance_note / compliance_notes / compliance_answers / compliance_correct / compliance_context / compliance_coverage / compliance_conflicts / compliance_standing_questions; compliance_review_list → compliance_review_decide / compliance_review_decide_batch on the planted corpus; compliance_sources / compliance_trace / compliance_draft_revisions / compliance_intentionality / compliance_flexibility / compliance_compare. Operator lane (eval store :8948): compliance_ingest / compliance_orphans / compliance_mappings / compliance_scope / compliance_route / lookup_control / search_controls / map_frameworks / patch_evidence / refresh_catalogs and the eight unwired engine tools (compliance_gaps retiring path, compliance_analyze, compliance_scenario, compliance_prospective, compliance_change_impact, compliance_impact, compliance_bundle, compliance_kb_search).

Covers (42): `nerc_cip_requirement`, `compliance_requirement`, `nerc_cip_currency`, `compliance_search`, `compliance_read`, `compliance_links`, `compliance_timeline`, `compliance_note`, `compliance_notes`, `compliance_answers`, `compliance_correct`, `compliance_context`, `compliance_coverage`, `compliance_conflicts`, `compliance_standing_questions`, `compliance_review_list`, `compliance_review_decide`, `compliance_review_decide_batch`, `compliance_sources`, `compliance_trace`, `compliance_draft_revisions`, `compliance_intentionality`, `compliance_flexibility`, `compliance_compare`, `compliance_ingest`, `compliance_orphans`, `compliance_mappings`, `compliance_scope`, `compliance_route`, `lookup_control`, `search_controls`, `map_frameworks`, `patch_evidence`, `refresh_catalogs`, `compliance_gaps`, `compliance_analyze`, `compliance_scenario`, `compliance_prospective`, `compliance_change_impact`, `compliance_impact`, `compliance_bundle`, `compliance_kb_search`.

### s5-proxmox-readonly — Proxmox read-only inventory + confirm-gated writes

auto-coding / auto-daily::fast: proxmox_list_nodes / proxmox_node_status / proxmox_cluster_status / proxmox_list_all_vms / proxmox_find_vm / proxmox_list_vms / proxmox_vm_status / proxmox_vm_config / proxmox_vm_agent_info / proxmox_list_snapshots / proxmox_list_containers / proxmox_container_status / proxmox_list_storage / proxmox_list_storage_content / proxmox_list_networks / proxmox_task_status / proxmox_list_tasks. Confirm-gated lane (lab only): proxmox_vm_start / proxmox_vm_shutdown / proxmox_vm_stop / proxmox_vm_reset / proxmox_vm_reboot / proxmox_vm_suspend / proxmox_vm_resume / proxmox_clone_vm / proxmox_delete_vm / proxmox_create_snapshot / proxmox_rollback_snapshot / proxmox_delete_snapshot / proxmox_exec_vm / proxmox_container_start / proxmox_container_stop / proxmox_container_shutdown / proxmox_container_exec / proxmox_node_exec / proxmox_deploy_ctf_lab.

Covers (36): `proxmox_list_nodes`, `proxmox_node_status`, `proxmox_cluster_status`, `proxmox_list_all_vms`, `proxmox_find_vm`, `proxmox_list_vms`, `proxmox_vm_status`, `proxmox_vm_config`, `proxmox_vm_agent_info`, `proxmox_list_snapshots`, `proxmox_list_containers`, `proxmox_container_status`, `proxmox_list_storage`, `proxmox_list_storage_content`, `proxmox_list_networks`, `proxmox_task_status`, `proxmox_list_tasks`, `proxmox_vm_start`, `proxmox_vm_shutdown`, `proxmox_vm_stop`, `proxmox_vm_reset`, `proxmox_vm_reboot`, `proxmox_vm_suspend`, `proxmox_vm_resume`, `proxmox_clone_vm`, `proxmox_delete_vm`, `proxmox_create_snapshot`, `proxmox_rollback_snapshot`, `proxmox_delete_snapshot`, `proxmox_exec_vm`, `proxmox_container_start`, `proxmox_container_stop`, `proxmox_container_shutdown`, `proxmox_container_exec`, `proxmox_node_exec`, `proxmox_deploy_ctf_lab`.

### s5-data-sql — Data analyst SQL lane

auto-research::data: attach_source a fixture CSV/SQLite, profile_table, run_sql a known-answer query, list_session shows the session. The s2-p3-data-mcp infra scenario only probes /health + /ready; this journey exercises the four tools.

Covers (4): `attach_source`, `run_sql`, `profile_table`, `list_session`.

### s5-jarvis-introspection — Jarvis personal task + pipeline introspection + git/unifi

auto-daily / Jarvis: jarvis_submit a personal task, arm_queue_task confirm flow (TTL > 0), get_pipeline_status / list_workspaces / get_loaded_models / get_metrics_summary / get_workspace_recommendation / trigger_backend_warmup; wiki_search / wiki_get_unit / wiki_explain; auto-coding::laguna: explore_repository / read_text_file / list_directory / search_files / write_file inside the task root; git_status / git_log / git_diff read-only, git_commit / git_push confirm-gated on a scratch repo; unifi_tool_index → unifi_load_tools → unifi_execute plus the 11 wired read-only unifi_* tools (confirm-gated).

Covers (35): `jarvis_submit`, `arm_queue_task`, `get_pipeline_status`, `list_workspaces`, `get_loaded_models`, `get_metrics_summary`, `get_workspace_recommendation`, `trigger_backend_warmup`, `wiki_search`, `wiki_get_unit`, `wiki_explain`, `explore_repository`, `read_text_file`, `list_directory`, `search_files`, `write_file`, `git_status`, `git_log`, `git_diff`, `git_commit`, `git_push`, `unifi_tool_index`, `unifi_load_tools`, `unifi_execute`, `unifi_list_devices`, `unifi_get_device_details`, `unifi_list_clients`, `unifi_get_client_details`, `unifi_list_wlans`, `unifi_get_wlan_details`, `unifi_list_networks`, `unifi_get_network_health`, `unifi_get_system_info`, `unifi_get_dashboard`, `unifi_list_alarms`.

### s5-gui-controls — GUI controls beyond the roster smoke

Browser journey: toggle web search ON and verify a cited result; open the integrations/tools menu and toggle a tool; play TTS audio from the message control; record/upload audio via the mic control; click a rendered artifact download link; reload the page and verify multi-turn history persists; rename/archive a chat from the sidebar.

### s5-channels-telegram-slack — Channel adapters: Telegram commands + Slack routing

Telegram: /start, /clear, /workspace <valid>, /workspaces, /jarvis status|digest|do, arm Approve/Deny callback; plain-text chat with history. Slack: @mention in #coding/#security/#research channels, DM, thread reply. Assert the dispatcher roster matches portal.yaml (currently drifted — see Fix List).

### s5-binresearch-ide — Binary research IDE surface (out-of-pipeline)

IDE-only journey on :8930 (expose_to_pipeline=false): re_tools inventory, re_exec shell in the DinD project, re_python snippet. Not a chat workspace feature; covered here so no served tool is untracked.

Covers (3): `re_exec`, `re_python`, `re_tools`.

### Coverage closure check

ACTIVE_UNTESTED unique names: 191; assigned to journeys: 191;
unassigned: 0 — zero omissions.

## 14. Honest Negatives & Known Issues

- **The brief's STALE_DEAD example does not hold at HEAD.** The "retired compliance coverage
  engine tools" are not dead: `compliance_gaps` is the retiring path but is deliberately
  exercised by `scripts/compliance_acceptance.py:279` (adapter_legacy) so the re-point to
  `compliance_coverage` stays measurable; `compliance_analyze`/`compliance_scenario`/
  `compliance_impact`/`compliance_prospective`/`compliance_kb_search` are called by
  `scripts/compliance_reliability_probe.py`, `scripts/run_seven_question_routed.py`,
  `scripts/verify_foundation_routed.py` and listed in `eval_instance.py` VERIFIED_TOOLS.
  All 8 remain in the manifest + `_DISPATCH`. They are ACTIVE_UNTESTED operator/eval
  surface, not purge candidates. No tool definition was tuned into a bucket to match the
  brief's expectation.
- **auto-council journey not emitted:** s2-p2-auto-council is gated on preset presence
  (scenarios.py:243) and auto-council has no OWUI preset at HEAD — the council workspace
  is internal; the scenario silently does not exist. Reported, not fixed (Lane B).
- **toggle_details is exercised but not asserted** (runner.py:1058/1068): a missing
  <details> block returns False without failing the scenario. Weak coverage, flagged.
- **Known-issues set locked by the unit test:** `browser_get_markdown` is the single
  pre-existing phantom native reference. The companion test carries it in an explicit
  KNOWN_PHANTOM_REFS set with a pointer to the fix lane; any NEW phantom fails the test.
- **External surface limits:** docker/context7 IDE tool lists are partially verified
  (minified dists); the unifi 210-name list is from the pinned 0.40.0 cache, not a live
  tools/list. Both are UNPROVEN against the running system — orchestrator verifies.

## 15. Verification

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/projects/portal-5/.venv uv run pytest tests/unit/test_feature_traceability_completeness.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/projects/portal-5/.venv uv run pytest tests/unit/ -q
uv run ruff check . && uv run ruff format --check .
python3 scripts/complexity_report.py --gate
```

The unit test re-parses portal.yaml, the persona YAMLs, every `@mcp.tool` definition and
this document, and asserts: zero untracked tools, zero phantom persona workspace bindings,
and no new phantom tool references beyond the locked known-issues set. It is a drift lock,
not live evidence — live verification belongs to the orchestrator (WORKER_CONTRACT §0).

