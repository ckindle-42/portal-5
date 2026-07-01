# PORTAL5_BENCH_SEC_EXECUTE_V2 — Security Bench Execution Prompt (V2: lab-setup expansion)

**ARCHIVE NOTE:** V1 (pre-2026-07-01) is superseded. V2 adds Phase 0 preconditions, Full
Expanded mode, the loop/validation invocations, on-demand target verbs, and the honeypot+
hardened-twin methodology. See `docs/LAB_SETUP.md` for the cold-start runbook.

---

## Phase 0 — Precondition: The lab MUST be ready before any bench

**Do not bench a cold lab.** Run these in order:

```bash
./launch.sh setup                # Tier 1: idempotent bulk downloads (once; re-run to update)
./launch.sh lab-up               # start the core lab stack
./launch.sh lab-up-wazuh         # start telemetry (optional; needed for blue-detection)
./launch.sh lab-ready            # readiness gate — RED means STOP, do not bench
```

If `lab-ready` returns RED, resolve the failing required components before proceeding. A green
`lab-ready` confirms: attack box built, vulhub cloned, challenge dirs materialized, space
sufficient.

---

## Four Modes

### 1. Quick — workspace scoring (unchanged from V1)

```bash
python3 -m tests.benchmarks.bench_security --dry-run
python3 -m tests.benchmarks.bench_security
```

### 2. Standard — chain test (unchanged)

```bash
python3 -m tests.benchmarks.bench_security \
  --chain-models MODEL_ID [MODEL_ID ...] \
  --all-scenarios --lab-exec --lab-snapshot
```

### 3. Full — multi-model exec chain (unchanged)

```bash
python3 -m tests.benchmarks.bench_security \
  --exec-chain-models M1 M2 M3 --exec-eval \
  --lab-exec --lab-snapshot
```

### 4. Full Expanded — every security bench step (NEW in V2)

Runs workspace scoring + chain tests + the entire expansion suite:

```bash
# Dry-run first to enumerate available steps:
python3 -m tests.benchmarks.bench_security --full-expanded --dry-run

# Real run:
./launch.sh sec-bench-full
# or equivalently:
python3 -m tests.benchmarks.bench_security --full-expanded --lab-exec --lab-snapshot
```

**What `--full-expanded` enables** (each step no-ops if its module is absent):

| Flag | What it runs | Ground-truth basis |
|---|---|---|
| `--verify-findings` | Named-oracle verification pass (oracles.py) — re-checks every claimed finding N/N | Named oracle (rce_shell, lfi_confirm, cve_confirmed, …) |
| `--ctf` | CTF flag-oracle bench (ctf_bench.py) | Captured flag = unambiguous ground truth |
| `--llm-redteam` | OWASP-LLM-Top-10 probes against Portal's own workspaces | Prompt-injection / tool-abuse / jailbreak resistance |
| `--validate-suite` | Loop-driven red/blue/purple validation against real lab targets | Honeypot + hardened-twin (appear on vulnerable, vanish on twin) |
| `--journal` | Field-journal write-back (field_journal.py) | Autonomy loop memory — engagement outcomes accrue |

Use individual flags to run specific steps without the full sweep:
```bash
python3 -m tests.benchmarks.bench_security --ctf --verify-findings --dry-run
python3 -m tests.benchmarks.bench_security --validate-suite --journal --dry-run
```

---

## Loop & Validation Invocations

The autonomous engagement loop runs a playbook to completion without per-step operator input:

```bash
# Dry-run a playbook (prints phases, scope, budget — no actuation):
./launch.sh sec-loop run playbooks/security/internal-ad-pentest.yaml --dry-run
python3 -m tests.benchmarks.bench_security loop run playbooks/security/web-app-assessment.yaml --dry-run

# Real run (requires lab-exec):
./launch.sh sec-loop run playbooks/security/internal-ad-pentest.yaml --lab-exec
```

The validation suite proves red/blue/purple do their jobs against real lab data using the
honeypot + hardened-twin method:

```bash
# Dry-run the suite:
./launch.sh sec-validate --dry-run

# Real run:
python3 -m tests.benchmarks.bench_security --validate-suite --lab-exec
```

**Validation pass condition:** A use-case PASSES only if the finding lands on the vulnerable
target AND vanishes on the hardened twin (zero false positives). Red, blue, and purple are each
scored independently with their own twin-control gate. A use-case where red lands on the hardened
twin is a false-positive red result and is escalated.

---

## On-Demand Target Verbs

Spin up ephemeral lab targets from the catalog or raw vulhub path:

```bash
./launch.sh lab-targets up vulhub-log4shell-solr --dry-run    # catalog id
./launch.sh lab-targets up struts2/s2-045 --dry-run            # raw vulhub path
./launch.sh lab-targets list                                    # all catalog entries
./launch.sh lab-targets ephemeral vulhub-log4shell-solr -- python3 -m tests.benchmarks.bench_security --chain-models VulnLLM-R-7B --lab-exec
./launch.sh lab-targets down vulhub-log4shell-solr

# Lane-specific targets:
./launch.sh lab-web-up     # SPA target for browser/OAST probes
./launch.sh lab-cloud-up   # LocalStack+kind for cloud lane
./launch.sh oast-up        # OAST collaborator
```

---

## Teardown

```bash
./launch.sh lab-down                # stops core + on-demand containers (no footprint left)
./launch.sh lab-teardown            # lab-down + option to reclaim disk
./launch.sh lab-teardown --purge-downloads  # deep reclaim (removes vulhub clone + base images)
```

---

## Reference

| Doc | What |
|---|---|
| `docs/LAB_SETUP.md` | Cold-start runbook: setup → up → gate → bench |
| `docs/SECURITY_BENCH_EXEC.md` | Per-step methodology (oracle verification, CTF, LLM-redteam, validation suite) |
| `config/lab_targets.yaml` | Live-target catalog (vulhub + Project Black + ptai twin) |
| `config/challenge_classes.yaml` | Challenge-class → container map |
| `playbooks/security/` | Engagement playbooks (AD, web, ICS-firmware) |
| `playbooks/security/validation/` | Validation use-cases (log4shell, kerberoast-purple) |
