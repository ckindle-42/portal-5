---
id: unit-fact-persona-roster
kind: what
title: 134 personas
sources:
- type: code
  path: config/personas/
  commit: d5814a812dbb
- type: code
  path: config/personas/adversarysimulator.yaml
  commit: d5814a812dbb
- type: code
  path: config/personas/agenticheavy.yaml
  commit: d5814a812dbb
- type: code
  path: config/personas/agenticlite.yaml
  commit: d5814a812dbb
- type: code
  path: config/personas/agentorchestrator.yaml
  commit: d5814a812dbb
- type: code
  path: config/personas/bench_gemma4_12b.yaml
  commit: d5814a812dbb
claims:
- probe: personas.count
  pattern: Persona roster ({value} personas)
confidence: high
tags:
- fact
- personas
created_at: 1784000421.217775
updated_at: 1788390213.6378188
---

# Persona roster (134 personas)

| Slug | Module | Workspace | Model Pin |
|---|---|---|---|
| `adversarysimulator` | security | `auto-security` | — |
| `agenticheavy` | coding | `auto-coding` | — |
| `agenticlite` | coding | `auto-coding` | — |
| `agentorchestrator` | coding | `auto-coding` | — |
| `bench-gemma4-12b` | eval | `bench-gemma4-12b` | — |
| `bench-gemma4-26b-optiq` | eval | `bench-gemma4-26b-optiq` | — |
| `bench-gemma4-26b-qat` | eval | `bench-gemma4-26b-qat` | — |
| `bench-gemma4-31b-qat` | eval | `bench-gemma4-31b-qat` | — |
| `bench-gemma4-e2b` | eval | `bench-gemma4-e2b` | — |
| `bench-gemma4-e4b` | eval | `bench-gemma4-e4b` | — |
| `bench-gemma4-e4b-qat` | eval | `bench-gemma4-e4b-qat` | — |
| `bench-glm` | eval | `bench-glm` | — |
| `bench-granite41-30b` | eval | `bench-granite41-30b` | — |
| `bench-granite41-8b` | eval | `bench-granite41-8b` | — |
| `bench-huihui-qwen36-27b` | eval | `bench-huihui-qwen36-27b` | — |
| `bench-huihui-qwen36-35b-a3b` | eval | `bench-huihui-qwen36-35b-a3b` | — |
| `bench-laguna` | eval | `bench-laguna` | — |
| `bench-lfm25-8b` | eval | `bench-lfm25-8b` | — |
| `bench-lfm25-8b-uncensored` | eval | `bench-lfm25-8b-uncensored` | — |
| `bench-nex-n2-mini` | eval | `bench-nex-n2-mini` | — |
| `bench-omnicoder2` | eval | `bench-omnicoder2` | — |
| `bench-qwen35-abliterated` | eval | `bench-qwen35-abliterated` | — |
| `bench-qwen36-27b-optiq` | eval | `bench-qwen36-27b-optiq` | — |
| `bench-qwen36-35b-a3b-ud` | eval | `bench-qwen36-35b-a3b-ud` | — |
| `bench-qwen36-abl-27b` | eval | `bench-huihui-qwen36-27b` | — |
| `bench-qwen36-hauhaucs` | eval | `bench-qwen36-hauhaucs` | — |
| `bench-qwen3-coder-30b` | eval | `bench-qwen3-coder-30b` | — |
| `bench-qwen3-coder-next` | eval | `bench-qwen3-coder-next` | — |
| `bench-qwen3-coder-next-abliterated` | eval | `bench-qwen3-coder-next-abliterated` | — |
| `blueteamdefender` | security | `auto-security` | — |
| `bugdiscoverycodeassistant` | coding | `auto-coding` | — |
| `businessanalyst` | general | `auto-reasoning` | — |
| `caddesigner` | cad | `auto-cad` | — |
| `chartanalyst` | general | `auto-vision` | — |
| `cippolicywriter` | compliance | `auto-compliance` | — |
| `codebasewikidocumentationskill` | coding | `auto-coding` | — |
| `codereviewassistant` | coding | `auto-coding` | — |
| `codereviewer` | coding | `auto-coding` | — |
| `codescreenshotreader` | general | `auto-vision` | — |
| `codingagentic` | coding | `auto-coding` | — |
| `codinguncensored` | coding | `auto-coding` | — |
| `codinguncensoredagentic` | coding | `auto-coding` | — |
| `complianceanalyst` | compliance | `auto-compliance` | — |
| `creativecoder` | coding | `auto-coding` | — |
| `creativewriter` | media | `auto-creative` | — |
| `cybersecurityspecialist` | security | `auto-security` | — |
| `dailydriver` | general | `auto-daily` | — |
| `dashboardarchitect` | research | `auto-data` | — |
| `dataanalyst` | research | `auto-data` | — |
| `databasearchitect` | research | `auto-data` | — |
| `dataextractor` | research | `auto-data` | — |
| `datascientist` | research | `auto-data` | — |
| `devopsautomator` | coding | `auto-coding` | — |
| `devopsengineer` | general | `auto-reasoning` | — |
| `devstral_coder` | coding | `auto-coding` | `devstral-small-2:latest-ctx8k` |
| `diagramreader` | general | `auto-vision` | — |
| `documentationarchitect` | documents | `auto-documents` | — |
| `e2edebugger` | coding | `auto-coding` | — |
| `e2etestauthor` | coding | `auto-coding` | — |
| `ethereumdeveloper` | coding | `auto-coding` | — |
| `excelsheet` | coding | `auto-coding` | — |
| `factchecker` | research | `auto-research` | — |
| `formfiller` | coding | `auto-coding` | — |
| `fullstacksoftwaredeveloper` | coding | `auto-coding` | — |
| `gdprdpoadvisor` | compliance | `auto-compliance` | — |
| `gemma4-heretic-coder` | coding | `auto-coding` | `portal5/gemma4-26b-heretic:q4_K_M-ctx256k` |
| `gemma4e4bvision` | general | `auto-vision` | — |
| `gemma4jangvision` | general | `auto-vision` | `hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF:gemma-4-31b-jang-crack-Q4_K_M.gguf` |
| `gemma_e4b` | general | `auto-daily` | — |
| `gemma_fast` | general | `auto-daily` | — |
| `gemma_vision` | general | `auto-vision` | `gemma4:31b-it-qat-ctx8k` |
| `gemmaresearchanalyst` | research | `auto-research` | — |
| `githubexpert` | coding | `auto-coding` | — |
| `glm-coder` | coding | `auto-coding` | `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` |
| `glm-thinker` | general | `auto-reasoning` | `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf-ctx64k` |
| `goengineer` | coding | `auto-coding` | — |
| `gptossanalyst` | general | `auto-reasoning` | — |
| `hauhaucs-coder` | coding | `auto-coding` | `portal5/hauhaucs-qwen36-35b:q4_K_M-ctx256k` |
| `hermes3writer` | media | `auto-creative` | — |
| `hipaaprivacyofficer` | compliance | `auto-compliance` | — |
| `interviewcoach` | media | `auto-creative` | — |
| `itarchitect` | general | `auto-reasoning` | — |
| `itexpert` | general | `auto` | — |
| `javascriptconsole` | coding | `auto-coding` | — |
| `kbnavigator` | research | `auto-research` | — |
| `kubernetesdockerrpglearningengine` | coding | `auto-coding` | — |
| `linuxterminal` | coding | `auto-coding` | — |
| `machinelearningengineer` | research | `auto-data` | — |
| `magistralstrategist` | general | `auto-reasoning` | `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` |
| `marketanalyst` | research | `auto-research` | — |
| `mathreasoner` | general | `auto-math` | — |
| `nemotronlightning` | general | `auto-nemotron` | — |
| `nerccipcomplianceanalyst` | compliance | `auto-compliance` | — |
| `networkengineer` | security | `auto-security` | — |
| `ocrspecialist` | general | `auto-vision` | — |
| `ornith15-coder` | coding | `auto-coding` | `portal5/ornith15-35b:q4_K_M-ctx256k` |
| `paywalledresearcher` | research | `auto-research` | — |
| `pcidssassessor` | compliance | `auto-compliance` | — |
| `pentester` | security | `auto-security` | — |
| `pentestlead` | security | `auto-security` | — |
| `personalassistant` | general | `auto-daily` | — |
| `phi4specialist` | documents | `auto-documents` | — |
| `phi4stemanalyst` | general | `auto-reasoning` | — |
| `printabilityengineer` | cad | `auto-cad` | — |
| `productmanager` | general | `auto-reasoning` | — |
| `proofreader` | media | `auto-creative` | — |
| `purpleteamexec` | security | `auto-security` | — |
| `purpleteamlead` | security | `auto-security` | — |
| `pythoncodegeneratorcleanoptimizedproduction-ready` | coding | `auto-coding` | — |
| `pythoninterpreter` | coding | `auto-coding` | — |
| `qwen38coder` | coding | `auto-coding` | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` |
| `qwen38coder-dflash` | coding | `auto-coding` | `Qwen3.8-27B-4bit` |
| `redteamoperator` | security | `auto-security` | — |
| `researchanalyst` | research | `auto-research` | — |
| `rustengineer` | coding | `auto-coding` | — |
| `securityuncensored` | security | `auto-security` | — |
| `seniorfrontenddeveloper` | coding | `auto-coding` | — |
| `seniorsoftwareengineersoftwarearchitectrules` | general | `auto-reasoning` | — |
| `soc2auditor` | compliance | `auto-compliance` | — |
| `softwarequalityassurancetester` | coding | `auto-coding` | — |
| `splunkdetectionauthor` | general | `auto-spl` | — |
| `splunksplgineer` | general | `auto-spl` | — |
| `sqlterminal` | coding | `auto-coding` | — |
| `statistician` | research | `auto-data` | — |
| `supergemma4researcher` | research | `auto-research` | — |
| `techreviewer` | general | `auto` | — |
| `techwriter` | documents | `auto-documents` | — |
| `terraformwriter` | coding | `auto-coding` | — |
| `toolcomposer` | general | `tools-specialist` | — |
| `typescriptengineer` | coding | `auto-coding` | — |
| `ux-uideveloper` | coding | `auto-coding` | — |
| `webnavigator` | general | `auto` | — |
| `webresearcher` | research | `auto-research` | — |
| `whiteboardconverter` | general | `auto-vision` | — |

## Why

The roster is derived from the persona YAML files under `config/personas/`, one per specialist, so the count and the slug/module/workspace bindings always reflect what the pipeline can actually route to. Personas are seeded into Open WebUI as model presets by the same files, so the wiki roster and the served roster cannot drift apart.
