---
id: unit-ADMIN_GUIDE-ollama-is-native-plist-is-the-source-of-truth
kind: why
title: "ADMIN_GUIDE \u2014 Ollama is Native \u2014 Plist Is the Source of Truth"
sources:
- type: code
  path: scripts/lib/services.sh
- type: code
  path: scripts/lib/util.sh
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: scripts/engine_autoupdate.py
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.816087
updated_at: 1790333591
---

On Apple Silicon the default Ollama is native under launchd, not a container — but **not** via Homebrew. `homebrew.mxcl.ollama` was disabled and fully uninstalled 2026-08-10: Homebrew's formula lags upstream releases and shipped below this project's minimum version (`OLLAMA_MIN_VERSION` in `scripts/lib/util.sh`), and a stale Homebrew reinstall had silently taken over `:11434` at one point, running an outdated build undetected. The supported native install is a pinned binary release run as `com.portal5.ollama`, a **system** LaunchDaemon (deliberately system-domain rather than a per-user LaunchAgent, so it's up before any user is logged in). `_launch_install_ollama` in scripts/lib/services.sh reports its status (it does not install — that's a deliberate one-time manual step, see the function's own guidance); `_ensure_native_services` in scripts/lib/util.sh restarts it via `sudo -n launchctl kickstart -k system/com.portal5.ollama` whenever `up` finds it installed but not responding — passwordless sudoers rules under `/etc/sudoers.d/` (`portal5-ollama`, `portal5-claude`) cover `launchctl` and `plutil` invocations on this box (kickstart, unload/load, and in-place plist edits all run without a password prompt; plain file operations like `cp` do not — the exact per-file grant boundary is root-readable only, not verified from an unprivileged shell). The compose `ollama` service is gated behind the `docker-ollama` profile, so compose env vars (e.g. `OLLAMA_MAX_LOADED_MODELS`) do not reach the native server. The authoritative config for native is the launchd plist:

```
/Library/LaunchDaemons/com.portal5.ollama.plist
```

Root-owned — edit with `sudo`. `ProgramArguments` points at `/Users/chris/ollama-current/ollama`; since 2026-09-25 `~/ollama-current` is a symlink to `~/ollama-live/`, a **fixed real path** whose contents are the active release (its version in `~/ollama-live/VERSION`), with every release archived as `~/ollama-<version>/` for rollback. The path is fixed because macOS keys an unbundled binary's permission to read the external `data01` volume (where `OLLAMA_MODELS` lives) to its path plus its Developer ID requirement, which is identical across Ollama releases — a new path per version meant a new approval popup per upgrade. **Upgrades are automatic:** `scripts/engine_autoupdate.py` (daily launchd job `com.portal5.engine-update`, installed by `./launch.sh up`) installs the newest non-pre-release weekly — sooner when a release in the gap carries a security fix, or on `--now` — kickstarts the daemon, waits for the model count to return (asking via Pushover for the data01 popup if it does not), and runs `scripts/engine_contract_check.py`. A contract failure rolls back to the previous release and records the rejected version in `~/.portal5/engine_update.json`; an unanswered popup rolls back and retries the next day. A plist edit still needs the full unload/load (a `kickstart -k` restarts the process but does not re-read the plist).

## Why

Native and container Ollama are two separate config surfaces, and the compose file documents only the container one. An operator who tunes the container's env block while running native (the default) has made a change that never takes effect — the plist is the only lever that does, so the source of truth must be stated explicitly. The Homebrew-vs-pinned-install distinction is called out explicitly because the failure mode is silent: both bind the same port, so a stale Homebrew reinstall serving an outdated Ollama version produces no error, just quietly-wrong behavior (a whole 3-hour benchmark leg ran against it undetected) until someone thinks to check `/api/version` against the live server instead of trusting `command -v ollama`, which resolves whatever is first on PATH. The `ollama-current` symlink indirection exists because the direct-path scheme required editing the plist's `ProgramArguments` and the `/opt/homebrew/bin/ollama` PATH symlink separately on every upgrade — two places that could silently disagree after a future upgrade if only one got updated.
