# Portal 6.0.0 — Backup & Restore Guide

This unit family documents the backup and restore surface of the platform: the `backup` and `restore` commands in `launch.sh` backed by `scripts/lib/backup.sh`. The guide header that named the version predates the current release, which is version 8.0.0 per `pyproject.toml`, but the operational surface it describes is the same two commands still wired today. The script covers the Open WebUI and Grafana volumes, `.env`, `config/`, and `imports/`.

## Why

The version label in the original guide is a snapshot artifact rather than a semantic statement about the backup code, which is why re-grounding ties these units to the actual script instead of to the dated document. Version-named documentation drifts as releases land; source-anchored units do not.

---

## What to Back Up

The backup command's artifact set is fixed and covers four things: the `portal-5_open-webui-data` volume with users and chat history, the `portal-5_grafana-data` volume with dashboards and datasources, the `.env` secrets file, and the `config/` plus `imports/` trees. Excluded by design are the `portal-5_ollama-models` weights volume and the host workspace at `${AI_OUTPUT_DIR}`, the latter being recoverable only by manual archive. This is the complete inventory; nothing outside it is snapshotted.

## Why

Publishing the exact inclusion and exclusion set prevents the two failure modes that plague backup systems: assuming a component is covered when it is not, and carrying re-downloadable bulk that slows every run. The list is derived from the literal artifact sequence in `_launch_backup`, so it stays truthful as long as the script does not change.

---

### 1. Open WebUI Data (Critical)

The `portal-5_open-webui-data` volume holds the Open WebUI database plus uploaded files the personas read, which is why the backup script treats it as the primary artifact. The backup step runs an alpine helper container that mounts the volume at `/data` and packs the directory with `tar czf`; the restore step runs the same helper but clears `/data` first, then extracts with the archive rooted at the filesystem root. Because the tarball stores absolute paths, the mount point places the content back at the correct location.

```bash
docker run --rm -v portal-5_open-webui-data:/data -v "$(pwd)":/backup alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

## Why

Operators expect chat history and identities to survive a full stack teardown, and that expectation lives entirely in this one volume. Backing it up before any configuration file matches the operator's priority ordering — a working deployment can be rebuilt from source, but the conversation data cannot be reconstructed.

---

# Manual backup

The manual one-liner for a single volume is exactly the mechanism `_launch_backup` wraps: an alpine container mounts `portal-5_open-webui-data` at `/data`, binds a host directory at `/backup`, and packs the data directory into a gzip tarball. The script hardcodes the volume names and output naming, so the raw one-liner is only useful when an operator wants a one-off snapshot outside the standard flow, such as right before a risky upgrade.

```bash
docker run --rm -v portal-5_open-webui-data:/data -v "$(pwd)":/backup alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

## Why

Exposing the primitive behind the wrapper matters because it is the same command an operator can run against a volume when the script's fixed artifact set is not enough. The script exists to standardize naming and the multi-artifact flow, while the raw invocation stays available for ad-hoc snapshots that predate the introduction of `scripts/lib/backup.sh`.

---

# With compression (faster for large volumes)

Compression is not an option the script exposes; `_launch_backup` always writes gzip tarballs via `tar czf` when packing the Open WebUI and Grafana volumes. An operator who wants the tighter `gzip -9` level must run the alpine container manually, trading wall-clock time for smaller snapshots on very large volumes. The restored content is identical either way, since tar decompression is independent of the compression level used at creation time.

```bash
docker run --rm -v portal-5_open-webui-data:/data -v "$(pwd)":/backup alpine tar -I 'gzip -9' -cf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```

## Why

The script optimizes for speed and simplicity by defaulting to standard gzip, which is fast enough for the two database volumes it handles. Compression level is a per-environment tradeoff between backup wall-clock and disk usage, so it is deliberately left to a manual invocation rather than hard-coded into the shared routine.

---

### 2. Configuration Files

Besides `config/`, the backup command copies the `imports/` directory, which holds the Open WebUI workspace presets and persona fixtures that `openwebui-init` seeds into the UI. These files are generated artifacts, so they are regenerable via `sync-config`, but shipping them in every snapshot makes a restore self-contained without requiring regeneration first. The copies land next to `config/` inside the same timestamped backup directory, so one directory represents a complete point-in-time configuration.

## Why

Persona and workspace presets are derived from config but are themselves inputs to the running Open WebUI database, so including them means recovery does not depend on re-running a generator at restore time. Storing them as plain copies alongside config keeps a single backup directory sufficient for a full reconstruction.

---

# Backup config directory

`_launch_backup` archives the configuration directory by copying it rather than tarring it: `cp -r config/` and `cp -r imports/` place the trees inside the backup path as plain directories. Because every backup run creates a fresh timestamped parent directory, the config copy can never collide with a previous run's snapshot. The `.env` file, when present, is copied alongside as a flat file so the whole backup is self-contained.

## Why

A plain copy preserves the directory structure and lets an operator diff the saved config against the live tree without extracting anything. Timestamped parents make retention trivially understandable — each directory is one complete point-in-time state, and pruning is a single removal of the oldest directories.

---

# Or just config (excluding .env for security)

The alternative of backing up only `config/` and leaving `.env` out is no longer supported by the code path. The current `_launch_backup` always copies `.env` into the snapshot, and there is no flag to omit it; the only way to produce a config-only snapshot is to copy `config/` by hand. If a config-only archive is wanted, the timestamped naming convention should still be followed so the result slots into the same restore workflow.

## Why

The code traded the option of a secret-free config archive for a simpler invariant: every backup is fully restorable. That invariant is what lets a restore be a single command instead of a puzzle about which artifacts were or were not included in a given snapshot.

---

### 3. Generated Artifacts (if applicable)

MCP servers read uploads from `${AI_OUTPUT_DIR}/uploads` and write generated artifacts under `${AI_OUTPUT_DIR}/generated/<category>`, per the workspace layout defined in `.env.example` and mounted into containers at `/workspace`. That host directory is not a Docker volume and is absent from the artifact sequence in `_launch_backup`, so `./launch.sh backup` does not cover it. The only way to capture it is a manual archive of the workspace directory.

```bash
tar czf mcp-backup-$(date +%Y%m%d).tar.gz -C "${AI_OUTPUT_DIR:-$HOME/AI_Output}" .
```

## Why

User-uploaded files and generated documents are host state, not container volumes, which is exactly why the shared-workspace rule exists; the backup script was written for Docker volumes and never taught about the host path. Until the script grows an explicit step for it, operators who value those files must schedule their own archive of the workspace.

---

### 4. Full System Backup Script

The full-system backup is not a standalone script; it is `scripts/lib/backup.sh`, which `launch.sh` sources at startup and dispatches through the `backup` and `restore` case branches. `_launch_backup` builds a directory named `portal5_backup_<YYYYmmdd_HHMMSS>` under `./backups` by default, then produces the Open WebUI and Grafana tarballs, copies `.env`, `config/`, and `imports/`, and prints the matching restore command for that exact path. `_launch_restore` consumes that directory and reverses the volume and `.env` steps.

## Why

Keeping the backup logic in a sourced library instead of a self-contained script lets `launch.sh` reuse its `ENV_FILE` and `COMPOSE_DIR` plumbing without duplicating path resolution. The timestamped subdirectory names each run's output so a restore command can target precisely the snapshot it wants, and repeated runs never overwrite each other.

---

# Backup Portal 5 data

The one-command entry point is `./launch.sh backup`, whose `_launch_backup` function orchestrates five artifacts in order: the `portal-5_open-webui-data` tarball, the `portal-5_grafana-data` tarball, a copy of `.env`, and the `config/` plus `imports/` trees. An optional positional argument overrides the output base directory, defaulting to `./backups`. Each volume tarball is produced through an alpine helper container that mounts the named volume directly, so the script does not depend on any single service being healthy.

## Why

Funneling every artifact through one command keeps the backup surface small enough to reason about and test. The script mounts volumes directly rather than asking each container to snapshot itself, which means backup succeeds even when individual services are down — the failure isolation that makes unattended runs trustworthy.

---

# Open WebUI data

The Open WebUI service in `deploy/portal-5/docker-compose.yml` mounts the named volume `open-webui-data` at `/app/backend/data`, and the project prefix turns that into `portal-5_open-webui-data` at the Docker level. The backup and restore functions reference the prefixed name directly so the alpine helper container can mount it. The volume survives `docker compose down` and is only destroyed by an explicit `clean` or `clean-all`, which is why the backup flow has to snapshot it separately.

## Why

Pinpointing the exact volume name matters because the backup script mounts it by literal name; a renamed or re-prefixed volume silently breaks both directions of the flow. Documenting that the prefix derives from the `deploy/portal-5` compose directory explains why the name is what it is, rather than being an arbitrary string in the script.

---

# Config (excluding .env for security - back that up manually)

The old guide recommended archiving `config/` while leaving `.env` out of the tarball so secrets would not ride along. The current script does the opposite: `_launch_backup` copies `.env` into every backup alongside `config/` and `imports/`, and `_launch_restore` copies it back on restore. Secrets therefore live in every snapshot directory, so the security requirement shifts from excluding them to protecting the backup location itself with the same care as the live `.env`.

## Why

Secrets are useless at restore time if the backup that carries them omits them — a restore without `.env` cannot bring the stack up with the same pipeline keys. Bundling `.env` trades the old exclusion advice for a simpler guarantee that a backup is fully restorable, at the cost of requiring the backup directory to be treated as sensitive as the live environment file.

---

# Generated artifacts (if exists)

MCP-generated artifacts and user uploads live in the host workspace at `${AI_OUTPUT_DIR}`, defaulting to `${HOME}/AI_Output` per `.env.example`. The backup command does not include this directory, and it is not a Docker volume, so nothing in `scripts/lib/backup.sh` covers it. A manual archive of the workspace is the only path: create the tarball from the directory contents when the directory exists, and skip the step entirely when it does not.

```bash
AI_OUTPUT_DIR="${AI_OUTPUT_DIR:-$HOME/AI_Output}"
if [ -d "$AI_OUTPUT_DIR" ]; then
    tar czf "${BACKUP_DIR}/mcp-${DATE}.tar.gz" -C "$AI_OUTPUT_DIR" .
fi
```

## Why

The workspace is a host directory precisely so that all MCP servers and Open WebUI share the same files without container-local copies; the backup script predates or ignores that design. Because the directory is optional and can grow large, treating its archive as a guarded, separate step keeps the core backup fast while still making artifact retention possible.

---

### 1. Open WebUI Data

Open WebUI stores users, chat history, settings, and workspace presets in the named `open-webui-data` volume, which the compose project under `deploy/portal-5` materializes as `portal-5_open-webui-data`. The `_launch_backup` function tars that volume into `openwebui-data.tar.gz` inside a fresh timestamped directory, and `_launch_restore` wipes the volume before extracting the tarball back in, so the current contents are overwritten by design. The two commands are the documented pair for moving this data around.

```bash
./launch.sh backup ./backups
./launch.sh restore ./backups/portal5_backup_20260301_120000
```

## Why

The Open WebUI database is the one piece of state the platform cannot regenerate: chat history and user accounts exist only in that volume. The restore path deliberately removes everything under the data mount before extracting, guaranteeing the recovered state matches the snapshot exactly rather than blending stale records with fresh ones.

---

# Stop services first

Restoring data should happen while the stack is down, and `_launch_restore` enforces that internally by calling the same compose teardown the `down` case uses, passing the telegram and slack profiles so profiled containers are not orphaned. The standalone `./launch.sh down` command additionally stops the native macOS services such as the MLX image/video MCPs and speech via launchctl. Backup, by contrast, mounts volumes directly and does not require the stack to be stopped first.

## Why

Volumes are safe to tar while services run, but writing restored files into a live database risks the running process overwriting them mid-restore. Restoring under a stopped stack is therefore built into the command itself rather than left to operator discipline, while the broader `down` stays available for full maintenance windows.

---

# Restore from backup

Restoring is `./launch.sh restore <backup-path>`, a deliberately interactive command: `_launch_restore` requires a directory argument, prints a warning that current data will be overwritten, and waits for an explicit `y` or `Y` confirmation before touching anything. It then stops the stack with the telegram and slack profiles, restores the Open WebUI and Grafana tarballs by clearing each volume and extracting, and copies `.env` back into place.

## Why

The confirm prompt exists because the restore path clears the destination volume before extraction — an irreversible operation that a mistaken invocation would otherwise perform silently. Making the destructive step require a typed confirmation matches the weight of the action, and the argument check rejects typos that name a nonexistent snapshot.

---

# Restart services

The final step of any restore or migration is `./launch.sh up`, which copies `.env.example` when `.env` is missing, bootstraps any unset secrets, initializes the shared workspace directories, tears down a stale stack, pulls images, starts native services, and runs the container suite. Named volumes survive this cycle, so the restored Open WebUI and Grafana data persists across the restart. The command also re-runs `openwebui-init` in the background to pick up new personas.

## Why

`up` is the single reconciliation point that makes a restore usable again: it creates the workspace structure the MCPs expect, regenerates secrets that were never stored, and brings the database-driven presets in line with config. Starting with `up` rather than raw compose commands guarantees all the launch-time preparation the stack depends on actually runs.

---

### 2. Configuration

The `config/` tree carries the operator-editable sources of truth: `portal.yaml` for workspaces and the MCP fleet, `backends.yaml` for the model catalog, and every persona file under `config/personas/`. `_launch_backup` copies the whole `config/` directory verbatim into the backup path instead of compressing it, so the layout survives byte-for-byte and can be diffed without extraction. Restore does not touch `config/`; after a restore the operator copies the saved directory back over the live tree by hand.

## Why

Configuration is cheap to store and expensive to reconstruct from memory, so the script copies it wholesale rather than pruning. Leaving config restoration out of the automated restore step is a deliberate boundary: config lives in version control too, so the backup copy is a convenience snapshot rather than the only authoritative source.

---

# Extract config (careful - may overwrite current settings)

Restoring configuration is a manual step because `_launch_restore` restores the volumes and `.env` but deliberately leaves `config/` and `imports/` alone. The operator copies the saved directories back over the live tree, and because the backup stored them as plain directories this is a file copy rather than an archive extraction. That copy is wholesale: any tuning made since the snapshot was taken is overwritten by the saved version.

## Why

Config restoration must be an explicit, careful act rather than a silent side effect of the restore command, because the saved snapshot may predate intentional changes. Keeping it manual forces the operator to look at the difference between what the backup holds and what the live tree has before choosing to replace it.

---

# After config changes, re-seed

After restoring or hand-editing config, the Open WebUI presets must be reconciled with the files on disk. The `seed` case runs `docker compose run --rm openwebui-init`, and the init container skips presets that already exist, so reseeding is additive and non-destructive. The `reseed` case forces recreation by passing `FORCE_RESEED=true`, which deletes and recreates every preset, persona prompt, and workspace tool binding before applying config afresh.

## Why

Config files and the seeded Open WebUI database are two layers that can drift apart, and `seed` is the bridge that reconciles them. The skip-existing default protects a restored chat database from having its workspace presets clobbered on boot, while the explicit force flag hands the operator a deliberate, destructive path when a clean re-apply is actually wanted.

---

### Daily Backup with Cron

A daily cadence is assembled by combining the operator's crontab with the `backup` command; there is no built-in daily job. The backup command is a one-shot, non-daemonizing run: it creates the timestamped directory, produces the artifacts, prints the restore hint, and exits. Running it from cron therefore works, but the cron environment must have access to the Docker socket and the `.env` file that `_launch_backup` sources at the top before it can mount the volumes.

## Why

A cron-triggered backup is only reliable if the command it invokes is idempotent and self-terminating, which the timestamped one-shot design guarantees. Each cron run yields an independent snapshot directory, so a failed or slow run never corrupts the previous night's backup.

---

# Add to crontab (crontab -e)

No scheduler is shipped with the project; nothing in `launch.sh` or the scripts tree registers a recurring backup job. An operator who wants unattended snapshots must add the invocation to their own crontab. Because `_launch_backup` accepts an output directory as its second argument, a cron line can pin backups to a dedicated location rather than relying on the default `./backups`, and each run lands in its own timestamped subdirectory.

```bash
0 2 * * * cd /path/to/portal-5 && ./launch.sh backup ./backups
```

## Why

Backup cadence is an operational policy, not a platform invariant, so the code deliberately leaves scheduling to the operator. Wiring in a built-in cron entry would bake assumptions about uptime and rotation that differ per deployment; exposing a plain command the operator schedules keeps the platform portable while still offering the exact entry point a cron job needs.

---

### Backup Retention

There is no retention policy implemented anywhere in the codebase: `_launch_backup` never deletes older backups, and no other script sweeps the `./backups` directory. Every run simply adds another `portal5_backup_<timestamp>` directory, so the set grows monotonically until the operator prunes it. The daily-for-a-week, weekly-for-a-month, monthly-for-a-year ladder suggested by the old guide is advisory documentation, not enforced behavior.

## Why

Retention is a capacity decision that depends on disk budget and restore SLAs, so it was left out of the automation rather than hard-coded. Making the absence explicit prevents an operator from believing old snapshots are being rotated automatically when in fact every run is retained indefinitely until someone deletes it.

---

# Cleanup old backups (run daily)

Nothing in the repo runs a daily cleanup of backup directories. The `clean` case tears down the stack and removes only the Open WebUI data volume, explicitly preserving the Ollama model volume; it does not touch anything under `./backups`. Any age-based pruning of snapshots, such as deleting tarballs older than a week, must be scheduled by the operator as a separate job operating on the backup directory.

## Why

The name `clean` means reset the Open WebUI database, not reclaim backup disk, and conflating the two would destroy recovery points during routine maintenance. Keeping snapshot pruning fully separate from stack cleanup means an operator who runs `./launch.sh clean` can be confident their restore history is untouched.

---

### Complete System Recovery

Full recovery is: reinstall the platform, restore `.env` so secrets and routing config are present, then run `./launch.sh restore <backup-path>`. The restore command stops the running stack itself, wipes and repopulates the Open WebUI and Grafana volumes, and copies `.env` back into place. The saved `config/` and `imports/` trees must be copied over manually because `_launch_restore` does not touch them, then `./launch.sh up` recreates all containers against the restored state.

## Why

The restore path deliberately limits itself to state that cannot be regenerated — the databases and the secrets file — while leaving versioned config to the operator's own copy. That split keeps the destructive command minimal and predictable; a restore that silently overwrote live config would merge an operator's post-backup tuning with stale files.

---

### Model Weights Recovery

Model weights live in the `portal-5_ollama-models` volume and are deliberately excluded from `./launch.sh backup`, which handles only the Open WebUI and Grafana volumes. The `clean-all` case removes the weights volume explicitly, while the `clean` case preserves it. Recovery is re-pulling: `./launch.sh pull-models` dispatches to `portal.platform.inference.cli models pull`, which walks the registry loaded from `config/backends.yaml` and issues native `ollama pull` commands for each configured model.

## Why

Weights are re-downloadable artifacts measured in tens of gigabytes, so backing them up would bloat every snapshot and slow every run for zero fidelity gain. The recovery loop is driven by the same registry that defines the model catalog, which means a rebuilt host converges to the configured model set without a manual inventory.

---

# Pull default model

Repopulating the model catalog on a fresh or rebuilt host is a single command: `./launch.sh pull-models`, which maps to `portal.platform.inference.cli models pull`. That command reads the registry loaded from `config/backends.yaml` and pulls every configured model, using native `ollama pull` for registry models and the Python API plus `ollama create` for HuggingFace-sourced weights. It skips models already present in Ollama, so re-running is cheap and idempotent.

## Why

Driving re-pulls from the registry rather than a hardcoded list means recovery always converges to the currently configured catalog, including models added since the last backup. The existence check makes the command safe to run after a partial pull or after the weights volume is restored, avoiding redundant downloads.

---

# Or manually

The manual model-recovery command suggested by the old guide, `docker exec ollama ollama pull`, no longer applies because the Ollama service sits behind the optional `docker-ollama` profile and the default runtime is host-native. The supported manual path is the CLI the `pull-models` case invokes, `python3 -m portal.platform.inference.cli models pull`, or a direct `ollama pull <model>` against the host's native Ollama on the default port.

## Why

The guide's docker-exec example assumes the containers-based runtime that is no longer the default, so following it on a host-native setup would fail with a missing container. Grounding the manual path in the actual CLI dispatch keeps recovery instructions aligned with how models are really pulled on this stack.

---

## Migration to New Host

Migration uses the same two commands as recovery: on the source host run `./launch.sh backup` to produce a timestamped snapshot, transfer that directory to the new machine, then on the target run `./launch.sh restore <path>`. The target must have `.env` present; `./launch.sh up` copies `.env.example` to `.env` when the file is missing, but restoring the saved `.env` preserves secrets and routing. The restored volumes and config become live once `./launch.sh up` recreates the compose project's containers.

## Why

Reusing the restore command for migration means the data format between hosts is identical to the recovery format — there is no separate migration artifact to generate or misplace. Because compose recreates the named volumes on first `up`, the operator does not need to pre-create them; restore populates them before the stack starts.

---

## What NOT to Back Up

Three artifact classes are intentionally outside the backup surface. The `portal-5_ollama-models` volume is excluded because weights are re-downloadable through `./launch.sh pull-models`. Docker images are excluded because they are rebuilt from the Dockerfiles via `./launch.sh rebuild`. The local Python environment is excluded because `uv pip install -e ".[dev]"` reproduces it from `pyproject.toml` and the lockfile. All three would multiply snapshot size for zero recovery value.

## Why

A backup's value is bounded by how much it speeds recovery of state that cannot otherwise be reproduced; weights, images, and virtual environments are all deterministic outputs of inputs already under version control. Excluding them keeps snapshots small and makes the restore contract honest about what the backup actually guarantees.

---

## Security Notes

Every backup produced by `_launch_backup` contains `.env`, including the pipeline API key, web UI secret, admin password, and any other secrets it holds. The script applies no encryption to the snapshot directory, so its confidentiality depends entirely on the filesystem permissions and physical security of the backup location. That elevates the backup directory to the same sensitivity class as the live `.env` file, with offsite or encrypted copies being the operator's responsibility.

## Why

The security model inverts the old advice: instead of keeping secrets out of backups, the code keeps them in backups and relies on the location being protected. Documenting that the snapshot is plaintext secrets at rest tells an operator why the backup directory must be treated like a credentials vault rather than a log archive.

---
