"""Portal 5 TPS benchmark package.

Decomposition of the former monolithic tests/benchmarks/bench_tps.py
(TASK_BENCH_MODULARIZE_V1). Module map:

    config.py      constants, env loading, reasoning-model detection
    prompts.py     prompt library + category maps
    discovery.py   backends.yaml/persona discovery, size estimation
    lifecycle.py   warmup/unload/idle/drain, backend health, hardware info
    results_io.py  crash-safe incremental JSON persistence
    measure.py     shared httpx client + streaming bench_tps() core
    runners.py     bench_direct / bench_pipeline / bench_personas
    report.py      console tables + availability report
    notify.py      Pushover/Telegram/Slack notifications
    cli.py         argparse main() + run orchestration

tests/benchmarks/bench_tps.py remains the operator-facing entry point as a
thin shim; invoke it exactly as before.
"""
