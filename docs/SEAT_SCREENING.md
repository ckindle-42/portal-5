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
output directory for review. `seat_rescreen.sh` runs the eight checked-in kit seats sequentially,
or accepts `variant slug` pairs as arguments or on standard input with `--stdin`. It probes both
think settings and unloads resident non-E4B Ollama models before each seat; it requires a prepared
kit config and the live Portal and Ollama services. The single-seat `seat_screen2.sh` runner does
not perform those probes or unloads.

The worker brief is copied from `scripts/seat_screen/SIDECAR_BENCH_BRIEF.md`. It directs the seat
not to run `launch.sh` or `sync-config`. The grader runs only repository-local checks. If it finds
changed derived artifacts, it regenerates them in a temporary copy from that seat's config and
reports exact matches under `derived_regenerated`. For `config/backends.yaml`, only an exact
match of the generated `workspace_routing` block is accepted, and all bytes outside that block
must still match `SEAT_BASE`. Other changed files remain in `stray_files` and fail `PASS`.

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

The dry run renders into a temporary repository copy and runs
`python -m tests.wfe.settings_audit --config-only --workspace auto-coding auto-spl`. It does not
write the target worktree. The screen runner does not start or stop the stack; its OpenCode
dispatch can send the worker's requested model calls through the configured Portal provider.
