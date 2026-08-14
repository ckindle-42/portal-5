# Security Bench Real-Execution Runbook

<!-- WIKI:GENERATED unit=unit-fact-security-variants -->
# Security canonical variants (10)

sec-bench `--workspaces` targets, addressed as `auto-security::<variant>`:

- `auto-security::blueteam`
- `auto-security::blueteam-council`
- `auto-security::blueteam-orchestrated`
- `auto-security::pentest`
- `auto-security::purpleteam`
- `auto-security::purpleteam-deep`
- `auto-security::purpleteam-exec`
- `auto-security::redteam`
- `auto-security::redteam-deep`
- `auto-security::uncensored`

## Why

The canonical variant set is the `variants` map on the `auto-security` workspace in `config/portal.yaml`. Each entry is an `auto-security::<variant>` id that `sec-bench --workspaces` targets; the pipeline resolves the variant to a model pool the same way a `?variant=` hint on any workspace does. Deriving the list from config keeps the documented target set and the live routing surface aligned.
<!-- /WIKI:GENERATED -->

---

`bench_security` is a **package** (`portal/modules/security/core/`), decomposed from a single module. Chain execution, scoring, and lab-exec logic were further split into focused sub-modules; `chain.py` and `cli.py` are now thin re-export shims over the implementations that moved out.

| Module | Purpose |
|--------|---------|
| `_data.py` | All configuration: PROMPTS, EXEC_SEQUENCES, CHAIN_INHERITANCE, constants, env vars, service probes, tool definitions |
| `_config.py` | `BenchConfig` dataclass -- per-run context replacing mutable module globals |
| `scoring.py` | Pure scoring functions (no I/O): response scoring, execution scoring, handoff quality, chain coherence, scope discipline |
| `lab.py` | Lab lifecycle: service probing, Proxmox snapshot/restore, sandbox dispatch, stealth queries, artifact injection |
| `blue.py` | Blue team defender: detection chain, telemetry, purple scoring, evasion loops |
| `exec_chain.py` | Execution chain: multi-turn tool-call chains, scenarios, `_run_exec_chain()`, synthetic results |
| `chain.py` | Re-export shim for `exec_chain.py`, `refusal.py`, and `intake.py` |
| `cli.py` | CLI entry point: argparse dispatcher; `run_bench()` and summary printers live in `commands/run.py` |
| `matrix.py` | Scenario x container matrix: `build_run_matrix`, `run_matrix`, `TelemetryBackend` protocol, coverage reports |
| `capability/` | Capability index -- unifies `_LAB_SERVICE_PROBES`, `challenge_classes.yaml`, and `lab_targets.yaml` into one queryable `Capability` list |
| `goal.py`, `goal_decide.py`, `goal_eval.py`, `goal_cli.py` | Goal-driven decide -- reasons over the capability index instead of a playbook DAG |
| `drift_gate.py`, `drift_cli.py` | Drift-detection gate -- rolling-baseline regression + model-behavior canary |
| `loop.py`, `loop_cli.py` | Autonomy loop escalation notifications + checkpoint/resume |
| `__init__.py` | Thin facade: pipeline I/O + re-exports |

## Why

The package boundary exists so the security bench can grow without a single monolithic script. The refactors split chain, blue, and lab-exec logic out of the original module, and the module-level shims (`chain.py`, `cli.py`, `__init__.py`) keep import compatibility while the implementation moves. Knowing which file owns which concern — configuration in `_data.py`, pure math in `scoring.py`, live lab I/O in `lab.py` — is what lets a new contributor add a scenario or a scoring rule without touching unrelated code paths.

---

## Capability Index

`portal.modules.security.core.capability` makes the scattered security library legible to a decide step. Read-only — indexes what already exists.

- `tool_inventory.py` — Kali tool arsenal curated from `config/tool_catalog.yaml`
- `index.py` — `Capability` dataclass + `build_index()` + `query()`
- `render.py` — `render_capabilities()` / `render_tool_arsenal()`
- CLI: `python3 -m portal.modules.security.core capability {list,query,tools,arsenal}`

## Goal-Driven Decide (Stage 2 — dry-run/proposal only)

Upgrades decide from lookup to reasoning. Deliberately stops at proposal + dry-run.

- `goal.py` — `EngagementGoal` + `validate_goal()`
- `goal_decide.py` — `decide_next_action()` over platform-core
- `loop.py::run_goal_engagement()` — open-ended loop, dry-run only
- `goal_eval.py::eval_proposals()` — Stage-3 go/no-go evidence

## Emergent Objective Loop (flag-gated)

Second path onto `portal.platform.agent.loop.run_loop`. Drops seeded first-move.

- `perception.py` — `LabPerception` hard-scoped to `10.10.11.0/24`
- `objective_executor.py` — `SecurityExecutor` wrapping real actuation
- `objective_entry.py` — `PORTAL_EMERGENT`-gated entry

## Drift-Detection Gate

Rolling-baseline regression + model-behavior canary. FLAG only.

- `drift_gate.py::drift_check(window=7)` — per (scenario, blue_model) pair
- `drift_gate.py::run_canary_probe(model)` — 12-probe deterministic suite

## Loop Notifications

Reuses existing notification subsystem. Fire-and-forget, non-fatal.

- Event types: `ENGAGEMENT_ESCALATED`, `ENGAGEMENT_STUCK`, `ENGAGEMENT_COMPLETE`
- Checkpoint/resume: `_write_checkpoint` persists `EngagementState`

## Why

Each sub-component extends the bench without touching the core chain: the capability index gives a decide step something legible to query, the goal-driven and emergent loops layer reasoning on top, drift gate flags model regressions across runs, and loop notifications surface long-running engagements. The deliberate pattern is containment — the capability index is read-only, goal decide stops at proposal, the emergent loop is flag-gated, and drift is a flag, not a verdict.

---

## Lab VMs must be running

```bash
docker exec portal5-dind docker run --rm --net bridge portal5-attack:latest \
  sh -c 'nxc smb 10.10.11.21 2>&1 | tail -2 && redis-cli -h 10.10.11.50 ping && \
         nxc smb 10.10.11.13 -u "" -p "" 2>&1 | head -3 && \
         curl -s -o /dev/null -w "%{http_code}" http://10.10.11.50:80/'
```

## attack image in DinD

```bash
docker exec portal5-dind docker images portal5-attack 2>/dev/null | grep latest
# If missing: ./launch.sh build-lab-attack
```

## .env configuration

Required in `.env`:
- `SANDBOX_LAB_EXEC=true`
- `SANDBOX_LAB_IMAGE=portal5-attack:latest`
- `LAB_TARGET_DC=10.10.11.21`
- `LAB_TARGET_SRV=10.10.11.33`
- `LAB_TARGET_WEB=10.10.11.50`

These must be present in the environment or `.env` for the lab-exec lane to activate; without `SANDBOX_LAB_EXEC=true` the bench silently falls back to synthetic results.

Optional — for Proxmox VM lifecycle (snapshot/restore):
- `PROXMOX_URL`, `PROXMOX_TOKEN_ID`, `PROXMOX_TOKEN_SECRET`
- `LAB_DC_VMID`, `LAB_SRV_VMID`, `LAB_CLEAN_SNAPSHOT`

## MCP sandbox running

```bash
./launch.sh status | grep sandbox
```

## Security models loaded

```
hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M
hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf
huihui_ai/baronllm-abliterated:latest
hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0
```

## Why

Every item here is a silent-failure precondition: the bench degrades to synthetic, unreachable, or wrong-model results rather than erroring when one is missing. `SANDBOX_LAB_EXEC` gates the entire lab-exec lane, the `LAB_TARGET_*` addresses are what the attack image actually reaches, and the model list is what the exec chain must have pulled locally before a run starts.

---

## Tier 1 — Theory (prose quality, workspace prompts only)

Runs the prompt set against the listed security workspaces with tools disabled. Measures structure adherence, disclaimer density, MITRE coverage. No lab needed.

```bash
python3 -m portal.modules.security.core \
  --workspaces \
    auto-security auto-security::redteam auto-security::redteam-deep auto-security::pentest \
    auto-security::blueteam auto-security::purpleteam-exec \
  2>&1 | tee /tmp/secbench_theory.log
```

## Tier 2 — Execution (tool-call scoring, exec workspaces only)

Same prompts but with tools enabled on the execution-capable workspaces. Scores tool call sequences against `exec_sequence` definitions. No lab dispatch.

```bash
python3 -m portal.modules.security.core \
  --workspaces auto-security::pentest auto-security::purpleteam-exec \
  --exec-eval \
  2>&1 | tee /tmp/secbench_exec.log
```

## Tier 3 — Lab-Exec (real dispatch against live lab)

Multi-model chain with real sandbox execution, blue defender, snapshot lifecycle, and lab probe: `--skip-workspace-bench --exec-chain-models <roster> --blue-defender-model <model> --prompt <key> --lab-exec` (a concrete command is in `unit-SEC_BENCH-single-prompt-tests`).

## Why

These three tiers are the same bench at increasing cost and fidelity, and the quick-start framing exists so an operator can pick the cheapest tier that answers the current question. Theory validates many models quickly, exec adds tool-call sequence without lab dependencies, and lab-exec is reserved for runs whose results must be trusted as real. The `--exec-eval` flag is what switches exec workspaces into tier two, which is why it appears in exactly that command.

---

## Single prompt, lab-exec

```bash
python3 -m portal.modules.security.core \
  --skip-workspace-bench \
  --exec-chain-models \
    "hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M" \
    "qwen3-coder:30b-a3b-q4_K_M" \
    "huihui_ai/baronllm-abliterated:latest" \
  --blue-defender-model "hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0" \
  --prompt kerberoasting \
  --lab-exec \
  2>&1 | tee /tmp/secbench_kerberoast.log
```

`--skip-workspace-bench` skips the theory/exec pipeline passes so only the chain runs; `--exec-chain-models` takes the 2-4 model roster; `--blue-defender-model` names the SOC-analysis model; `--prompt` selects a single `PROMPTS` key; `--lab-exec` enables real dispatch.

## Probe lab services only

```bash
python3 -m portal.modules.security.core --probe-lab --dry-run 2>&1
```

## Why

These two commands are the fastest paths to a single answer: run one prompt end-to-end against the live lab, or just check reachability before committing to a long run. The single-prompt form is also the debugging loop — when a full scenario fails, isolating one prompt with one model roster makes the failure reproducible in minutes instead of hours.

---

22 features of the execution chain (drawn from `exec_chain.py`, `scoring.py`, `lab.py`, and `_data.py`):

1. **Adaptive Retry** — `fallback_techniques` tried when primary fails
2. **Cross-Prompt Artifact Chaining** — `CHAIN_INHERITANCE` forwards credentials
3. **Blue Active Response** — `block_ip`, `disable_account`, `revoke_tgt`
4. **Step Dependency DAG** — topological sort via `build_step_dag()` in `lab.py`
5. **Lab Service Auto-Discovery** — 17 service probes in `_LAB_SERVICE_PROBES`, `--probe-lab`
6. **Stealth Scoring** — Windows Event Log queries, `stealth_event_ids`
7. **Proxmox VM Snapshot/Restore** — `--lab-snapshot`
8. **Per-Step Time Budgets** — `time_budget_s`, `speed_score`
9. **Conditional Branching** — `condition` field evaluated against observations
10. **Dynamic CVE Research** — `--dynamic-cve`, model must `web_search` CVE
11. **Sequence Adherence** — LIS of matched tool call indices
12. **Success Gating** — `success_indicators` required for 'proven' status
13. **False Positive Testing** — `--false-positive-test`
14. **Defense Efficacy Testing** — `--defense-efficacy`
15. **Detection Latency** — `detection_latency_s` in blue turn results
16. **Defense Verification** — `verify_defense` probes target after blue action
17. **Rescore** — `--rescore FILE` re-derives metrics without re-executing
18. **Retry Failed** — `--retry-failed FILE`, `--retry-prompts PROMPT`
19. **Full Output Capture** — `tool_calls`, `lab_outputs`, `lab_observations`
20. **Proven Scoring** — `proven_coverage` in lab-exec mode
21. **Library x Container Matrix** — `--matrix` / `--matrix-all`
22. **Linux/Web Telemetry** — `TelemetryBackend` protocol + platform telemetry contracts (`splunk`/`winevent`/`wazuh`)

## Why

The feature list is the map a reviewer uses to decide whether a behavior is already covered before adding a new flag or scorer. Every item traces to a concrete hook in the bench code — a data field, a CLI flag, or a scoring function — so "we should add X" is answerable by checking the list first. The execution chain is deliberately the thickest surface of the bench: it is where theory, real command dispatch, blue detection, and lab lifecycle all meet.

---

## Execution modes — 33 executable prompts plus theory-only exercises

`PROMPTS` contains both theory exercises and executable lab exercises.
`EXEC_SEQUENCES` (33 keys, one of which — `chain_inherits` — is a synthetic
dispatch entry) is the lab-exercise boundary: only its entries may dispatch
commands in the disposable attack image. `cron_privesc`, `container_escape`,
and `kernel_exploit_chain` remain useful theory prompts, but are deliberately
excluded because their target-local commands would otherwise inspect or modify
the attack container instead of the intended target.

Step definitions may carry `time_budget_s`, `fallback_techniques`, `depends_on`, `stealth_event_ids`, `condition`, `output_keywords`, and `success_indicators` alongside the `keywords`/`output_keywords` pair used for the two-path method-or-result scoring.

Key AD-focused prompts: `kerberoasting`, `asrep_roasting`, `bloodhound_ad_recon`, `pass_the_hash`, `smb_enum_relay`, `redis_to_rce`, `adcs_template_abuse`, `ad_dcsync_golden_ticket`, `rbcd_attack`, `nfs_privesc_chain`, `eternalblue_ms17010`.

Web-focused prompts: `sqli_manual`, `web_shell_upload`, `ssrf_exploitation`, `lfi_to_rce`, `tomcat_manager`, `log4shell_rce`.

Metasploitable3 prompts: `ftp_backdoor`, `mysql_udf_privesc`, `glassfish_deploy`, `es_script_rce`, `iis_webdav_scanner`, `meta3_full_compromise`.

The historical FTP and MySQL IDs are retained for result compatibility, but
their executable steps now match Metasploitable3 Windows: IIS FTP credential
validation and bounded MySQL metadata access. They do not dispatch the Linux
vsftpd port-6200 or UDF shared-object techniques.

Cross-target chains: `web_to_dc_pivot`, `htb_responder_chain`, `htb_lfi_log_poison`, `htb_sqli_to_shell`.

## Why

The `EXEC_SEQUENCES` boundary is the line between prompts that may drive real commands and prompts that only score prose. Keeping it explicit matters because a theory prompt can turn destructive once dispatched — `cron_privesc` and `container_escape` would attack the disposable image itself. The retained FTP/MySQL IDs show the cost of result compatibility: their names survived so historical result files stay comparable, while their actual steps were re-pointed at the Metasploitable3 Windows service fleet.

---

The exec-chain summary line and result JSON expose these per-chain metrics (`chain_exec_composite`, `chain_handoff_quality`, `blue_detection_rate`, and the reliability block in `exec_chain.py`):

| Metric | What it measures |
|---|---|
| `exec` | `chain_exec_composite` — composite of step coverage (method OR result hit), sequence adherence (LIS), and tool diversity |
| `tools` | Fraction of participating models that made at least one tool call |
| `handoff` | Adjacent-model context passing; N/A (None) when fewer than two chain results exist |
| `speed` | Fraction of applicable expected steps completed within `time_budget_s` |
| `stealth` | Conditional event-count score; None unless execution is fully proven (`proven_coverage == 1.0`) |
| `blue_det` | `blue_detection_rate` — fraction of blue turns with tool calls to analyze that were flagged detected |
| `final_det` | `detection_score` — weighted fraction of attack steps named plus MITRE coverage in the final holistic report |
| `reliability` | Per-turn tool-call reliability, gated at `valid_rate < 0.70` |

## Result-based scoring: method OR result match

Each step has two independent scoring paths. A step is marked **hit** if either fires:
1. **Method match** — a keyword from `step["keywords"]` appears in tool call arguments
2. **Result match** — a string from `step["output_keywords"]` appears in real sandbox output

## Why

The two-path scoring exists because a model can name the right technique without executing it, or execute it without naming it — scoring only one path would reward half the skill. Method match credits procedural knowledge from the tool arguments; result match credits the lab output actually produced. The metric table exists so a reader can tell which number measures what: `exec` is a composite, `stealth` is gated on proven execution, and `reliability` carries its own hard floor rather than being folded into a composite.

---

## What to Verify After Running

1. **Real execution** — the chain phase prints a per-prompt `chain(...)` summary with `exec=`, `tools=`, and `handoff=`; real dispatch yields `steps_proven`/`proven_coverage` in the result JSON rather than the `(synthetic.)` fallback marker
2. **Real IPs** — grep for `10.10.11.21`; leftover HTB IPs mean `_sub_hint()` is not substituting
3. **Stealth scoring** — grep for `[STEALTH]` lines
4. **Blue active response** — grep for `[BLUE-ACTIVE` (with `--blue-active`)
5. **Artifact chaining** — grep for `Inherited artifacts`
6. **Lab probe** — `python3 -m portal.modules.security.core --probe-lab --dry-run`

## Known Issues

- **Read-only root filesystem** — the attack image mounts a read-only root fs, so tools that must write (e.g. `smbclient`) fail inside it; the probes use `nxc smb` for SMB reachability
- **nmap requires privileges** — NET_RAW cap added for lab-exec containers
- **Clock skew** — `ensure_lab_time_sync()` auto-syncs before first dispatch
- **HTB IP hallucination** — `_sub_hint()` resolves `$LAB_TARGET_DC`/`$DOMAIN`/`$LAB_TARGET_SRV`/`$LAB_TARGET_WEB`
- **Small model exploration** — Use `--chain-rounds 3` if steps are missed

## Why

Verification matters here more than in a unit test because lab-exec results are only as trustworthy as the evidence they carry: a model can emit plausible tool calls that never reached a real target, and a synthetic fallback must never be read as a live win. The checklist therefore greps for the markers that only real dispatch produces, and the known-issues list records the failure modes that already misled people once — stale HTB IPs, clock skew, and a read-only filesystem that silently breaks certain tools.

---

## File locations after refactor

```
portal/modules/security/core/
├── _data.py        <- Add new prompts, EXEC_SEQUENCES, CHAIN_INHERITANCE here
├── __init__.py     <- Package facade (pipeline I/O, re-exports)
├── __main__.py     <- CLI entry (do not modify)
├── exec_chain.py   <- _run_exec_chain() now lives here
├── lab.py          <- _lab_mcp_call, _proxmox_mcp_call
├── blue.py, chain.py, cli.py, matrix.py, scoring.py, ... (plus dozens more)
```

## Architecture invariant

The bench NEVER modifies Open WebUI or the pipeline. It communicates directly with:
- Ollama at :11434 for model inference
- MCP sandbox at :8914 for command execution
- Proxmox MCP at :8927 for VM lifecycle

## Rebuild triggers

```bash
# After Dockerfile.attack change:
./launch.sh build-lab-attack
# After code_sandbox_mcp.py change:
./launch.sh restart-mcp
# After _data.py or __init__.py change:
# No rebuild needed — Python picks up changes directly
```

## Why

Re-entering this package after a refactor is cheap only if the module map is current; the map above is the first thing a contributor checks before adding a prompt, a scenario, or a lab hook. The rebuild triggers matter because the lab-exec lane runs inside Docker images that do not pick up Python edits automatically — only `_data.py` and `__init__.py` are hot-reloadable, so knowing which layer a change lands in determines whether a rebuild is required.

---

`--blue-mode` selects which blue investigation path a run uses:

| Mode | Shape | Prompt |
|---|---|---|
| `scripted` | 1 model, tools | Mandatory step checklist |
| `discovery` (default) | 1 model, tools | Fully open-ended, no hints |
| `hybrid` | 1 model, tools | Open-ended with technique-reference hints |
| `orchestrated` | 3 sections | tool + reasoning + expert |
| `orchestrated-2section` | 2 sections | tool + merged reasoning/expert |
| `council` | tool + N reasoning + arbiter | N interpreters vote over shared evidence |
| `multichain` | N independent chains | N fully independent investigations

`scripted` and `hybrid` are assisted diagnostics and do not produce a primary
capability score. `orchestrated`, `orchestrated-2section`, `council`, and
`multichain` are standalone modes that replay a captured red episode
(`--replay-captured-red`) rather than `--purple` prompt variants.

## Three-section pipeline (`orchestrated`)

Retriever gathers telemetry; Hunter forms hypotheses; Expert renders verdict.

## Council of Agreement (`council`)

One Retriever gathers evidence once; N reasoning members vote independently.

## Multi-chain analyst (`multichain`)

N fully independent investigative chains. Consolidation routes to: `AUTO_CONFIRM`, `ESCALATE`, `CONFIRM_AND_ESCALATE`, `DISMISS`.

Escalation is a SCORED win, not a miss.

## Why

The mode table exists because a single blue prompt cannot serve every evaluation question. Scripted and discovery measure a lone defender; orchestrated, council, and multichain isolate how multiple models split evidence gathering from verdicts. The default is discovery so an operator who omits the flag gets the least-leading evaluation, while the standalone modes intentionally require a captured episode so comparisons stay reproducible against the same red evidence.
