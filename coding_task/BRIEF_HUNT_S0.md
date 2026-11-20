# BRIEF: hunt slice S0, truthful measurement and one path

Implement **slice S0 exactly as specified** in `docs/hunt/ORCACYBER_HUNT_PLAN.md` (§4, "S0 — Truthful measurement and one path"). Read §3 (the C0.2 measurement spec), §4 S0, and `docs/hunt/SPLUNK_REALISM_AND_SETUP.md` §2.8 (the preview-row defect) first. The hunt code is under `portal/modules/security/core/hunt/notables/`, plus `product_jobs.py` and `siem/spl_backend.py`.

Rules:
- Build only S0. Meet every acceptance bullet S0 lists. A stored run is under `/Volumes/data01/portal5_hunt/snap_neon_02cc2e3/results/hunt/neon/` and in `coding_task/scratch/` if present. The baseline must reproduce from it.
- Blind hunt rules apply. Never open the held-out proof sets or their keys: hb_ait_wheeler, hb_cloudobs_aws, botsv1. No live Splunk searches.
- Gate: `uv run pytest tests/unit/ -q && uv run ruff check . && uv run ruff format --check . && uv run mypy portal/`, plus the hunt tests under `portal/modules/security/`. Afterwards, `git checkout -- portal/modules/security/core/field_journal/_index.json` and clean new dated entries.
Commit on your branch. The RESULT gives each acceptance bullet with its proof (test name, or a command plus output), the files changed, and the baseline reproduction numbers.
