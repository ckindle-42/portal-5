# Lab Setup — Cold-Start Runbook

<!-- WIKI:GENERATED unit=unit-lab-setup-lab-setup-cold-start-runbook -->
Cold starts follow a two-tier model. Tier 1 is the expensive, rare, idempotent
bulk-download phase handled by `scripts/lab_setup.py`, which clones vulhub,
materializes the purpose-built challenge directories, and pulls the
security-lane models. Tier 2 is the cheap, frequent operational phase:
`./launch.sh lab-up` and `./launch.sh lab-down` start and stop the provisioned
containers from the lab profile in `deploy/portal-5/docker-compose.lab.yml`
without re-downloading anything. The tiers deliberately split provisioning cost
from daily operation so a cold start is a one-time investment.

## Why

The two-tier split exists because the downloads are the expensive part: a vulhub
clone and the model pulls happen once, while the per-day start and stop cycle
must stay nearly free. Keeping the provisioner and the operational commands
separate is what lets an operator rebuild the runtime cheaply without losing
the cached downloads.
<!-- /WIKI:GENERATED -->

---

## Tier 1 — First-Time Setup (run once, re-run to update)

<!-- WIKI:GENERATED unit=unit-lab-setup-tier-1-first-time-setup-run-once-re-run-to-update -->
The first-time setup is `python3 scripts/lab_setup.py`. It is idempotent and
safe to re-run: the vulhub step short-circuits with already cloned when the repo
exists, the challenges step recreates directories idempotently from
`config/challenge_classes.yaml`, and the models step reuses `./launch.sh
pull-models`. The --update flag is accepted by the CLI but the current
implementation gives it no distinct behavior: `setup_vulhub` never issues a git
pull, so re-running does not refresh an existing clone.

## Why

Re-running must be harmless because the provisioner is the one command an
operator re-executes after a failed or partial setup, and a non-idempotent clone
would waste the cached downloads. The inert --update flag is called out
explicitly so nobody reads the CLI help and assumes a refresh that the code does
not perform.
<!-- /WIKI:GENERATED -->

---

# Full setup (downloads vulhub, challenge composes, base images, model pulls):

<!-- WIKI:GENERATED unit=unit-lab-setup-full-setup-downloads-vulhub-challenge-composes-base-images-model-pulls -->
The full Tier-1 provisioner is invoked as `python3 scripts/lab_setup.py`. It
runs three idempotent steps from the `STEPS` table in order: the vulhub step
shallow-clones the upstream repository into `$LAB_DIR/vulhub` unless it is
already present, the challenges step materializes the purpose-built directories
named by the classes list in `config/challenge_classes.yaml`, and the models
step delegates to the existing `./launch.sh pull-models` path. There is no
separate base-image pre-pull step and no telemetry download inside this
provisioner.

## Why

The three-step split keeps the expensive, rarely-changing downloads separate
from the frequent operational phase: cloning once into `$LAB_DIR/vulhub` and
caching it across runs is what makes re-running the provisioner idempotent, and
delegating the model step to the existing pull-models command keeps a single
source of truth for which security models should be resident.
<!-- /WIKI:GENERATED -->

---

# Metadata-only (skip heavy vulhub + model pulls):

<!-- WIKI:GENERATED unit=unit-lab-setup-metadata-only-skip-heavy-vulhub-model-pulls -->
The metadata-only path is `python3 scripts/lab_setup.py --skip-heavy`. Under
the flag every step in `STEPS` short-circuits before downloading: the vulhub
clone returns skipped with the reason --skip-heavy, the challenges step returns
before materializing any directory, and the models step returns before invoking
`./launch.sh pull-models`. The provisioner therefore prints its plan and exits
having downloaded nothing. This is the safe way to prepare a lab machine when
the heavy vulhub and model downloads must be deferred to a later maintenance
window.

## Why

A --skip-heavy mode exists because the full setup can pull gigabytes across the
clone and model steps, and an operator may want to validate configuration or run
the readiness gate first. Marking the download steps heavy in the `STEPS` table
keeps the decision explicit in one place instead of scattering skip logic
through the script body.
<!-- /WIKI:GENERATED -->

---

# Update an existing setup (git pull vulhub, refresh composes):

<!-- WIKI:GENERATED unit=unit-lab-setup-update-an-existing-setup-git-pull-vulhub-refresh-composes -->
Updating an existing setup is `python3 scripts/lab_setup.py --update`, but the
flag is currently inert: `setup_vulhub` returns already cloned without running
git pull, so neither vulhub nor the other steps are refreshed. The only place a
git pull on an existing clone exists is `provision_vulhub_env` in
`scripts/lab_targets.py`, which pulls when the LXC-112 root is already a repo
and clones it when it is not. The provisioner's other steps stay idempotent:
challenges materialize purpose-built dirs from `config/challenge_classes.yaml`
and models reuse `./launch.sh pull-models`. The readiness gate requires more
than 10 GB free on the `$LAB_DIR` mount before a bench.

## Why

The update claim in the doc does not match the implementation: --update has no
code path, so this unit records where refresh actually happens, in the on-demand
provisioner's git pull. Keeping the provisioner idempotent while making refresh
explicit in `lab_targets.py` is what prevents a partial update from corrupting
a cached clone.
<!-- /WIKI:GENERATED -->

---

## Tier 2 — Daily Operations

<!-- WIKI:GENERATED unit=unit-lab-setup-tier-2-daily-operations -->
Daily operations start and stop the provisioned lab containers without
re-downloading anything. `./launch.sh lab-up` starts the core lab profile: the
Incalmo C2 and the Talon SOC analyst, from `deploy/portal-5/docker-compose.lab.yml`
via `scripts/lib/lab.sh`. `./launch.sh lab-up-wazuh` adds the full Wazuh SIEM
stack and requires LAB_OPENSEARCH_PASSWORD to be set in .env. The readiness
gate is `python3 scripts/lab_ready.py`, not a launch.sh subcommand; it exits
zero when no required check is RED.

## Why

The operational commands stay thin on purpose because the heavy work happened
during Tier 1: starting containers against an already-provisioned lab is cheap
and repeatable. The separate lab-up-wazuh variant exists because the Wazuh stack
is heavy and optional, so a plain session should not pay its memory cost.
<!-- /WIKI:GENERATED -->

---

### On-Demand Targets (from lab_targets.yaml)

<!-- WIKI:GENERATED unit=unit-lab-setup-on-demand-targets-from-lab-targets-yaml -->
On-demand targets are driven by `python3 scripts/lab_targets.py`, not by a
launch.sh subcommand. The CLI accepts up, down, ephemeral, status, and list.
The catalog is loaded from `config/lab_targets.yaml`. The up action accepts
either a catalog id such as vulhub-log4shell-solr or a raw vulhub path such as
struts2/s2-045, resolves the compose file path on LXC 112 through
`scripts/lab_host.py`, and runs docker compose up. The down action runs docker
compose down for that environment. The ephemeral action does not itself run a
bench command and does not tear the target down: it records the resolved port
mapping and writes `.port_map.json` under the security core results directory so
the bench knows where to connect.

## Why

Accepting both a catalog id and a raw vulhub path lets the operator spin up any
upstream environment without editing the catalog first, while the catalog id
path carries the cve and technique metadata the bench needs. The ephemeral
action is deliberately narrow: it only resolves and records the port mapping,
leaving the up, bench, and down steps to the caller.
<!-- /WIKI:GENERATED -->

---

### Lane Targets

<!-- WIKI:GENERATED unit=unit-lab-setup-lane-targets -->
The web-browser, cloud, and OAST lanes described in the source doc do not
exist: launch.sh has no lab-web-up, lab-cloud-up, or oast-up command. The target
lanes that are implemented are the vulhub ephemeral lane, whose catalog entries
in `config/lab_targets.yaml` are started as docker-compose environments on LXC
112 by `cmd_up` in `scripts/lab_targets.py`; the static-host lane, dc, srv, web,
and meta3 from the `lab_hosts` block, probed by `scripts/lab_ready.py` over the
AD and web ports; and the SOC-analyst lane, `./launch.sh lab-up`, which starts
the Incalmo C2 and Talon SOC analyst containers through the lab profile in
`deploy/portal-5/docker-compose.lab.yml`.

## Why

The doc promised dedicated per-lane launch commands that were never wired into
launch.sh, so this unit records the lanes that actually exist rather than the
advertised ones. The three real lanes are distinguished by lifecycle: vulhub
targets are ephemeral compose sessions, static hosts are Proxmox VMs that stay
up, and the SOC lane is a container stack for the analyst pair.
<!-- /WIKI:GENERATED -->

---

## Teardown

<!-- WIKI:GENERATED unit=unit-lab-setup-teardown -->
Teardown is lighter than the doc advertised: launch.sh implements only lab-down,
which runs docker compose down across the lab, lab-wazuh, and lab-wazuh-ui
profiles in `scripts/lib/lab.sh`, stopping the Incalmo C2, Talon SOC, and Wazuh
containers. There is no lab-teardown command and no --purge-downloads flag, so
the deep-reclaim options in the doc are not implemented. On-demand vulhub
targets are stopped individually with `python3 scripts/lab_targets.py down`,
which resolves the compose file and runs docker compose down for that single
environment on LXC 112.

## Why

The doc promised a teardown command that was never wired into launch.sh, so
recording only what lab-down actually does keeps the unit honest. The download
caches under `$LAB_DIR/vulhub` are intentionally untouched by every stop path,
which is why a later lab-up and the on-demand target engine can come back
instantly.
<!-- /WIKI:GENERATED -->

---

## Readiness Gate

<!-- WIKI:GENERATED unit=unit-lab-setup-readiness-gate -->
The readiness gate is `python3 scripts/lab_ready.py`. It prints a board of
GREEN, AMBER, and RED statuses from the `CHECKS` table and exits non-zero when a
required check is RED:

| Check | Required | What it checks |
|---|---|---|
| docker | Yes | local Docker daemon present |
| dind | Yes | portal5-dind nested daemon running |
| attack_image | Yes | portal5-attack image exists inside the DinD runtime |
| attack_manifest | Yes | in-image manifest complete, contract SHA-256 equals `config/attack_image_contract.json`, runtime probes pass |
| vulhub_clone | Yes | vulhub repo exists on the remote lab host or under `$LAB_DIR/vulhub` |
| challenge_dirs | Yes | `$LAB_DIR/challenges/` is materialized |
| disk | Yes | more than 10 GB free on the `$LAB_DIR` mount |
| ollama | No | Ollama present (best-effort) |
| dc_reachable | Yes | DC at 10.10.11.21:445 reachable from a nested attack container |
| srv_reachable | Yes | SRV at 10.10.11.33:445 reachable from a nested attack container |
| web_reachable | Yes | Web at 10.10.11.50:8080 reachable from a nested attack container |
| snapshots | No | clean-baseline snapshots exist for the DC and SRV VMIDs |

Optional checks warn but never block the gate. The attack image build runs
`verify_attack_image.py` against `config/attack_image_contract.json` inside
`Dockerfile.attack`, so an absent command or support file fails the build. At
runtime the gate reads the manifest from inside the image and rejects both false
entries and an image built from an older contract hash. Static-target
connectivity is probed with `nc -z -w 3` launched in a fresh nested attack
container; GNU timeout must not replace it because it exits 125 as PID one in
this image.

## Why

The gate exists to make a bench run against a broken lab impossible: a required
RED check is a hard stop before any scenario starts. The manifest hash check is
the sharpest part, because a rebuilt image that silently dropped a tool still
reports green to a naive existence probe, and the nested runtime probe exists
because tools installed but unusable under the container capabilities are a
failure that an ordinary which check cannot see.
<!-- /WIKI:GENERATED -->

---

## Verification

<!-- WIKI:GENERATED unit=unit-lab-setup-verification -->
Verification uses the scripts themselves, not the doc. `python3 scripts/lab_ready.py`
runs the full readiness gate and exits zero only when every required check is
GREEN. `python3 scripts/lab_discover.py` probes the live LXC 112 state read-only
through `scripts/lab_host.py` and writes the report to lab_discovery.json in the
repo root. `python3 scripts/verify_attack_image.py config/attack_image_contract.json`
checks every required tool, file, and runtime probe against the contract and
exits zero when the attack image satisfies it, failing the build otherwise.

## Why

These three commands cover the three distinct readiness questions: whether the
host-side gate passes, what the live lab actually reports from a probe that
writes nothing, and whether the attack image's manifest matches the contract
exactly. Using them together catches a stale image or a drifted host before any
benchwork starts.
<!-- /WIKI:GENERATED -->

---

# All these should succeed after setup:

<!-- WIKI:GENERATED unit=unit-lab-setup-all-these-should-succeed-after-setup -->
After a successful lab setup these commands must all exit cleanly; they are the
first checks an operator runs to confirm the provisioned environment is usable
without re-downloading anything.

python3 scripts/lab_setup.py --skip-heavy --dry-run
python3 scripts/lab_ready.py
python3 scripts/lab_targets.py up struts2/s2-045 --dry-run
python3 scripts/lab_targets.py list

## Why

The dry-run flags make the first three checks safe on a machine that has no
attack image yet: `setup` prints its plan, the target `up` path resolves the
vulhub compose path without starting it, and `lab_ready` reports which required
components are missing. The `list` command simply prints the catalog from
`config/lab_targets.yaml`, so it is the cheapest sanity check of the group.
<!-- /WIKI:GENERATED -->

---

## Reference

<!-- WIKI:GENERATED unit=unit-lab-setup-reference -->
The lab reference table maps each artifact to its role:

| Artifact | What it is |
|---|---|
| Dockerfile.attack | builds portal5-attack and verifies the lab-exercise tool contract at build time |
| scripts/lab_setup.py | Tier-1 provisioner (vulhub, challenges, models) |
| scripts/lab_ready.py | readiness gate |
| scripts/lab_targets.py | on-demand ephemeral target engine |
| config/lab_targets.yaml | live-target catalog |
| config/challenge_classes.yaml | challenge-class to container mapping |
| tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md | security bench execution runbook |
| scripts/lib/lab.sh | launch.sh lab-up, lab-down, lab-status implementations |

The bench execution runbook is version V3, not V2, and the lab container
commands live in `scripts/lib/lab.sh`, which launch.sh sources at startup.

## Why

Each artifact has a single owner file so the operator can trace a claim to its
implementation: the catalog and its classes are declarative config, the three
python scripts are the three lifecycle phases, and lab.sh is the launch.sh
integration point. Recording the current names prevents a stale artifact list
from being trusted by agents that route on unit content.
<!-- /WIKI:GENERATED -->

---
