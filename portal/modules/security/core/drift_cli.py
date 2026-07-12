"""``python3 -m portal.modules.security.core drift-check|model-canary ...``
(TASK_SEC_DRIFT_GATE_V1, Phase 3 — additive, opt-in; never runs by default).
"""

from __future__ import annotations

import json


def drift_check_main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="portal security drift-check",
        description="Rolling-baseline drift gate over the latest purple-test results",
    )
    parser.add_argument("--window", type=int, default=7, help="Trailing baseline window size")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any DRIFT-REGRESSION is found (opt-in; default just informs)",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--propose-writeback",
        action="store_true",
        help=(
            "For each confirmed DRIFT-REGRESSION, propose a cited wiki note "
            "(confirm-gated — proposes only, never auto-confirms)"
        ),
    )
    args = parser.parse_args(argv)

    from .drift_gate import drift_check, render_drift_markdown

    report = drift_check(window=args.window)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render_drift_markdown(report))

    regressions = [
        (pair["scenario"], pair["blue_model"], m)
        for pair in report["pairs"]
        for m in pair["metrics"]
        if m["status"] == "DRIFT-REGRESSION"
    ]

    if args.propose_writeback and regressions:
        _propose_drift_writeback(regressions, report)

    if args.strict and regressions:
        print(f"\nSTRICT: {len(regressions)} DRIFT-REGRESSION(s) found")
        return 1
    return 0


def _propose_drift_writeback(regressions: list[tuple[str, str, dict]], report: dict) -> None:
    """A confirmed DRIFT-REGRESSION becomes a cited wiki proposal. Propose only
    — confirm-gated (PROMOTE_POLICY: confirm-only), never auto_confirm."""
    try:
        from portal.platform.wiki.writeback import propose_unit
    except ImportError:
        print("\n(writeback skipped: portal.platform.wiki.writeback not importable)")
        return

    for scenario, blue_model, metric in regressions:
        try:
            proposal = propose_unit(
                {
                    "title": f"drift: {metric['metric']} regressed on {scenario} ({blue_model})",
                    "kind": "why",
                    "sources": [
                        {"type": "drift_gate", "path": f"results/*/purple_tests[{scenario}]"},
                    ],
                    "body": (
                        f"# Drift Regression — {metric['metric']}\n\n"
                        f"**Scenario:** {scenario}\n"
                        f"**Blue model:** {blue_model}\n"
                        f"**Metric:** {metric['metric']}\n"
                        f"**Baseline mean:** {metric['baseline_mean']} (n={metric['n_baseline']})\n"
                        f"**Candidate mean:** {metric['candidate_mean']} (n={metric['n_candidate']})\n"
                        f"**Delta:** {metric['delta']}\n"
                        f"**Method:** {metric['method']}\n"
                        f"**Detected:** {report['generated_at']}\n\n"
                        "This is a FLAG from the rolling-baseline drift gate — it does not change "
                        "any capability_verdict and did not auto-fail the run it came from.\n"
                    ),
                    "tags": [metric["metric"], "drift-gate", scenario],
                },
                proposed_by="drift_gate",
                auto_confirm=False,
            )
            print(f"  proposed: {proposal.unit_id} ({proposal.status})")
        except ValueError as e:
            print(f"  writeback skipped for {scenario}/{metric['metric']}: {e}")


def model_canary_main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="portal security model-canary",
        description="Fixed deterministic probe suite — detects the model itself has changed",
    )
    parser.add_argument("--model", required=True, help="Ollama model ID")
    parser.add_argument(
        "--save-baseline", action="store_true", help="Save this run as the new baseline"
    )
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from .drift_gate import check_model_canary, save_canary_baseline

    if args.save_baseline:
        snapshot = save_canary_baseline(args.model, ollama_url=args.ollama_url)
        if args.json:
            print(json.dumps(snapshot, indent=2, default=str))
        else:
            print(
                f"Baseline saved for {args.model}: {snapshot['pass_count']}/{snapshot['total']} passed"
            )
        return 0

    result = check_model_canary(args.model, ollama_url=args.ollama_url)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"MODEL-DRIFT: {result['status']}  ({args.model})")
        if result["status"] == "NO-BASELINE":
            print("  no saved baseline — run with --save-baseline first")
        else:
            print(f"  pass rate: {result['pass_count']}/{result['total']}")
            for f in result["flipped"]:
                print(
                    f"  FLIPPED: {f['probe']}  was_passed={f['was_passed']} now_passed={f['now_passed']}"
                )

    return 0
