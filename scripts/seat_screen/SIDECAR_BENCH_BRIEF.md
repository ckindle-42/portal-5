# Reasoning suite builder: move item literals to a data sidecar (complexity gate)

Read `coding_task/WORKER_CONTRACT.md` first. Work only in this worktree.

Do not run `launch.sh` or `sync-config`. This seat worktree is isolated, and the
grader checks the generated suite and config outputs without touching the live stack.

`python3 scripts/complexity_report.py --gate` fails: `data_lines: 13,092 > budget 12,700`. The
cause is two module-level tables in `tests/wfe/suites/build_reasoning_hard_production.py`:
`COMPETITION` and `SCIENCE`.

## Method (do it this way)

Do **not** retype or hand-copy the data. Generate the JSON with a short script:

1. Write `/tmp/dump_items.py`: import the builder module, and `json.dump` `COMPETITION` and
   `SCIENCE` into `tests/wfe/suites/data/reasoning_hard_items.json` (indent=2,
   ensure_ascii=False). Each COMPETITION entry holds a verifier **function** at index 4: write
   its `__name__` instead.
2. In the builder, replace the two literal tables with a load of that JSON, and wherever a
   COMPETITION entry's verifier is called, resolve the stored name back to the function
   (for example `globals()[name]()`). Remove the old literals with one small edit per table:
   delete the lines with a script (`sed`/Python by line range), do not paste them into an edit.

## Checks, in this order — stop and fix if one fails

1. `cp tests/wfe/suites/reasoning_hard_production.jsonl /tmp/before.jsonl` (do this first).
2. After the change: `.venv/bin/python -m tests.wfe.suites.build_reasoning_hard_production`
   then `cmp tests/wfe/suites/reasoning_hard_production.jsonl /tmp/before.jsonl` — must be
   identical, and the builder must print "wrote … 36 tasks".
3. `.venv/bin/pytest tests/wfe/tests/test_wfe_reasoning_hard_slice.py -q`
4. `python3 scripts/complexity_report.py --gate` — report data_lines (prose may still exceed;
   do not edit the budget).
5. `.venv/bin/ruff check tests/wfe/suites && .venv/bin/ruff format tests/wfe/suites`

Do not commit (the orchestrator reviews and commits). End with a RESULT block: RESULT,
WHAT CHANGED, EVIDENCE, OPEN / RISK.
