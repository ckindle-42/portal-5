# FINDING — Splunk index-time transforms need WRITE_META (stage 2, 2026-11-21)

Lane: `lane/splunk-write-meta`. Brief: `coding_task/BRIEF_SPLUNK_WRITE_META.md`.

## What was wrong

`scripts/lab/splunk_setup/conf.py` rendered every `[ph_ix_*]` transform with `REGEX` + `FORMAT`
only. Without `WRITE_META = true` Splunk runs the extraction but keeps the value out of the
tsidx, so `| tstats … by acct` answers 0 rows; `fields.conf`'s `INDEXED = true` on the same names
suppresses the search-time fallback, so `acct=*` finds nothing either. Silent, both ways.

The flag acts at index time: an index built without it must be dropped and re-shipped, a restart
is not enough.

## What now owns it

- `conf.transforms_conf()` emits `WRITE_META = true` on every stanza; the committed app tree is
  regenerated from it (`app --check` → `in_sync: true`, `drift: []`).
- `plan.entity_probe(spec)` gives each tuned index an `entity_indexed:<index>` probe
  (`| tstats count where index=<i>_v2 by <entity_field>`), and `Probe.min_rows` makes `verify`
  fail on **rows**, not on conf text: a 0-row answer is `failed: true` with
  `expected >= 1 rows, got 0`. The same `min_rows` now enforces the other `> 0 rows`
  declarations (`auth_model`, `control_tsidx_name`).
- `verify --index X` gates X only, so the rolling per-family stage 2 does not fail on families
  that are not shipped yet.

## Gate baseline (read this before blaming a lane)

`uv run mypy portal/` is **not** clean at this HEAD: 650 errors in 70 files. Proved pre-existing
by extracting `git archive HEAD` (the tree is identical to `origin/main`, `5f89f4dfe`) into a temp
dir and running mypy there with the same venv — same 650/70, no error in any file this lane
touched. Cause: `mypy portal/` follows lazy imports into `scripts/` and `tests/`
(e.g. `portal/modules/eval/persona_matrix/cli.py` imports `tests.persona_matrix_diff`), and those
trees are not strict-clean under `[tool.mypy] strict = true`. `scripts/ci_local.sh:79` runs the
same scope, so it fails at that step too.

## Orchestrator's live proof

```bash
# 1. drop the hotfix, install the regenerated default, restart (apply restarts)
ssh -i $LAB_SSH_KEY root@$LAB_PROXMOX_HOST \
  "pct exec 301 -- docker exec -u splunk splunk rm -f /opt/splunk/etc/apps/portal5_hunt_setup/local/transforms.conf"
uv run python -m scripts.lab.splunk_setup apply

# 2. rebuild each index that was shipped before the fix (flag is index-time)
uv run python -m scripts.lab.splunk_setup rollback --index santos
uv run python -m scripts.lab.splunk_setup reindex --index santos --ship

# 3. the property
uv run python -m scripts.lab.splunk_setup verify --index santos | tee coding_task/scratch/splunk_setup/verify.json
```

Worked: exit 0, `entity_indexed:hb_ait_santos_v2` has `row_count > 0`, `rows` carry real account
names. Did not: exit 1, that probe has `failed: true` and
`messages[-1] == "expected >= 1 rows, got 0"`.
