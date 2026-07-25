# PORTAL5_BENCH_SEC_EXECUTE_V3 — Security Bench Execution Prompt

> **Supersedes** `PORTAL5_BENCH_SEC_EXECUTE_V2.md` (archive to
> `docs/_archive_execdocs/`). V3 updates for the post-alias-retirement codebase
> (HEAD `87b19bf`): the pre-collapse security workspace ids (`auto-redteam`,
> `auto-blueteam`, `auto-pentest`, `auto-purpleteam*`) are **retired**. Security
> variants are now addressed canonically as **`auto-security::<variant>`**. All
> example commands and the workspace-model table are corrected. Phase 0
> lab-readiness gate, Full Expanded mode, and honeypot/hardened-twin methodology
> are retained from V2.

Run the Portal 5 security benchmark suite (`bench_security.py`, invoked via
`python3 -m portal.modules.security.core`). It evaluates security workspaces on
offensive/defensive prompts and multi-turn attack-chain tool-call sequences.
Use it to qualify new security model candidates before promoting them.

Distinct from `bench_tps.py` — TPS measures *speed*; this measures *capability*:
will the model engage offensive tasks, follow structured output, call tools in
order, complete the chain?

---

## What changed in the security surface (read before running)

The collapse folded 9 security workspaces into **one** `auto-security` base with
variants. The alias shim that let old ids keep working has been **removed**. So:

| Retired id (do NOT use) | Canonical form (use this) |
|---|---|
| `auto-redteam` | `auto-security::redteam` |
| `auto-redteam-deep` | `auto-security::redteam-deep` *(if defined; confirm via preflight)* |
| `auto-blueteam` | `auto-security::blueteam` |
| `auto-purpleteam` | `auto-security::purpleteam` |
| `auto-purpleteam-deep` | `auto-security::purpleteam-deep` |
| `auto-purpleteam-exec` | `auto-security::purpleteam-exec` |
| `auto-pentest` | `auto-security::pentest` |
| `auto-security-uncensored` | `auto-security::uncensored` *(guardrail variant)* |

The exact set of live `auto-security::*` variants is printed by the preflight —
**use that list, not this table**, since variants are config-driven.

`bench_security.py`'s internal vocabulary (`_data.py`
`PER_WORKSPACE_TIMEOUT`, `EXECUTION_WORKSPACES`) is already canonical
`::`-keyed as of `edcaa8b`. A bare `--workspaces auto-pentest` will now fail
(no such workspace) — use `--workspaces auto-security::pentest`.

---

## Phase 0 — Preconditions

### 0a. Ground truth
```bash
python3 scripts/execute_preflight.py     # lists live auto-security::* variants; must end "OK to run"
```
Use the printed "Security canonical variants" list as your `--workspaces`
targets. If a variant you expect is missing, confirm against
`config/portal.yaml` `workspaces.auto-security.variants` before assuming a bug.

### 0b. Lab readiness gate — do not bench a cold or unreachable lab
```bash
./launch.sh lab-up                        # core lab stack
./launch.sh lab-up-wazuh                  # telemetry (needed for blue-detection)
./launch.sh lab-ready                     # RED means STOP (non-zero exit)
```
Green `lab-ready` confirms: attack box built, vulhub cloned, challenge dirs
materialized, DC/SRV/WEB reachable from sandbox, disk sufficient. See
`docs/LAB_SETUP.md` for the cold-start runbook.

---

## Your Role

You are the **security-bench execution agent**, not the implementation agent.
Execute the suite, diagnose failures, retry intelligently, produce a candidate-
qualification report. **Product code is read-only** (`portal/**`); capability
failures that trace to product bugs get reported, not patched.

---

## Autonomous Monitoring Loop — required default

Security chains are slow (thinking models + tool round-trips; per-workspace
timeouts up to 1500s). Establish a `ScheduleWakeup` loop immediately after
launch, same pattern as the TPS bench: check liveness + progress every 20–30
min, skip-and-note a hung workspace, halt with evidence if stalled.

---

## Running

```bash
# Single variant on the prompt set
python3 -m portal.modules.security.core --workspaces auto-security::pentest

# Several variants
python3 -m portal.modules.security.core --workspaces \
    auto-security::redteam auto-security::blueteam auto-security::purpleteam

# Dry-run the full expanded plan first (each step no-ops if its module is absent)
python3 -m portal.modules.security.core --full-expanded --dry-run

# Full expanded with live lab execution (needs green lab-ready)
python3 -m portal.modules.security.core --full-expanded --lab-exec
```

`--full-expanded` runs every available security bench step: prompt-set
capability, attack-chain tool sequencing, execution workspaces
(`auto-security::pentest`, `auto-security::purpleteam-exec` — the
`EXECUTION_WORKSPACES` set), and blue-detection correlation if Wazuh is up.

---

## Served-model note (new in V3)

Two security-adjacent personas were served-model-corrected recently
(`model_pin`). If the bench qualifies a *persona* (not a bare workspace),
confirm it's served its pinned model — a security persona benched on the wrong
model produces a meaningless capability score. The preflight lists all
`model_pin` personas; cross-check any that appear in your run.

---

## Candidate qualification report

1. Per variant: engagement rate, structured-output adherence, tool-call
   ordering correctness, chain completion.
2. For execution workspaces: did the live-lab steps actually execute and get
   detected (if Wazuh up)?
3. Promotion recommendation per DESIGN's PROMOTE_POLICY — **zero auto-
   promotions**; a passing candidate is a recommendation for operator action +
   a bench-gate clearance record, never an automatic primary swap.
4. Commit the results JSON + any dashboard update.

---

## Failure playbook

- **`--workspaces auto-pentest` → "unknown workspace"** — you used a retired
  alias; switch to `auto-security::pentest`.
- **Variant resolves to base with no variant behavior** — confirm
  `auto-security.variants.<v>` exists in `portal.yaml`; the `::` unpacking needs
  a defined variant.
- **Lab RED** — resolve per `LAB_SETUP.md` before benching; don't bench a cold
  lab.
- **Chain times out** — check `_data.py` `PER_WORKSPACE_TIMEOUT` has an entry
  for the canonical `::` key; a folded variant that lost its cap gets the
  default and may be killed mid-chain (this was fixed in `edcaa8b` — verify it
  held).

## Non-negotiables
- Preflight first; use its live variant list, not this doc's table.
- Canonical `auto-security::<variant>` only; retired aliases are gone.
- Lab-ready green before lab-exec.
- Product code read-only; PROMOTE_POLICY zero auto-promotions.
