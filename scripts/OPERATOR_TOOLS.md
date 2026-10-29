# Operator Tools — scripts/ invoked directly by a human

The scripts in this manifest are run by a human (or an operator agent), not wired
into `validate_system.py` or a Makefile target. They read live state and print
results; they are the deliberate, documented operator surface of the repo. Listing
them here is what makes each one "referenced", so the complexity census does not
report them as unwired.

## Image / video / speech generation

```bash
./launch.sh install-mflux          # MLX-native image generation MCP (:8933)
./launch.sh install-video-mlx      # install the MLX-native video MCP (LTX-2.3, :8935); start-video-mlx runs it
python3 scripts/register_trainer_voice.py --audio <clip> --name <name> --text "<transcript>" --test
                                    # clean a recording + register it as a voice-clone trainer profile (host :8918)
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
python3 scripts/update_grafana_acceptance.py       # portal5_acceptance.json from docs/ACCEPTANCE_RESULTS.md
python3 scripts/update_grafana_benchmarks.py       # portal5_benchmarks.json from bench results
python3 scripts/update_grafana_uat.py              # portal5_uat.json from UAT_RESULTS.md
python3 scripts/blend_acceptance_results.py        # blend docs/ACCEPTANCE_RESULTS.md from git history + live file
```

## Verification and measurement

```bash
uv run python scripts/orchestration_acceptance.py --dry-run
                                    # arm smoke/wiring harness: offline fake Pipeline by default; live mode refuses while a WFE sweep is active and is not Gate B/C evidence
uv run python scripts/arm_shadow_batch.py --repeat 10 --minimum-compared 20 --output results/arm/shadow_n20.json
                                    # Spark review point: N test_fixing arm tasks from the WFE bite suite, each read/check bite detached to the shadow seat, then the shadow summary (job spec: config/arm_jobs/spark-shadow-n20.yaml)
uv run python scripts/gate_c_calculator.py <task-dir-or-receipt>...
                                    # read-only Gate C floor from arm receipts + pre-written pass_criteria; prints the value to set
python3 scripts/uat_engines.py                     # one shot per enabled engine and variant, plus engines-and-roles checks (JSON under ${PORTAL_DATA_ROOT}/uat/; --dry-run, --only ID)
python3 scripts/uat_swap.py --dry-run              # swap-sequence UAT: engine ping-pong, size ladder, the 2026-10-22 order, a concurrent pair, and a pinned seat under a long request (JSON under ${PORTAL_DATA_ROOT}/uat/; --sequence, --pinned-seat, --wait-for-quiet)
python3 scripts/check_model_bindings.py             # live gate: every model_pin/model_hint/alias/promptfoo-provider resolves to an installed Ollama tag
python3 scripts/check_updates.py                    # report upstream drift + GitHub security advisories for the Obscura pin, Ollama, oMLX, compose images, python deps, catalog models, and the orchestrator's worker harnesses (opencode/codex/grok) (weekly launchd: com.portal5.update-check); accepts a component subset, e.g. `check_updates.py ollama harnesses`
python3 scripts/model_pin_backfill.py               # dry-run: pin each hf.co id in config/backends.yaml from the local Ollama blob + HF main; --write records repo/filename/sha256 or unpinned
python3 scripts/model_autoupdate.py                 # replace catalog models whose upstream changed (weekly launchd: com.portal5.model-update); --dry-run reports, --now is the manual opt-in
python3 scripts/verify_proxmox_mcp.py              # quick Proxmox MCP check (no Docker)
python3 scripts/spine_census.py                    # wiki granularity census (mirror/surface/orphan)
python3 scripts/saluki_rule5_reverify.py          # Rule-5 loop re-verify (Ollama, one request in flight; cell tags must exist, rewrites p4_rule5_reverify.json)
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
python3 scripts/build_specimen_corpus.py            # frozen three-lane real specimen corpus builder
python3 scripts/defensive_bully_specimen_e2e.py     # P7 live-indexed real-specimen gate/cutover/rollback proof
python3 scripts/defensive_bully_train.py            # operator-gated HARV/TRAIN build, serve, and rollback surface
python3 scripts/defensive_bully_closeout.py         # fail-closed P7 proof-bundle assembler over durable evidence
python3 scripts/corpus_acquire.py                   # SA5.1 acquire/stage external corpus sources + acquisition manifest
python3 scripts/corpus_ingest.py                    # SA5.2/SA5.4 bulk-inject acquired corpora to lab Splunk (live-indexed)
python3 scripts/analyst_corpus_real_ingest.py       # SA5.5 ingest acquired cloud/identity data through analyst-corpus layer
python3 scripts/analyst_corpus_snapshot_v2.py       # SA5.6 freeze ANALYST_CORPUS_SNAPSHOT_V2 + pivot pairs
python3 scripts/defensive_bully_discovery_v3.py     # SA5.7 discovery re-run on multi-class corpus → DISCOVERY_BASELINE_V3
python3 scripts/defensive_bully_p04_adoption.py     # P0.4 embed-arm adoption bake-off (A/B/C on deduplicated set)
python3 scripts/bully_inject_capture.py             # E.5 generate/inject/capture live plural data plane run (fail-closed to the E.3 fixture)
python3 scripts/bully_universal_intake_run.py       # M.6 universal-intake verification run → BULLY_UNIVERSAL_INTAKE_RUN_M6_V1
```

## Convention

New operator tools live in `scripts/` and should be added here so the complexity
census's `unwired_scripts` stays at zero. A tool that a machine should invoke
automatically belongs in `validate_system.py` or a Makefile target instead.

## Compliance product operations

```bash
python3 scripts/materialize_internal_corpus.py --corpus coding_task/v9_compliance/ACME-CIP
                                    # P4: sourced control-block metadata + section functions onto
                                    # the canonical store, quarantines folder-derived proposals
python3 scripts/rebuild_compliance_projections.py --corpus coding_task/v9_compliance/ACME-CIP
                                    # P5/P6: rebuild retrieval+graph projections from one canonical
                                    # fingerprint, prove materialization, record index manifests
python3 scripts/verify_foundation_routed.py --service-pid <pid> --served-commit <sha>
                                    # P7: the eight foundation observations over HTTP (:8937)
python3 scripts/probe_single_part_live.py --part "CIP-007-6 R2 Part 2.2"
                                    # smallest live case with per-stage timing before expensive runs
python3 scripts/run_seven_question_routed.py [--scenario]
                                    # P6: the compound seven-question CIP-007 R2 arm through the
                                    # deployed route; --scenario adds the isolated proposed edit
python3 scripts/measure_substrate_properties.py
                                    # SUBSTRATE_PROPERTIES_V1 P6.2: re-run the superseded-competition,
                                    # recall@k and scorer-validation measurements against the live store
                                    # and index; appends nothing — overwrites the measurements JSON
python3 scripts/capture_register_standards.py --verify-sha --all
                                    # ONE_REGULATORY_EXTRACTION_V1 P3: give each of the Register's 14
                                    # standards a docling whole-document capture, sha-verified against
                                    # the Register's recorded digest — a mismatch STOPs that document
python3 scripts/anchor_requirements.py --all --report [--verify-bundle-equivalence]
                                    # ONE_REGULATORY_EXTRACTION_V1 P3/P5: anchor every requirement into
                                    # its captured revision by exact match and persist the join; every
                                    # miss lands in requirement_anchor_misses by name. Run it after any
                                    # re-capture — a moved section boundary invalidates the join.
```

## Compliance program scripts (`scripts/compliance/`)

Run by hand for the compliance program phases named in each; one line from each docstring.

| Script | Purpose |
|---|---|
| `scripts/compliance/bench_sweep_engines.py` | SPLASH_SWEEP_ACCELERATION_V1 P3 - four-arm sweep throughput measurement. |
| `scripts/compliance/calibrate_cip007.py` | CLOSEOUT_V1 P5 - CIP-007-6 calibration against the pre-sweep baseline. |
| `scripts/compliance/capture_technical_basis.py` | Every register requirement carries what it says AND how it is meant to be met. |
| `scripts/compliance/cite_and_scope_measure.py` | CITE_AND_SCOPE_V1 §P3 — assemble ``p3/measured.json`` from the receipts. |
| `scripts/compliance/correction_loop_demo.py` | MODULE_COMPLETE_V1 §P3 — the correction loop, demonstrated end to end. |
| `scripts/compliance/decide_sweep_engine.py` | SPLASH_SWEEP_ACCELERATION_V1 P5 - the promotion decision, made by the data. |
| `scripts/compliance/derive_document_scope.py` | CITE_AND_SCOPE_V1 §P2 — read every operator document ONCE and store what it |
| `scripts/compliance/lane_alteration_diff.py` | The lane-alteration diff (TASK_COMPLIANCE_PIPELINE_ALIGNMENT_V1 §P1). |
| `scripts/compliance/measure_payload_turn.py` | DATA_TRUTH DD4 — one real turn through the deployed pipeline with the DD3 |
| `scripts/compliance/pipeline_alignment_verify.py` | Live verification of the P1/P2/P3 pipeline work (PIPELINE_ALIGNMENT_V1). |
| `scripts/compliance/pipeline_call_site_ledger.py` | The live call-site ledger (TASK_COMPLIANCE_PIPELINE_ALIGNMENT_V1 §P0). |
| `scripts/compliance/reading_loop_triage.py` | Reading-seat triage: the same compliance-reading turn, direct to each engine |
| `scripts/compliance/retype_relations.py` | MODULE_COMPLETE_V1 §P1 — act on adjudicated wrong relations; supersede, never delete. |
| `scripts/compliance/self_agreement_pipeline.py` | Self-agreement on the serving engine (TASK_COMPLIANCE_PIPELINE_ALIGNMENT_V1 §P4). |
| `scripts/compliance/session_proof.py` | MODULE_COMPLETE_V1 §P2 — hold a conversation: multi-turn sessions on one thread. |
| `scripts/compliance/single_vs_split.py` | TASK_COMPLIANCE_PROVE_THE_MODULE_V1 §P4b - single model or split: the |
| `scripts/compliance/sweep_acceptance_ab.py` | Sweep acceptance A/B: map-read a standard's requirements with ``write=False`` |
| `scripts/compliance/verify_conjunction_adoption.py` | CLOSEOUT_V1 P1.3 - the no-regression guard on the conjunction adoption. |
| `scripts/compliance/verify_technical_basis_coverage.py` | MODULE_COMPLETE_V1 §P0.5 — technical-basis coverage verified per requirement. |
| `scripts/compliance/window_census.py` | The window census (TASK_COMPLIANCE_PIPELINE_ALIGNMENT_V1 §P2). |
| `scripts/compliance/write_closeout_report.py` | CLOSEOUT_V1 P9.1 - the closing report generator. |
| `scripts/compliance/write_splash_report.py` | SPLASH_SWEEP_ACCELERATION_V1 P7.1 - the splash report generator. |
