# QUALITY_LEDGER — TASK_PORTAL_QUALITY_V1

Single source of truth for what has been found, decided, and done during the
quality program. Append-mostly; never re-read a file marked `READ`, never
re-open a `DONE`/`BLOCKED` row. Update `status` in place.

Row schema: `| ID | file:line | cat | evidence | proposed fix | decision | status |`

- `status` — `OPEN` → `DONE` | `BLOCKED: <reason>` | `RECORDED` | `OSCILLATION`

## P0 — Seed (at `3c03cc6d`, verbatim from task §4)

| ID | file:line | cat | evidence | proposed fix | decision | status |
|---|---|---|---|---|---|---|
| Q001 | `security/core/cli.py:main` | SILENT | `def main() -> None:` — 3 returns, all `None`; no `sys.exit`/`SystemExit` anywhere in the file | `main() -> int`, thread status to the entry point | FIX-NOW | OPEN |
| Q002 | `commands/blue_modes.py` (all `run_*`) | SILENT | `print("  ERROR: ...")` then bare `return` | return `int`; `0` ok, non-zero fail | FIX-NOW | OPEN |
| Q003 | `cli.py:_dispatch_standalone` | SHAPE | returns only `True`/`False` — "handled", with no failure channel | `int \| None`: `None` = not handled | FIX-NOW | OPEN |
| Q004 | 43 files, `_load_data`/`_load_catalog` | DUP | 4–5L each, identical but for the data root: ×26, ×13, ×10, ×9 | one parameterized helper (see P2) | FIX-NOW | OPEN |
| Q005 | `blue_modes.py:282`, `:404` | RISK | `load_portal_config().workspaces.get("auto-security").variants` — `.get` returns `None` | guard the outer `.get` | FIX-NOW | OPEN |
| Q006 | `blue_modes.py`, `run.py`, `cli.py` | NOISE | 74 in-function imports; `load_episode` ×4, `SectionSpec` ×3, `load_portal_config` ×3 | lift to module level | FIX-NOW | OPEN |
| Q007 | `blue_modes.py` — 3 conventions | SHAPE | `run_x(args)` / `run_x(args, a, b, c, d, e)` / `run_x(run: BenchRun)` | one convention: `(run: BenchRun) -> int` | RECORD → P4 | OPEN |

## P1 — Exit codes (Q001–Q003)

| ID | file:line | cat | evidence | proposed fix | decision | status |
|---|---|---|---|---|---|---|
| Q001 | `security/core/cli.py:main` | SILENT | `def main() -> None:` — 3 returns, all `None`; no `sys.exit`/`SystemExit` anywhere in the file | `main() -> int`, thread status to the entry point | FIX-NOW | DONE |
| Q002 | `commands/blue_modes.py` (all `run_*`) | SILENT | `print("  ERROR: ...")` then bare `return` | return `int`; `0` ok, non-zero fail | FIX-NOW | DONE |
| Q003 | `cli.py:_dispatch_standalone` | SHAPE | returns only `True`/`False` — "handled", with no failure channel | `int \| None`: `None` = not handled | FIX-NOW | DONE |

P1 also converted the four other same-defect entry points: `scripts/gen-video.py`, `scripts/gen-image.py`, `scripts/update_workspace_tools.py`, `portal/modules/security/core/benign_corpus_bench.py` — each `main()` now returns `int` and the entry point exits with it. Golden stdout byte-identical (verified against `/tmp/q_golden_before`); listings exit 0; every error path exits non-zero.

## P2 — Loader collapse (Q004)

## P3 — Imports and guards (Q005–Q006)

## P4 — Discovery findings

## P5 — FIX-NOW work

## P6 — Final state
