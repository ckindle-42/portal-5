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
last_generated_commit: a81c5e73569f981ecedb0d95b088563fcce651ed
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.816087
updated_at: 1783195000.816087
---

On Apple Silicon the default Ollama is native under launchd, not a container — but **not** via Homebrew. `homebrew.mxcl.ollama` was disabled and fully uninstalled 2026-08-10: Homebrew's formula lags upstream releases and shipped below this project's minimum version (`OLLAMA_MIN_VERSION` in `scripts/lib/util.sh`), and a stale Homebrew reinstall had silently taken over `:11434` at one point, running an outdated build undetected. The supported native install is a pinned binary release run as `com.portal5.ollama`, a **system** LaunchDaemon (deliberately system-domain rather than a per-user LaunchAgent, so it's up before any user is logged in). `_launch_install_ollama` in scripts/lib/services.sh reports its status (it does not install — that's a deliberate one-time manual step, see the function's own guidance); `_ensure_native_services` in scripts/lib/util.sh restarts it via `sudo -n launchctl kickstart -k system/com.portal5.ollama` whenever `up` finds it installed but not responding — passwordless sudoers rules under `/etc/sudoers.d/` (`portal5-ollama`, `portal5-claude`) cover `launchctl` and `plutil` invocations on this box (kickstart, unload/load, and in-place plist edits all run without a password prompt; plain file operations like `cp` do not — the exact per-file grant boundary is root-readable only, not verified from an unprivileged shell). The compose `ollama` service is gated behind the `docker-ollama` profile, so compose env vars (e.g. `OLLAMA_MAX_LOADED_MODELS`) do not reach the native server. The authoritative config for native is the launchd plist:

```
/Library/LaunchDaemons/com.portal5.ollama.plist
```

Root-owned — edit with `sudo`. Since the 2026-08-13 upgrade to v0.32.9, `ProgramArguments` points at `/Users/chris/ollama-current/ollama`, a symlink to the active versioned install directory (currently `ollama-0.32.9/`), not a hardcoded version path — this was a deliberate fix after the previous scheme (editing the plist's binary path on every upgrade) left the PATH symlink and the plist able to drift out of sync. **A version upgrade is now just:** unpack the new release to `~/ollama-<version>/`, flip the symlink (`ln -sfn ~/ollama-<version> ~/ollama-current`), then reload the daemon — no plist edit needed. Reload with `sudo launchctl unload /Library/LaunchDaemons/com.portal5.ollama.plist && sudo launchctl load /Library/LaunchDaemons/com.portal5.ollama.plist` (equivalent to `bootout`/`bootstrap` — both fully remove and re-register the service, re-reading the plist from disk; a mere `kickstart -k` restarts the process but does **not** re-read the plist, so it only picks up env var or `ProgramArguments` changes via the full unload/load or bootout/bootstrap cycle). The previous version directory (e.g. `ollama-0.32.7/`) is left on disk after an upgrade so a rollback is one more symlink flip, no reinstall.

## Why

Native and container Ollama are two separate config surfaces, and the compose file documents only the container one. An operator who tunes the container's env block while running native (the default) has made a change that never takes effect — the plist is the only lever that does, so the source of truth must be stated explicitly. The Homebrew-vs-pinned-install distinction is called out explicitly because the failure mode is silent: both bind the same port, so a stale Homebrew reinstall serving an outdated Ollama version produces no error, just quietly-wrong behavior (a whole 3-hour benchmark leg ran against it undetected) until someone thinks to check `/api/version` against the live server instead of trusting `command -v ollama`, which resolves whatever is first on PATH. The `ollama-current` symlink indirection exists because the direct-path scheme required editing the plist's `ProgramArguments` and the `/opt/homebrew/bin/ollama` PATH symlink separately on every upgrade — two places that could silently disagree after a future upgrade if only one got updated.
