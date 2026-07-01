# Lab Setup — Cold-Start Runbook

Two-tier lab: **Tier 1** (expensive, rare, idempotent — downloads everything) and **Tier 2**
(cheap, frequent — start/stop what's provisioned).

## Tier 1 — First-Time Setup (run once, re-run to update)

```bash
# Full setup (downloads vulhub, challenge composes, base images, model pulls):
./launch.sh setup

# Metadata-only (skip heavy vulhub + model pulls):
./launch.sh setup --skip-heavy

# Update an existing setup (git pull vulhub, refresh composes):
./launch.sh setup --update
```

**What `setup` downloads** (all idempotent — skips if already present/current):
- vulhub (1,234 environments, 154 families) — `git clone --depth 1` into `$LAB_DIR/vulhub`
- Purpose-built challenge composes (JWT, k8s, cloud-metadata, GraphQL — vulhub gaps)
- Base images pre-pull (heavy vulhub images + telemetry stack) for warm first `lab up`
- Security-lane model pulls (reuses `./launch.sh pull-models`)
- Seed data (sprayable accounts, breach pairs via the existing seed path)

**Disk expectation:** ~10–15 GB for vulhub (shallow clone) + models (variable). Use
`--skip-heavy` to defer large downloads.

## Tier 2 — Daily Operations

```bash
./launch.sh lab-up               # start the core lab stack
./launch.sh lab-up-wazuh         # start telemetry (Wazuh/WinEvent)
./launch.sh lab-ready            # readiness gate — GREEN = ready to bench
```

### On-Demand Targets (from lab_targets.yaml)

```bash
./launch.sh lab-targets list                                           # show catalog
./launch.sh lab-targets up vulhub-log4shell-solr                       # by catalog id
./launch.sh lab-targets up struts2/s2-045                              # by raw vulhub path
./launch.sh lab-targets ephemeral vulhub-log4shell-solr -- <bench cmd> # up → bench → down
./launch.sh lab-targets down vulhub-log4shell-solr
./launch.sh lab-targets status
```

### Lane Targets

```bash
./launch.sh lab-web-up   / lab-web-down      # SPA target (browser/OAST)
./launch.sh lab-cloud-up / lab-cloud-down    # LocalStack+kind (cloud)
./launch.sh oast-up      / oast-down         # OAST collaborator
```

## Teardown

```bash
./launch.sh lab-down                        # stop core + on-demand (no footprint)
./launch.sh lab-teardown                    # lab-down + teardown
./launch.sh lab-teardown --purge-downloads  # deep reclaim (removes vulhub clone + images)
```

Default preserves downloads (`--purge-downloads` is opt-in) so the next `lab up` is instant.

## Readiness Gate

`./launch.sh lab-ready` checks and prints a green/red board:

| Component | Required | What it checks |
|---|---|---|
| attack_image | Yes | portal5-attack built |
| attack_manifest | No | `/opt/portal5-attack.manifest.json` present |
| vulhub_cloned | Yes | `$LAB_DIR/vulhub/.git` exists |
| challenge_dirs | Yes | `$LAB_DIR/challenges/` materialized |
| telemetry | No | Wazuh/WinEvent reachable on 10.10.11.21:55000 |
| snapshots | No | `LAB_DC_VMID` set |
| disk_space | Yes | >10 GB free on `$LAB_DIR` mount |

Returns non-zero if a **required** component is RED. **Do not bench a lab that fails
lab-ready.** Best-effort components (extended arsenal, optional telemetry) warn but don't
block.

## Verification

```bash
# All these should succeed after setup:
./launch.sh setup --skip-heavy --dry-run
./launch.sh lab-ready
python3 scripts/lab_targets.py up struts2/s2-045 --dry-run
python3 scripts/lab_targets.py list | wc -l   # ≥ 7 targets
```

## Reference

| Artifact | What |
|---|---|
| `Dockerfile.attack` | Builds portal5-attack (AD arsenal required; RE/cloud/web/CTF best-effort) |
| `scripts/lab_setup.py` | Tier-1 provisioner |
| `scripts/lab_ready.py` | Readiness gate |
| `scripts/lab_targets.py` | Tier-2 on-demand container engine |
| `config/lab_targets.yaml` | Live-target catalog |
| `config/challenge_classes.yaml` | Class → container map |
| `tests/PORTAL5_BENCH_SEC_EXECUTE_V2.md` | Security bench execution runbook |
