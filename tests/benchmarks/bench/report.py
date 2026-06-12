"""Console reporting: availability summary and per-tier result tables.

Extracted byte-for-byte from tests/benchmarks/bench_tps.py.
"""

def _print_availability_report(
    ollama_available: bool,
    pipeline_available: bool,
    results: list[dict],
) -> None:
    """Print configured vs available vs tested vs failed counts."""
    print("\n" + "=" * 70)
    print("AVAILABILITY REPORT")
    print("=" * 70)

    ollama = [r for r in results if r.get("backend") == "ollama"]
    if ollama:
        configured = len(ollama)
        available = sum(1 for r in ollama if r.get("available", True))
        tested = sum(1 for r in ollama if r["runs_success"] > 0)
        failed = available - tested
        missing = configured - available
        print(
            f"  Ollama:  {configured} configured | {available} installed | {tested} passed | {failed} failed | {missing} not installed"
        )

    pipeline = [r for r in results if r.get("path") == "pipeline"]
    if pipeline:
        configured = len(pipeline)
        tested = sum(1 for r in pipeline if r["runs_success"] > 0)
        failed = configured - tested
        print(
            f"  Pipeline (workspaces): {configured} configured | {tested} passed | {failed} failed"
        )

    personas = [r for r in results if r.get("path") == "persona"]
    if personas:
        configured = len(personas)
        tested = sum(1 for r in personas if r["runs_success"] > 0)
        failed = configured - tested
        print(
            f"  Pipeline (personas):   {configured} configured | {tested} passed | {failed} failed"
        )

    print("=" * 70)


def _print_direct_table(results: list[dict]) -> None:
    direct = [r for r in results if r["path"] == "direct"]
    if not direct:
        return

    print("\n" + "=" * 130)
    print(
        f"{'Model':<50} {'Backend':<10} {'Size':<8} {'Status':<10} {'Avg TPS':<10} {'Q-Score':<9} {'TPS×Q':<8} {'Tokens':<8}"
    )
    print("=" * 130)
    # Sort: successful first by tps_quality desc, then unavailable
    for r in sorted(
        direct,
        key=lambda x: (x["runs_success"] > 0, x.get("tps_quality", x["avg_tps"])),
        reverse=True,
    ):
        model_short = r["model"].split("/")[-1]
        size_gb = r.get("est_memory_gb", 0)
        size_str = f"{size_gb:.0f}GB" if size_gb else "-"
        if r["runs_success"] > 0:
            qs = r.get("quality_score", 1.0)
            tq = r.get("tps_quality", r["avg_tps"])
            print(
                f"{model_short:<50} {r['backend']:<10} {size_str:<8} {'OK':<10} {r['avg_tps']:<10.1f} "
                f"{qs:<9.2f} {tq:<8.1f} {r['avg_completion_tokens']:<8}"
            )
        elif not r.get("available", True):
            print(
                f"{model_short:<50} {r['backend']:<10} {size_str:<8} {'MISSING':<10} {'-':<10} {'-':<9} {'-':<8} {'-':<8}"
            )
        else:
            errors = {run.get("error", "?") for run in r.get("runs", []) if "error" in run}
            err_short = ", ".join(errors)[:20] if errors else "error"
            print(
                f"{model_short:<50} {r['backend']:<10} {size_str:<8} {err_short:<10} {'-':<10} {'-':<9} {'-':<8} {'-':<8}"
            )
    print("=" * 130)


def _print_pipeline_table(results: list[dict]) -> None:
    pipeline = [r for r in results if r["path"] == "pipeline"]
    if not pipeline:
        return

    print("\n" + "=" * 105)
    print(
        f"{'Workspace':<30} {'Avg TPS':<10} {'Q-Score':<9} {'TPS×Q':<8} {'Tokens':<8} {'Runs':<8}"
    )
    print("=" * 105)
    for r in sorted(pipeline, key=lambda x: x.get("tps_quality", x["avg_tps"]), reverse=True):
        ws = r.get("workspace", "?")
        if r["runs_success"] > 0:
            qs = r.get("quality_score", 1.0)
            tq = r.get("tps_quality", r["avg_tps"])
            print(
                f"{ws:<30} {r['avg_tps']:<10.1f} {qs:<9.2f} {tq:<8.1f} "
                f"{r['avg_completion_tokens']:<8} {r['runs_success']}/{r['runs_total']}"
            )
        else:
            print(
                f"{ws:<30} {'FAIL':<10} {'-':<9} {'-':<8} {'-':<8} {r['runs_success']}/{r['runs_total']}"
            )
    print("=" * 105)


def _print_persona_table(results: list[dict]) -> None:
    personas = [r for r in results if r["path"] == "persona"]
    if not personas:
        return

    print("\n" + "=" * 125)
    print(
        f"{'Persona':<30} {'Category':<12} {'Workspace Model':<40} {'Avg TPS':<10} {'Q-Score':<9} {'Runs':<8}"
    )
    print("=" * 125)
    for r in sorted(personas, key=lambda x: x.get("tps_quality", x["avg_tps"]), reverse=True):
        slug = r.get("persona_slug", "?")
        cat = r.get("persona_category", "?")
        wm = r.get("workspace_model", "?")
        wm_short = wm.split("/")[-1] if "/" in wm else wm
        if r["runs_success"] > 0:
            qs = r.get("quality_score", 1.0)
            print(
                f"{slug:<30} {cat:<12} {wm_short:<40} {r['avg_tps']:<10.1f} {qs:<9.2f} {r['runs_success']}/{r['runs_total']}"
            )
        else:
            print(
                f"{slug:<30} {cat:<12} {wm_short:<40} {'FAIL':<10} {'-':<9} {r['runs_success']}/{r['runs_total']}"
            )
    print("=" * 125)
