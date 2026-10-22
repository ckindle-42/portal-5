# Coder seat screening

The repository copy of the coder seat harness lives in `scripts/seat_screen/`. It creates an
isolated worktree per requested seat, commits the OpenCode provider setup, runs
`scripts/seat_preflight.py` against that worktree, and dispatches only seats that pass. A blocked
preflight appends a `preflight_blocked` row with its reasons to `seat_results.jsonl` and skips
dispatch for that seat.

## Run a screen

```bash
scripts/seat_screen/seat_screen2.sh --dispatch ~/.claude/orchestrate/bin/dispatch.py \
  --output-dir results/seat_screen kitqwen3827b
```

The default setup base is `e75095ef`; pass `--base-commit` when screening from another setup
commit. Each worktree receives the provider model in `opencode.jsonc`, commits that setup, and
exports the resulting commit as `SEAT_BASE` for the grader. Worktrees and logs remain under the
output directory for review. `seat_rescreen.sh` runs the default variant/slug pairs checked
into that script, sequentially, or accepts `variant slug` pairs as arguments or on standard
input with `--stdin`. It probes both think settings and unloads resident non-E4B Ollama models
before each seat; it requires a prepared kit config and the live Portal and Ollama services.
The single-seat `seat_screen2.sh` runner does not perform those probes or unloads.

The worker brief is copied from `scripts/seat_screen/SIDECAR_BENCH_BRIEF.md`. It directs the seat
not to run `launch.sh` or `sync-config`. The grader runs only repository-local checks. If it finds
changed derived artifacts, it regenerates them with
`python -m portal.platform.inference.cli sync-config` in a temporary copy and reports matches
under `derived_regenerated`. Derived files other than `config/backends.yaml` must be
byte-identical to that copy. For `config/backends.yaml`, the bytes before `workspace_routing`
must match `SEAT_BASE` and the `workspace_routing` block must match the regenerated block.
Bytes after that block are not part of the comparison. A failed regeneration is
`derived_check_error` and fails `PASS`. Other changed files remain in `stray_files` and fail
`PASS`. `scripts/seat_preflight.py` also runs the host-quiet gate before the config checks and
blocks the seat when the host is busy, unless `--force` is passed. The screen runner does not
pass `--force`.

## Apply or revert the kit

`kit_apply.py` renders the experimental variant, backend, and persona data from `kit/` into a
target worktree. Applying saves backups under `~/.local/state/portal5-seat-screen/<repo-hash>`;
`--backup-dir` can set a different location. Revert refuses to overwrite config or persona files
that changed after apply.

```bash
scripts/seat_screen/kit_apply.py apply --repo /path/to/worktree --dry-run
scripts/seat_screen/kit_apply.py apply --repo /path/to/worktree
scripts/seat_screen/kit_apply.py revert --repo /path/to/worktree
```

A dry run of apply or revert renders that action into a temporary repository copy and runs
`python -m tests.wfe.settings_audit --config-only` for `auto-coding`, `auto-spl`, and every
variant of those workspaces, including every seat the kit leaves applied. It does not
write the target worktree. The screen runner does not start or stop the stack; its OpenCode
dispatch can send the worker's requested model calls through the configured Portal provider.
