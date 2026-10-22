# Coder seat screening

The repository copy of the coder seat harness lives in `scripts/seat_screen/`. It creates an
isolated worktree per requested seat, commits the OpenCode provider setup, and dispatches only
seats that pass preflight. Preflight runs from the main checkout: `screen.py` invokes that
checkout's `scripts/seat_preflight.py` with `--repo` set to the seat worktree and `--config-repo`
set to the main checkout. The seat worktree's copy of the script is not what runs. The committed
provider check accepts opencode 2.0.x `providers.<id>.settings` and the older
`provider.<id>.options` schema a seat worktree at an older task base still carries. Either form
must name the portal model and a `baseURL`. A blocked preflight appends a `preflight_blocked`
row with its reasons to `seat_results.jsonl` and skips dispatch for that seat. Transient
host-quiet blockers — pytest/xdist over `UAT_MAX_PYTEST_PROCESSES`, headroom under
`UAT_MIN_HOST_HEADROOM_GIB`, and a live WFE/bench PID — are re-checked every
`--quiet-poll-seconds` (default 30) until `--quiet-max-wait-seconds` (default 20 minutes).
Each wait is logged. A card mismatch, an uncommitted `opencode.jsonc`, or the wrong engine
fails that seat on the first check.

`scripts/seat_preflight.py` applies the shared host-quiet gate before seat checks and prints a
`host_quiet` receipt with start and end snapshots. It blocks below `UAT_MIN_HOST_HEADROOM_GIB`
(default 1.5 GiB), on a live entry in `/tmp/portal5-memory-safety-test-pids`, or when detected
pytest/xdist processes exceed `UAT_MAX_PYTEST_PROCESSES` (default 5: one capped `-n 4` hook). Those three are transient
and the screen waits them out. Other host-quiet blockers, and every config blocker, fail at once.
Dispatch lane jobs and Pipeline busy requests remain visible in the snapshots but do not block
the screen.

## Run a screen

```bash
scripts/seat_screen/seat_screen2.sh --dispatch ~/.claude/orchestrate/bin/dispatch.py \
  --output-dir results/seat_screen kitqwen3827bb
```

The default setup base is `e75095ef`; pass `--base-commit` when screening from another setup
commit. Each worktree receives the provider model in `opencode.jsonc`, commits that setup, and
exports the resulting commit as `SEAT_BASE` for the grader. Worktrees and logs remain under the
output directory for review. `seat_rescreen.sh` runs the default variant/slug pairs checked
into that script, sequentially, or accepts `variant slug` pairs as arguments or on standard
input with `--stdin`. It probes both think settings and unloads resident non-E4B Ollama models
before each seat; it requires a prepared kit config and the live Portal and Ollama services.
It does not source `.env`. It reads `PIPELINE_API_KEY` and `OMLX_API_KEY` only, unsets
`PROMETHEUS_MULTIPROC_DIR`, and sets `PIPELINE_URL` to `http://localhost:9099`, so a container
pipeline URL or metrics directory in `.env` cannot fail the host preflight.
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
pass `--force`. It waits out transient host blockers before it records `preflight_blocked`.

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

## Think A/B run list

Eight kit variants pair arm A (`think: false` plus the card's instruct sampling) with arm B
(`think: true` plus the card's thinking sampling and `thinking_budget: 8192`) on one oMLX id.
Run each pair back to back, A then B, before moving to the next model: the pair is the
measurement, and a `-b` row only compares with the `-a` row taken next to it on the same host
state.

| # | arm | seat | persona slug | oMLX model id |
|---|-----|------|--------------|---------------|
| 1 | A | `auto-coding::kit-qwen38-27b-a` | `kitqwen3827ba` | `Qwen3.8-27B-oQ4e-mtp` |
| 2 | B | `auto-coding::kit-qwen38-27b-b` | `kitqwen3827bb` | `Qwen3.8-27B-oQ4e-mtp` |
| 3 | A | `auto-coding::kit-huihui36-a` | `kithuihui36a` | `Huihui-Qwen3.6-27B-abliterated-MLX-4bit` |
| 4 | B | `auto-coding::kit-huihui36-b` | `kithuihui36b` | `Huihui-Qwen3.6-27B-abliterated-MLX-4bit` |
| 5 | A | `auto-coding::kit-qwen36-27b-a` | `kitqwen3627ba` | `unsloth--Qwen3.6-27B-UD-MLX-4bit` |
| 6 | B | `auto-coding::kit-qwen36-27b-b` | `kitqwen3627bb` | `unsloth--Qwen3.6-27B-UD-MLX-4bit` |

Every seat in the list carries a persona, so `seat_rescreen.sh` and `seat_screen2.sh`
screen either arm by slug. `scripts/seat_screen/kit/run_list.txt` holds these six
`variant slug` pairs: it is the default list of `seat_rescreen.sh`, and
`seat_rescreen.sh --stdin < scripts/seat_screen/kit/run_list.txt` runs it explicitly.
Its lines may name the variant with or without the `auto-coding::` prefix.
`kit_apply.py apply --dry-run` fails when a run-list seat has no persona in
`kit/personas.yaml`. Probe each seat before the campaign:

```bash
scripts/seat_screen/probe_seat.py auto-coding::kit-qwen38-27b-a --think false
scripts/seat_screen/probe_seat.py auto-coding::kit-huihui36-a  --think false
scripts/seat_screen/probe_seat.py auto-coding::kit-qwen36-27b-a --think false
scripts/seat_screen/probe_seat.py auto-coding::kit-qwen38-27b-b --think true --qwen38
scripts/seat_screen/probe_seat.py auto-coding::kit-huihui36-b   --think true
scripts/seat_screen/probe_seat.py auto-coding::kit-qwen36-27b-b --think true
```

The Pipeline must carry the `plan/think-budget` field: without it `thinking_budget` parses into
the workspace dict but is never forwarded, so every `-b` seat silently runs uncapped. A `-b` row
whose oMLX request trace has no `thinking_budget` is invalid. Each seat needs its own WFE plan
row; no kit rows exist in `tests/wfe/workloads.yaml` yet.

## First result (2026-10-22)

The first finished pair is Qwen3.8-27B oQ4e (`Qwen3.8-27B-oQ4e-mtp`). Arm A,
`auto-coding::kit-qwen38-27b-a` (thinking off, instruct sampling), passed in 17.5 minutes.
Arm B, `auto-coding::kit-qwen38-27b-b` (thinking on), timed out. The Huihui pair
(`kit-huihui36-a`/`-b`) likewise passed arm A and failed arm B; its arm-A seat is now
`auto-coding::uncensored-agentic` and the interim `auto-spl` seat. The OrcaRouter pair
(`kit-orcarouter-a`/`-b`) failed both think arms with verified setup and was removed
2026-10-22; its seats, personas and run-list rows are gone.
