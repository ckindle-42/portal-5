# EXECUTION DOC: Full-Coverage Live Sec Bench → Blue/Purple Proof → Stage 1/2 Gate

**Doc ID:** EXEC-SEC-FULL-COVERAGE-V1
**Supersedes (for this purpose):** `PORTAL5_BENCH_SEC_EXECUTE_V2` (stale: "8 scenarios" now 27,
`lab-up-wazuh` now Splunk, framed as model-qualification rather than blue/purple proof).
**Purpose:** Run the FULL-coverage live security bench — red generates real telemetry across the whole
lab (AD + web + meta3 + broadened vulhub), **blue/purple detects and responds against it** — validate
the run, and gate toward Stage 1/2. **Blue/purple is the driver; red is the means; the theory/workspace
prompt benches are NOT the driver and are skipped.**
**Base:** HEAD after `TASK-SEC-COVERAGE-EXPAND-V1` lands (meta3 + vulhub ~50, every scenario
blue-scorable). **Run when:** coverage expansion has landed and the lab is up.

## The framing that shapes this doc (operator's, load-bearing)

We are building **detection + response capability in a controlled lab** — a working blue/purple defender
stack. Red exploitation exists to generate the real telemetry blue must detect. So this doc:
- Runs red across FULL coverage to produce varied real attack data — NOT to qualify a model.
- Requires blue/purple to actually fire against that data (real telemetry → SPL → detection → response).
- **Skips the theory/workspace prompt benches** (`--skip-workspace-bench`) — heuristic prompt scoring
  isn't what unlocks Stage 1/2; real red→blue→purple execution is.
- Gates: a run only counts if blue/purple detected real telemetry, never synthetic (synthetic →
  indeterminate, never pass).

## Step 0 — Preconditions: full lab up, blue/purple stack live

**0a. Bring the lab up, then wait — don't probe a cold lab.** VMs/containers that were shut down
(hygiene — see the end-of-run step) take real boot time (Windows Server VMs: minutes; LXCs: seconds
to tens of seconds for their internal docker services to start). Probing immediately after start
produces false-DOWN reads that look like real outages.

```bash
# AGENT: start every lab VM/LXC that isn't already running (via the proxmox MCP: proxmox_vm_start /
# proxmox_container_start), THEN WAIT before probing:
#   - LXCs (vulhub, mbptl, splunk): ~30-60s for internal docker services to come up
#   - Windows VMs (DC, SRV, meta3-win2k8): 2-5 min for a cold boot
sleep 180   # AGENT: adjust based on what was actually cold-started; skip if everything was already up
```

**0b. Probe — real, not `--dry-run`.** `--dry-run` makes every service report reachable=True
unconditionally (it's a plumbing/plan check, not a connectivity check) — never use it to gate Step 1/2.

```bash
cd ~/path/to/portal-5
# NOTE: run via `python3 -m portal.modules.security.core` (the package's real
# location post BUILD-SPEC-PORTAL-MODULES-V1) — no PYTHONPATH export needed.
# `python3 -m bench_security` (with PYTHONPATH=tests/benchmarks) or
# `tests.benchmarks.bench_security` are dead: that shim has no __main__ entry
# point and silently no-ops instead of running the bench.
# lab reachable (the whole lab, not just AD) — standalone form works without --chain-models:
python3 -m portal.modules.security.core --probe-lab            # AGENT: confirm DC/SRV/WEB(LXC112)/meta3/mbptl reachable
# coverage really expanded (meta3 no longer 0, vulhub broadened, all blue-scorable) — --dry-run here is
# fine, this is a static resolution count, not a connectivity check:
python3 -m portal.modules.security.core --matrix-coverage --dry-run
python3 -c "from portal.modules.security.core.exec_chain import SCENARIOS; \
bad=[k for k,v in SCENARIOS.items() if not v.get('detect_ground_truth')]; \
print('scenarios:',len(SCENARIOS),'| red-only (must be empty):',bad)"
# Splunk up + HEC reachable (blue telemetry sink):
# AGENT: confirm the lab-local Splunk is up and LAB_SPLUNK_* env is set; blue reads from it.
# env for real exec:
export SANDBOX_LAB_EXEC=true          # real lab dispatch (Kali via execute_bash + phases)
```
**Gate:** all lab targets reachable, `scenarios` count reflects the expansion, zero red-only scenarios,
Splunk reachable. If any fails after the wait in 0a, treat it as a real per-service gap: record which
scenarios it touches and whether they're skippable, rather than blocking the whole run on one dead
service the available tooling can't reach to fix (no SSH/guest-agent access is a known infra gap — see
`docs/LAB_REACHABILITY_DIAGNOSTIC_2026-06-30.md`-style notes). A full lab outage (AD or the whole
subnet down) still STOPs the run — a handful of individual app-level services does not.

## Step 1 — Full-coverage RED run (generate real telemetry across the whole lab)

Red drives every scenario against real targets via Kali. This is the data-generation pass.

```bash
python3 -m portal.modules.security.core \
  --skip-workspace-bench \          # theory prompts are NOT the driver
  --lab-exec \                      # real execution against the live lab
  --all-scenarios \                 # AD + web + meta3 + broadened vulhub (all 27+)
  --chain-models <red-model(s)> \   # AGENT: the red model(s) to drive exploitation
  | tee /tmp/sec_full_red_$(date +%Y%m%dT%H%M%SZ).txt
```
Expect: real exploitation across disciplines, `lab_success` where the chain truly compromises, honest
`indeterminate`/effort-tier where it doesn't. This run ALSO ships telemetry to Splunk
(collect→ship→wait_indexed, matrix.py) so blue has real data to detect.

## Step 2 — BLUE/PURPLE run (the actual objective: detect + respond to the real telemetry)

```bash
# Blue: detect the techniques red executed, from real telemetry (Splunk SPL / WinEvent).
# Purple: red x blue interaction scoring — did blue catch what red did?
python3 -m portal.modules.security.core \
  --skip-workspace-bench \
  --lab-exec \
  --all-scenarios \
  --chain-models <red-model(s)> \
  --blue-models <blue-model(s)> \       # AGENT: blue defender model(s)
  --purple \                             # red x blue interaction scoring
  --blue-active \                        # blue can take response actions (needs --lab-exec)
  --blue-defender-model <blue-model> \
  | tee /tmp/sec_full_purple_$(date +%Y%m%dT%H%M%SZ).txt
```
**This is the point of the whole exercise.** Success = blue detects real red telemetry per scenario's
`detect_ground_truth`, purple scores red-executed-vs-blue-detected, and detection came from REAL
telemetry matching real SPL — never synthetic.

## Step 3 — Run-trust gate: is this full-coverage run trustworthy?

```bash
# system health:
python3 scripts/validate_system.py
# coverage: every discipline+target exercised, none silently empty:
python3 -m portal.modules.security.core --matrix-coverage
# integrity: blue detections came from REAL telemetry, not synthetic-fallback:
python3 - <<'PY'
import json, glob, os
f = max((x for x in glob.glob("portal/modules/security/core/results/sec_bench_*.json")
         if ".partial." not in x), key=os.path.getmtime)
d = json.load(open(f)); ct = d.get("chain_tests", [])
red_ok = sum(1 for e in ct if e.get("lab_success"))
# AGENT: read the blue/purple result fields actually written (blue_detections / purple_score / source)
print(f"latest={os.path.basename(f)} scenarios={len(ct)} red_lab_success={red_ok}")
print("Check: blue detections present, source=live (not synthetic-fallback), across disciplines.")
PY
```
**Gate:** validator green; coverage shows AD+web+meta3+vulhub all exercised (no discipline at 0); blue
detections are real (source=live), not synthetic. A run that's red-only, or where blue leaned on
synthetic telemetry, is NOT trustworthy — record what's dirty; don't feed it to Stage 1.

## Step 4 — Feed Stage 1 + re-run Stage 2 (now over full, real coverage)

```bash
# Stage 1 self-index over the full-coverage run:
python3 -m portal.modules.security.core self-index | tee /tmp/self_index_fullcov.txt
python3 -m portal.modules.security.core self-index --json > /tmp/self_index_fullcov.json
# Stage 2: web/linux/meta3 oracles now have REAL data — promotions can be earned:
python3 -m portal.modules.security.core stage2-propose | tee /tmp/stage2_fullcov.txt
```
Now the weakness view reflects the whole lab, and Stage 2's oracles have real evidence to be proven
against (the gap the earlier 0/46 exposed). Bring both artifacts to the review.

## Step 4.5 — Lab hygiene: shut down what Step 0a brought up

The lab VMs/LXCs are attack-lab infra, not always-on services — leaving them running burns host
resources for no reason once the run is done. Shut down whatever Step 0a started (mirror it: LXCs first,
then VMs), using the proxmox MCP (`proxmox_container_shutdown` / `proxmox_vm_shutdown`, graceful —
not `_stop`). Leave anything that was already up before Step 0a in whatever state it was in.

## Step 5 — STOP at the review (do not auto-advance)

This doc ends at: the full-coverage run is trustworthy, blue/purple fired on real data, Stage 1 reflects
complete coverage, and Stage 2 has real evidence. The Stage 1/2 design/approval happens WITH the
operator against these artifacts — per the crawl-before-walk gate. Explicit non-goals: no auto-applying
Stage 2 promotions (operator `--apply` only); no treating a blue-blind or synthetic run as proof.

## Report back (to the review)

Bring: (1) full-coverage confirmation — every discipline/target exercised (AD+web+meta3+vulhub), zero
red-only scenarios; (2) the blue/purple result — how many techniques blue detected from REAL telemetry,
purple red-vs-blue score, per discipline; (3) run-trust verdict (validator green, no synthetic-fallback
passes); (4) the Stage 1 full-coverage weakness view + the Stage 2 promotable count with evidence.
**That set proves the blue/purple defender stack works on real, varied data — the actual objective — and
that Stage 1/2 now reason over complete coverage. Red was the means; the working blue/purple stack is
the result.**

## Why this doc exists separately

The old exec doc qualified models against a handful of AD scenarios using theory prompts. The driver now
is different: full-coverage red execution as a telemetry generator, with blue/purple detection/response
as the measured objective, gating Stage 1/2. Different purpose, different gates (blue-fired-on-real-data,
not model-passed-heuristics) — so it's a dedicated doc, not a patch to the model-qualification one.
