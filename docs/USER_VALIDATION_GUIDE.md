# Portal 5 User Validation Guide

This guide covers the Portal 5 stack described by the current repository configuration. QAT uses `http://localhost:8080` by default; `OPENWEBUI_URL` overrides it. The client creates real chats, sends multiple user turns, reads the pipeline trace, and downloads the artifacts returned to those chats. A passing unit test checks the grader. Only the operator's run against the served stack checks the product.

## Run order

1. Check the discovered plan and roster without contacting services:

   ```bash
   uv run python -m tests.qat --dry-run
   ```

2. Run preflight and hardening before a conversation campaign:

   ```bash
   uv run python -m tests.qat --stage 0,1
   ```

3. Run the human-grade Open WebUI UAT stage:

   ```bash
   uv run python -m tests.qat --stage uat
   ```

   `--stage 5` selects the same stage. Use `--scenario <scenario-id>` to focus a rerun; stage 5 IDs are printed by `--dry-run`. `--api-only` keeps the run on the Open WebUI chat API. Chat cleanup is archive-by-default; `--cleanup-chats` deletes UAT chats.

4. Review `QAT_REPORT.md`, `review.html`, and `results.jsonl` under the printed run directory. A `WARN` row requires operator review; the diarized-transcription row is a warning because the committed speech sample has no gold transcript. Compare its returned transcript with the audio before accepting word-level accuracy.

UAT requires a working Open WebUI login or `OWUI_API_KEY`, a healthy Portal Pipeline, the models and tools selected by current configuration, and the relevant host services. Document deep checks use `python-docx`, `openpyxl`, and `python-pptx`; image checks use Pillow; video checks use `ffprobe`. A missing optional executable or service is a real UAT failure to resolve, not a substitute-pass.

## Current workspace catalog

Workspace IDs and model hints come from `config/portal.yaml`; the listed variant names are its configured variants. A variant is selectable in Open WebUI only when the module and variant exposure rules seed it. The dry-run roster compares that design with `imports/openwebui/workspaces/workspaces_all.json`.

| Workspace ID | Module | Model hint | Configured variants |
|---|---|---|---|
| `auto` | general | `huihui_ai/qwen3.5-abliterated:9b-ctx8k` | — |
| `auto-general-uncensored` | general | `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF:q4_K_M-ctx8k` | `throwaway`, `throwaway-gemma4-heretic`, `throwaway-ornith15`, `creative` |
| `auto-daily` | general | `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k` | `gemma-fast`, `fast`, `deep`, `nemotron`, `inkling` |
| `auto-coding` | coding | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k` | `laguna`, `northmini`, `uncensored`, `uncensored-agentic`, `fast-repair`, `heavy`, `lite`, `ornith`, `cad`, `bigfix`, `devstral_coder`, `gemma4-heretic-coder`, `glm-coder`, `hauhaucs-coder`, `ornith15-coder`, `qwen38coder`, `qwen38coder-dflash` |
| `auto-spl` | general | `Qwen3.8-27B-oQ4e-mtp` | `nano` |
| `auto-security` | security | `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k` | `uncensored`, `pentest`, `blueteam`, `redteam`, `redteam-deep`, `purpleteam`, `purpleteam-deep`, `purpleteam-exec`, `blueteam-orchestrated`, `blueteam-council`, `security-council-qwen36-27b`, `bully-handoff-drafter`, `security-tool-granite41-8b`, `security-council-granite41-30b`, `security-council-mistral-small32-24b`, `security-expert-foundation-sec-8b` |
| `tools-specialist` | general | `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx96k` | `fast` |
| `auto-reasoning` | general | `hf.co/bartowski/K2-Horizon-MoVA-36B-A4B-GGUF:Q4_K_M-ctx64k` | `deep`, `math`, `glm-thinker`, `magistralstrategist` |
| `auto-council` | general | `gemma-4-26b-a4b-it-QAT-4bit` | — |
| `auto-documents` | documents | `gemma4:26b-a4b-it-qat-ctx32k` | `extract-uncensored` |
| `auto-research` | research | `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M-ctx16k` | `data` |
| `auto-vision` | general | `qwen3-vl:32b-ctx8k` | `gemma4jangvision`, `gemma_vision` |
| `security-reviewer` | security | `granite4.1:8b-ctx8k` | — |
| `hunt-reasoning` | security | `gemma4:26b-a4b-it-qat-ctx8k-hunt` | — |
| `auto-compliance` | compliance | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | `reading` |
| `compliance-mapping` | compliance | `gemma4:26b-a4b-it-q4_K_M-ctx128k` | — |
| `compliance-council-qwen38` | compliance | `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k` | — |
| `compliance-council-granite41` | compliance | `granite4.1:30b-ctx16k` | — |
| `compliance-council-deepseek-r1` | compliance | `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` | — |
| `compliance-reading-overflow` | compliance | `gemma4:26b-a4b-it-qat-ctx64k` | — |
| `auto-audio` | media | `gemma4:12b-it-qat-ctx8k` | `image`, `video`, `music` |
| `task-router` | eval | `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M-ctx2k` | — |

The code below prints the current persona slugs and their workspace associations, configured MCP ports, and the effective host-to-container ports from Compose. `docker compose config` resolves the operator's environment overrides without starting containers.

```bash
uv run python - <<'PY'
import subprocess
from pathlib import Path

import yaml

root = Path.cwd()
portal = yaml.safe_load((root / "config/portal.yaml").read_text())
compose_text = subprocess.run(
    ["docker", "compose", "-f", "deploy/portal-5/docker-compose.yml", "config"],
    check=True,
    capture_output=True,
    text=True,
).stdout
compose = yaml.safe_load(compose_text)
print("MCP ID | configured port")
for item in portal.get("mcp_fleet", []):
    print(f"{item.get('id')} | {item.get('port') or 'host-managed'}")
print("\nCOMPOSE SERVICE | published -> target")
for name, service in (compose.get("services") or {}).items():
    for port in service.get("ports") or []:
        if isinstance(port, dict):
            print(f"{name} | {port.get('published')} -> {port.get('target')}")
        else:
            print(f"{name} | {port}")
print("\nPERSONA SLUG | workspace | category | model pin")
for path in sorted((root / "config/personas").glob("*.yaml")):
    persona = yaml.safe_load(path.read_text()) or {}
    print(" | ".join(str(persona.get(key) or "") for key in
                     ("slug", "workspace_model", "category", "model_pin")))
PY
```

## Persona behavioral constraints

Use each persona by its configured slug in the Open WebUI model selector. The stage 5 discovery reads top-level persona YAML files, excludes the bench directory, and chooses personas from their declared policies. It covers these current policy types when present:

- Ambiguous requests must trigger a clarifying question before a recommendation. The current roster includes this rule for agent-orchestration and defensive-analysis roles.
- Destructive actions require a clear risk explanation and confirmation or a backup step.
- Statistical advice distinguishes correlation from causation, states confounders, and challenges accuracy claims on rare classes.
- Compliance answers cite the applicable framework and requirement parts, identify missing evidence, and do not certify an environment as compliant.
- Terminal and spreadsheet personas keep their strict output formats: terminal output stays in a single code block, and spreadsheet formulas are evaluated before values are shown.

The UAT transcript grades the response behavior, and the pipeline trace proves which workspace and model served it. If a persona policy is renamed or its wording changes, scenario selection follows the YAML text; inspect the dry-run plan before the next campaign.

## Workspace routing and lane discipline

Stage 5 sends real requests through the `auto` workspace and checks its per-turn trace:

- A Kubernetes RBAC request should route to the configured coding workspace and produce least-privilege guidance.
- A TLS handshake and firewall investigation should route to the configured security workspace and begin with safe, read-only diagnosis.
- A definite integral should route to the configured math variant and include a derivation that agrees with the exact result.
- A 600-line Okta-to-PostgreSQL service request sent to the daily driver should be redirected to the discovered coding workspace instead of being printed inline.

The stage fails a mismatch between the expected discovered route and the trace workspace, even when the answer text sounds plausible.

## Tool and media workflows

The QAT stage requests capabilities only when the current seeded preset grants their tools. It verifies successful `tool.completed` spans, then fetches the linked file and inspects its contents.

| Workflow | User task | Acceptance evidence |
|---|---|---|
| Code sandbox | Run Python and Bash output markers, then attempt a short `urllib` request | Both output markers appear; the sandbox returns `URLError` for network access |
| Documents | Create a Word report, Excel inventory, and PowerPoint summary | DOCX heading, marker and table dimensions; XLSX exact headers and data row; PPTX slide and bullet marker |
| Document read-back | Create a DOCX, upload it into the same chat, summarize it, then quote a fact on a follow-up turn | `read_word_document` succeeds; the downloaded DOCX and later answer contain the same unique code, owner, and date |
| Image | Generate an image and surface its inline Open WebUI artifact link | PNG decodes, meets minimum dimensions, and has non-trivial pixel variance; blank or solid-color images fail |
| Video | Generate a four-second clip | `ffprobe` sees a video stream, non-zero frames and dimensions, and duration of at least three seconds |
| Music | Generate an instrumental WAV | Valid WAV, at least eight seconds, measurable non-silent RMS |
| TTS | Speak a supplied sentence to WAV, upload that WAV in the next turn, and transcribe it back | `speak` and `transcribe_audio` spans, valid WAV, duration and non-silent RMS, expected words recovered |
| Voice clone | Clone from the provided two-speaker clip and speak a new sentence | `clone_voice` trace and non-silent WAV; response must not invent a source transcript |
| STT | Transcribe the provided two-speaker recording | `transcribe_with_speakers`, speaker labels, transcript file; operator checks exact wording against playback |
| CAD | Build a 20 mm cube and render it | STL triangle geometry has approximately 20 mm bounds on each axis; rendered PNG is nonblank |

## Advanced multi-turn journeys

- **Document RAG:** create a DOCX with fixed facts, upload it to the active chat, summarize through the document reader, and ask a later turn to quote the exact project code and owner.
- **Cross-session memory:** one chat stores a run-specific code and a preferred color with `remember`; a separate Open WebUI chat must recover both with `recall`. The test uses a fresh random code each run to prevent stale memories from passing.
- **Security hunt:** `security-reviewer` must discover a real source, start a scoped hunt, check that exact job's status, and retrieve leads for the same identifier. The suite checks the required tool spans and the returned job identifier.
- **Compliance:** ask a multi-framework privileged-access logging question. The answer must include the requested NERC CIP and GDPR citations, call out evidence gaps, and avoid certification language. This is an answer-quality check, not a compliance determination.
- **Monitoring:** run Stage 1 hardening before judging chat behavior. For operator triage, inspect the health, metrics, and trace surfaces linked from `portal config show`; verify that the workspace and backend shown for a user turn agree with its trace rather than treating HTTP success as acceptance.

The existing QAT compliance limitation remains in force: compliance workspace smoke activity does not by itself prove corpus-grounded compliance quality. Keep that annotation in the report and require subject-matter review for operational conclusions.

## Results and interpretation

Stage 5 writes normal QAT result rows, report, and review packet. `PASS` means the declared conversation, tool, trace, and artifact checks passed. `WARN` means an operator decision remains, such as comparing the STT result with audio that has no committed reference transcript. `FAIL` records the first concrete acceptance defect. `SKIP` is reserved for a capability that current discovery cannot expose; the dry-run plan shows the reason.

For a failed result, preserve the chat and artifact links, inspect its trace, and rerun only that scenario after the cause is fixed:

```bash
uv run python -m tests.qat --stage uat --scenario <scenario-id>
```
