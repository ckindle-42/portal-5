"""Portal 5 Adaptive UAT (TASK_UAT_ADAPTIVE_OVERHAUL_V1).

A generative, per-space-adaptive, operator-reviewed UAT layer that sits above
the fast keyword catalog. Module map:

    introspect  read live workspace/persona/module contracts from config
    generate    author deep, dimension-spanning challenges per space (seeded,
                frozen, replayable); adapts to what each space declares
    rubric      deterministic operator-scoring rubric per challenge
    run         bulk cascade execution -> full-response corpus + auto-scores
    review      HTML review packet + verdict ingest + ADAPTIVE_UAT_RESULTS.md

Entry point: tests/portal5_uat_adaptive.py, or `portal5_uat_driver.py --adaptive`.
Scope is M7 module-gated: disabled-module spaces are dropped, matching how
sync-config drops disabled-module workspaces from OWUI presets.
"""
