#!/usr/bin/env python3
"""Run N test_fixing arm tasks and print the shadow comparison summary.

The job-facing entry point for the Spark review point: a job step carries no environment
variables and the arm CLI is outside the job runner's scripts/ allowlist. Fixtures come
from the discipline's own WFE bite suite; an existing task directory is skipped, so a
re-run continues instead of restarting. The shadow worker is detached by the service, so
the summary polls until the comparison count settles.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portal.modules.orchestration.planner import instantiate_plan_template  # noqa: E402
from portal.modules.orchestration.service import (  # noqa: E402
    ArmService,
    load_arm_config,
    seated_model_tags,
)
from portal.modules.orchestration.shadow import summarize_all  # noqa: E402
from portal.modules.orchestration.worker import Engine  # noqa: E402

DEFAULT_SUITE = ROOT / "tests" / "wfe" / "suites" / "orchestration_test_fixing.jsonl"
DEFAULT_CONFIG = ROOT / "config" / "orchestration_arm.yaml"
_IMPL_SUFFIXES = (".py",)


def _cases(suite: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line) for line in suite.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    return [row for row in rows if isinstance(row.get("seed"), dict)]


def _impl_and_test(seed: dict[str, str]) -> tuple[str, str]:
    impl = sorted(name for name in seed if name.endswith(_IMPL_SUFFIXES) and "test" not in name)
    test = sorted(name for name in seed if name.endswith(_IMPL_SUFFIXES) and "test" in name)
    if not impl or not test:
        raise ValueError(f"seed needs one implementation and one test file: {sorted(seed)}")
    return impl[0], test[0]


def materialize(case: dict[str, Any], source_dir: Path) -> dict[str, str]:
    """Write the suite's seed files and return the template's parameters."""
    source_dir.mkdir(parents=True, exist_ok=True)
    seed: dict[str, str] = case["seed"]
    for name, body in seed.items():
        (source_dir / name).write_text(body, encoding="utf-8")
    impl, test = _impl_and_test(seed)
    return {
        "source_file": impl,
        "test_file": test,
        "expected_behavior": str(case.get("instruction") or case["id"]),
    }


def _engines(config: dict[str, Any], pipeline_url: str, api_key: str) -> dict[str, Engine]:
    tags = seated_model_tags(config)
    load_plan = config.get("load_plan_models") or {}
    engines: dict[str, Engine] = {}
    for seat in ("fast", "deep"):
        digest = os.environ.get(f"PORTAL_ARM_{seat.upper()}_DIGEST", "")
        identity = load_plan.get(seat) if isinstance(load_plan, dict) else None
        if not digest or not isinstance(identity, dict) or not identity.get("model"):
            raise ValueError(
                f"set PORTAL_ARM_{seat.upper()}_DIGEST and configure load_plan_models.{seat}"
            )
        engines[seat] = Engine(
            tags[seat],
            digest,
            pipeline_url,
            api_key,
            str(identity.get("engine", "omlx")),
            str(identity.get("model", "")),
        )
    return engines


def _plans(args: argparse.Namespace, config: dict[str, Any]) -> list[tuple[str, Path, dict]]:
    plans = []
    for case in _cases(args.suite):
        for repeat in range(args.repeat):
            task_id = f"{args.prefix}-{case['id']}-{repeat:02d}"
            source_dir = args.workdir / task_id
            parameters = materialize(case, source_dir)
            plan = instantiate_plan_template(
                config,
                template_key=args.template,
                discipline_key=args.discipline,
                task_id=task_id,
                parameters=parameters,
                source_dir=source_dir,
            )
            plans.append((task_id, source_dir, plan.as_dict()))
    return plans


def _submit(
    args: argparse.Namespace, config: dict[str, Any], plans: list[tuple[str, Path, dict]]
) -> list[dict[str, str]]:
    service = ArmService(
        args.tasks_dir,
        _engines(config, args.pipeline_url, os.environ.get("PIPELINE_API_KEY", "")),
        residency_config=args.config,
    )
    submitted = []
    for task_id, source_dir, plan in plans:
        if (args.tasks_dir / task_id).exists():
            submitted.append({"task_id": task_id, "state": "already present"})
            continue
        service.submit(plan, source_dir)
        submitted.append({"task_id": task_id, "state": "ran"})
        print(f"ran {task_id}", flush=True)
    return submitted


def _summary(args: argparse.Namespace) -> dict[str, Any]:
    deadline = time.monotonic() + args.wait_seconds
    summary = summarize_all(args.tasks_dir)
    while summary["compared"] < args.minimum_compared and time.monotonic() < deadline:
        time.sleep(args.poll_seconds)
        summary = summarize_all(args.tasks_dir)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--discipline", default="test_fixing")
    parser.add_argument("--template", default="repair_with_tests")
    parser.add_argument("--repeat", type=int, default=10, help="tasks per suite case")
    parser.add_argument("--prefix", default="shadow")
    parser.add_argument("--tasks-dir", type=Path, default=None)
    parser.add_argument("--workdir", type=Path, default=None)
    parser.add_argument(
        "--pipeline-url", default=os.environ.get("PORTAL_ARM_PIPELINE_URL", "http://127.0.0.1:9099")
    )
    parser.add_argument("--minimum-compared", type=int, default=20)
    parser.add_argument("--wait-seconds", type=float, default=900.0)
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--dry-run", action="store_true", help="validate and print the plans only")
    parser.add_argument("--summary-only", action="store_true", help="print the summary only")
    parser.add_argument("--output", type=Path, help="write the JSON result here as well")
    return parser


def main(argv: list[str] | None = None) -> int:
    from portal.platform.mcp_host.workspace import get_generated_dir

    args = _parser().parse_args(argv)
    if args.repeat < 1:
        print("ERROR: --repeat must be at least 1", file=sys.stderr)
        return 2
    args.tasks_dir = args.tasks_dir or get_generated_dir("tasks")
    args.workdir = args.workdir or args.tasks_dir / "_shadow_sources"
    try:
        args.tasks_dir.mkdir(parents=True, exist_ok=True)
        config = load_arm_config(args.config)
        plans = _plans(args, config)
        if args.dry_run:
            print(json.dumps([plan for _id, _dir, plan in plans], indent=1))
            return 0
        submitted = [] if args.summary_only else _submit(args, config, plans)
        summary = _summary(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    payload = json.dumps(
        {"tasks": submitted, "shadow": summary, "minimum_compared": args.minimum_compared},
        indent=2,
        sort_keys=True,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if summary["compared"] >= args.minimum_compared else 1


if __name__ == "__main__":
    raise SystemExit(main())
