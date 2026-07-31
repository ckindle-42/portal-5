# Lab Setup — Cold-Start Runbook

<!-- WIKI:GENERATED unit=unit-lab-setup-lab-setup-cold-start-runbook -->
Two-tier lab: **Tier 1** (expensive, rare, idempotent — downloads everything) and **Tier 2**
(cheap, frequent — start/stop what's provisioned).
<!-- /WIKI:GENERATED -->

---

## Tier 1 — First-Time Setup (run once, re-run to update)

<!-- WIKI:GENERATED unit=unit-lab-setup-tier-1-first-time-setup-run-once-re-run-to-update -->
```bash
<!-- /WIKI:GENERATED -->

---

# Full setup (downloads vulhub, challenge composes, base images, model pulls):

<!-- WIKI:GENERATED unit=unit-lab-setup-full-setup-downloads-vulhub-challenge-composes-base-images-model-pulls -->
./launch.sh setup
<!-- /WIKI:GENERATED -->

---

# Metadata-only (skip heavy vulhub + model pulls):

<!-- WIKI:GENERATED unit=unit-lab-setup-metadata-only-skip-heavy-vulhub-model-pulls -->
./launch.sh setup --skip-heavy
<!-- /WIKI:GENERATED -->

---

# Update an existing setup (git pull vulhub, refresh composes):

<!-- WIKI:GENERATED unit=unit-lab-setup-update-an-existing-setup-git-pull-vulhub-refresh-composes -->
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
<!-- /WIKI:GENERATED -->

---

## Tier 2 — Daily Operations

<!-- WIKI:GENERATED unit=unit-lab-setup-tier-2-daily-operations -->
```bash
./launch.sh lab-up               # start the core lab stack
./launch.sh lab-up-wazuh         # start telemetry (Wazuh/WinEvent)
./launch.sh lab-ready            # readiness gate — GREEN = ready to bench
```
<!-- /WIKI:GENERATED -->

---

### On-Demand Targets (from lab_targets.yaml)

<!-- WIKI:GENERATED unit=unit-lab-setup-on-demand-targets-from-lab-targets-yaml -->
```bash
./launch.sh lab-targets list                                           # show catalog
./launch.sh lab-targets up vulhub-log4shell-solr                       # by catalog id
./launch.sh lab-targets up struts2/s2-045                              # by raw vulhub path
./launch.sh lab-targets ephemeral vulhub-log4shell-solr -- <bench cmd> # up → bench → down
./launch.sh lab-targets down vulhub-log4shell-solr
./launch.sh lab-targets status
```
<!-- /WIKI:GENERATED -->

---

### Lane Targets

<!-- WIKI:GENERATED unit=unit-lab-setup-lane-targets -->
```bash
./launch.sh lab-web-up   / lab-web-down      # SPA target (browser/OAST)
./launch.sh lab-cloud-up / lab-cloud-down    # LocalStack+kind (cloud)
./launch.sh oast-up      / oast-down         # OAST collaborator
```
<!-- /WIKI:GENERATED -->

---

## Teardown

<!-- WIKI:GENERATED unit=unit-lab-setup-teardown -->
```bash
./launch.sh lab-down                        # stop core + on-demand (no footprint)
./launch.sh lab-teardown                    # lab-down + teardown
./launch.sh lab-teardown --purge-downloads  # deep reclaim (removes vulhub clone + images)
```

Default preserves downloads (`--purge-downloads` is opt-in) so the next `lab up` is instant.
<!-- /WIKI:GENERATED -->

---

## Readiness Gate

<!-- WIKI:GENERATED unit=unit-lab-setup-readiness-gate -->
`./launch.sh lab-ready` checks and prints a green/red board:

| Component | Required | What it checks |
|---|---|---|
| attack_image | Yes | `portal5-attack` exists in the nested DinD runtime |
| attack_manifest | Yes | Manifest is complete, its SHA-256 matches the current lab-exercise contract, and required runtime probes pass |
| vulhub_cloned | Yes | Vulhub exists on the remote lab target host |
| challenge_dirs | Yes | `$LAB_DIR/challenges/` materialized |
| static targets | Yes | DC/SRV SMB and Web HTTP are reachable from the sandbox |
| snapshots | No | Clean-baseline snapshots exist on the configured Proxmox node |
| disk_space | Yes | >10 GB free on `$LAB_DIR` mount |

Returns non-zero if a **required** component is RED. **Do not bench a lab that fails
lab-ready.** Best-effort components (extended arsenal, optional telemetry) warn but don't
block.

The image build runs `scripts/verify_attack_image.py` against
`config/attack_image_contract.json`; any absent required command or support file
fails the image build. At runtime, `lab-ready` reads the manifest from the image
inside DinD, rejects false entries, rejects an image built from an older
contract hash, and executes the contract's runtime checks. This catches tools
that are installed but unusable under the container's default capabilities.
Theory-only exercises are intentionally outside this image contract.
<!-- /WIKI:GENERATED -->

---

## Verification

<!-- WIKI:GENERATED unit=unit-lab-setup-verification -->
```bash
<!-- /WIKI:GENERATED -->

---

# All these should succeed after setup:

<!-- WIKI:GENERATED unit=unit-lab-setup-all-these-should-succeed-after-setup -->
./launch.sh setup --skip-heavy --dry-run
./launch.sh lab-ready
python3 scripts/lab_targets.py up struts2/s2-045 --dry-run
python3 scripts/lab_targets.py list | wc -l   # ≥ 7 targets
```
<!-- /WIKI:GENERATED -->

---

## Reference

<!-- WIKI:GENERATED unit=unit-lab-setup-reference -->
| Artifact | What |
|---|---|
| `Dockerfile.attack` | Builds portal5-attack (AD arsenal required; RE/cloud/web/CTF best-effort) |
| `scripts/lab_setup.py` | Tier-1 provisioner |
| `scripts/lab_ready.py` | Readiness gate |
| `scripts/lab_targets.py` | Tier-2 on-demand container engine |
| `config/lab_targets.yaml` | Live-target catalog |
| `config/challenge_classes.yaml` | Class → container map |
| `tests/PORTAL5_BENCH_SEC_EXECUTE_V2.md` | Security bench execution runbook |
<!-- /WIKI:GENERATED -->

---
