# Operator Tools — scripts/ invoked directly by a human

The scripts in this manifest are run by a human (or an operator agent), not wired
into `validate_system.py` or a Makefile target. They read live state and print
results; they are the deliberate, documented operator surface of the repo. Listing
them here is what makes each one "referenced", so the complexity census does not
report them as unwired.

## Image / video generation

```bash
python3 scripts/gen-image.py        # rapid image generation via the ComfyUI MCP
python3 scripts/gen-video.py        # video generation via the video MCP (shelved service, retained tooling)
```

## Lab and corpus operations

```bash
python3 scripts/caldera_emulate.py                 # live Caldera/ART emulation lane → Splunk
python3 scripts/lab_discover.py                    # read-only lab host discovery (Phase 0)
python3 scripts/lab_splunkbase_install.py          # install Splunkbase apps BOTS needs
python3 scripts/execute_preflight.py               # ground-truth preflight before bench/sec/acceptance sessions
python3 scripts/security_capture_recipes.py        # capture replayable lab data by recipe
python3 scripts/security_corpus_report.py          # combined red-corpus readiness report
python3 scripts/security_replay_verify.py          # verify live captures replay into Splunk
```

## Dashboards and results

```bash
python3 scripts/update_grafana_acceptance.py       # portal5_acceptance.json from ACCEPTANCE_RESULTS.md
python3 scripts/update_grafana_benchmarks.py       # portal5_benchmarks.json from bench results
python3 scripts/update_grafana_uat.py              # portal5_uat.json from UAT_RESULTS.md
python3 scripts/blend_acceptance_results.py        # blend ACCEPTANCE_RESULTS.md from git history + live file
```

## Verification and measurement

```bash
python3 scripts/check_model_bindings.py             # live gate: every model_pin/model_hint/alias/promptfoo-provider resolves to an installed Ollama tag
python3 scripts/verify_proxmox_mcp.py              # quick Proxmox MCP check (no Docker)
python3 scripts/spine_census.py                    # wiki granularity census (mirror/surface/orphan)
python3 scripts/spine_p0_manifest.py               # TASK_BULLY_P0 P0.1 keep/release/archive classification (docs/SPINE_P0_MANIFEST.md)
python3 scripts/spine_p0_strip_pins.py             # TASK_BULLY_P0 A1 one-shot last_generated_commit stripper (already run; kept for reproducibility)
python3 scripts/spine_p0_release_prose.py          # TASK_BULLY_P0 A4 one-shot RELEASE-block un-fencer (already run; kept for reproducibility)
python3 scripts/spine_p0_archive_run.py            # TASK_BULLY_P0 A5 archive bridge-rule batch driver (docs/SPINE_P0_ARCHIVE_RUN.md)
python3 scripts/collapse_snapshot.py               # read-only surface snapshot for BUILD_PROGRAM_COLLAPSE_V1
python3 scripts/model_cleanup_audit.py              # workspace-variants + result-evidence aware model reclaim audit
python3 scripts/pending_verdicts_evidence.py        # mine PENDING_MODEL_VERDICTS.md evidence into a decision sheet
python3 scripts/fetch_pending_model_cards.py        # one-time network prefetch of model cards for pending tags
python3 scripts/pending_verdicts_report.py          # per-model informed-decision analysis (intake/capability/fleet/card-alignment)
python3 scripts/rebench_plan.py                     # category-grouped re-bench run plan from the newest analysis report
python3 scripts/execute_pending_verdicts.py         # two-stage plan/execute reclaim executor for recorded verdicts
python3 scripts/defensive_bully_calibrate.py        # frozen P6.8 cousin-calibration run + curve artifacts
python3 scripts/defensive_bully_train.py            # operator-gated HARV/TRAIN build, serve, and rollback surface
python3 scripts/defensive_bully_closeout.py         # fail-closed P7 proof-bundle assembler over durable evidence
```

## Convention

New operator tools live in `scripts/` and should be added here so the complexity
census's `unwired_scripts` stays at zero. A tool that a machine should invoke
automatically belongs in `validate_system.py` or a Makefile target instead.
