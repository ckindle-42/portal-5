#!/usr/bin/env python3
"""Create, preflight, dispatch, and grade one or more coder-seat worktrees."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import host_quiet  # noqa: E402

DEFAULT_BASE = "e75095ef"


def _run(
    argv: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=timeout
    )


def _git(repo: Path, *args: str) -> str:
    result = _run(["git", *args], repo)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def _append_result(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def _write_setup_provider(path: Path, slug: str) -> None:
    lines = path.read_text().splitlines(True)
    model_line = f'        "{slug}": {{"name": "{slug}"}},\n'
    if any(f'"{slug}":' in line for line in lines):
        raise ValueError(f"opencode.jsonc already contains model {slug!r}")
    start = next((i for i, line in enumerate(lines) if '"portal": {' in line), None)
    if start is None:
        raise ValueError("opencode.jsonc has no Portal provider")
    models = next((i for i in range(start, len(lines)) if '"models": {' in lines[i]), None)
    if models is None:
        raise ValueError("Portal provider has no models object")
    lines.insert(models + 1, model_line)
    text = "".join(lines)
    if '"api": "openai",' not in text:
        raise ValueError("opencode.jsonc has no OpenAI provider API declaration")
    path.write_text(text.replace('"api": "openai",', '"npm": "@ai-sdk/openai-compatible",'))


def _preflight(wt: Path, slug: str, output: Path) -> tuple[bool, list[str]]:
    command = [
        "uv",
        "run",
        "--project",
        str(ROOT),
        "python",
        str(ROOT / "scripts/seat_preflight.py"),
        "--repo",
        str(wt),
        "--config-repo",
        str(ROOT),
        "--workspace",
        slug,
        "--model",
        f"opencode:portal/{slug}",
    ]
    result = _run(command, ROOT)
    output.write_text(result.stdout + result.stderr)
    reasons = []
    for line in (result.stdout + result.stderr).splitlines():
        if line.startswith("BLOCK transient:"):
            reasons.append("transient: " + line.removeprefix("BLOCK transient:").strip())
        elif line.startswith("BLOCK:"):
            reasons.append(line.removeprefix("BLOCK:").strip())
    if result.returncode and not reasons:
        reasons = [
            (result.stdout + result.stderr).strip() or f"seat preflight exited {result.returncode}"
        ]
    return result.returncode == 0, reasons


def _classified_reasons(reasons: list[str]) -> tuple[list[str], bool]:
    display: list[str] = []
    transient_only = bool(reasons)
    for reason in reasons:
        if reason.startswith("transient: "):
            display.append(reason.removeprefix("transient: "))
        else:
            transient_only = False
            display.append(reason)
    return display, transient_only


def _note_waits(output: Path, waited: list[str]) -> None:
    if waited:
        with output.open("a", encoding="utf-8") as stream:
            stream.write("\n".join(waited) + "\n")


def _preflight_until_quiet(
    args: argparse.Namespace, wt: Path, slug: str, output: Path
) -> tuple[bool, list[str]]:
    poll_s = float(getattr(args, "quiet_poll_seconds", host_quiet.DEFAULT_QUIET_POLL_S))
    max_wait_s = float(getattr(args, "quiet_max_wait_seconds", host_quiet.DEFAULT_QUIET_MAX_WAIT_S))
    deadline = time.monotonic() + max(0.0, max_wait_s)
    waited: list[str] = []
    while True:
        passed, reasons = _preflight(wt, slug, output)
        display, transient_only = _classified_reasons(reasons)
        if passed or not transient_only:
            _note_waits(output, waited)
            return passed, display
        delay = host_quiet.quiet_delay(deadline - time.monotonic(), poll_s)
        if delay is None:
            message = host_quiet.format_quiet_timeout(max_wait_s, display)
            print(message, file=sys.stderr, flush=True)
            waited.append(message)
            _note_waits(output, waited)
            return False, display
        message = host_quiet.format_quiet_wait(delay, display)
        print(message, file=sys.stderr, flush=True)
        waited.append(message)
        time.sleep(delay)


def _dispatch_log(role: str) -> Path | None:
    directory = Path.home() / ".claude/orchestrate/logs" / role.replace("-", "_")
    logs = sorted(directory.glob("*.jsonl"), key=lambda path: path.stat().st_mtime)
    return logs[-1] if logs else None


def _prepare_worktree(args: argparse.Namespace, slug: str, role: str) -> tuple[Path, str]:
    wt_root = args.output_dir / "worktrees"
    wt_root.mkdir(parents=True, exist_ok=True)
    placeholder = Path(tempfile.mkdtemp(prefix=f"{slug}-", dir=wt_root))
    placeholder.rmdir()
    wt = placeholder
    branch = f"bench/{role}"
    _git(args.repo, "worktree", "add", "-q", "-b", branch, str(wt), args.base_commit)
    setup = _run(["uv", "venv", "-q", "--python", "3.13", ".venv"], wt)
    if setup.returncode:
        raise RuntimeError((setup.stdout + setup.stderr).strip())
    setup = _run(["uv", "sync", "-q", "--all-extras"], wt)
    if setup.returncode:
        raise RuntimeError((setup.stdout + setup.stderr).strip())
    _write_setup_provider(wt / "opencode.jsonc", slug)
    setup = _run(
        ["git", "-c", "core.hooksPath=/dev/null", "commit", "-qam", "seat setup: provider"],
        wt,
    )
    if setup.returncode:
        raise RuntimeError((setup.stdout + setup.stderr).strip())
    return wt, _git(wt, "rev-parse", "HEAD")


def _dispatch_and_grade(
    args: argparse.Namespace, slug: str, role: str, wt: Path, seat_base: str
) -> dict:
    task_dir = wt / "coding_task"
    task_dir.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "coding_task/WORKER_CONTRACT.md", task_dir / "WORKER_CONTRACT.md")
    shutil.copy2(
        ROOT / "scripts/seat_screen/SIDECAR_BENCH_BRIEF.md",
        task_dir / "SIDECAR_BENCH_BRIEF.md",
    )
    dispatch_log = args.output_dir / f"seat_{slug}.log"
    environment = dict(os.environ)
    environment["SEAT_BASE"] = seat_base
    command = [
        sys.executable,
        str(args.dispatch),
        "--repo",
        str(wt),
        "run",
        "--role",
        role,
        "--model",
        f"opencode:portal/{slug}",
        "--brief",
        "coding_task/SIDECAR_BENCH_BRIEF.md",
        "--new",
        "--peak-ok",
        "--timeout",
        str(args.timeout),
    ]
    dispatched = _run(command, wt, env=environment)
    dispatch_log.write_text(dispatched.stdout + dispatched.stderr)
    grade_command = [
        sys.executable,
        str(ROOT / "scripts/seat_screen/grade_sidecar.py"),
        str(wt),
        "--base",
        seat_base,
    ]
    log_path = _dispatch_log(role)
    if log_path:
        grade_command.insert(3, str(log_path))
    graded = _run(grade_command, ROOT, env=environment)
    try:
        report = json.loads(graded.stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        report = {"PASS": False, "grade_error": graded.stdout + graded.stderr}
    report["status"] = next(
        (
            line.strip()
            for line in dispatch_log.read_text().splitlines()
            if line.startswith("status")
        ),
        "status unavailable",
    )
    return report


def _screen_one(args: argparse.Namespace, slug: str, results: Path) -> bool:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", slug):
        _append_result(
            results, {"seat": slug, "status": "setup_error", "reason": "invalid seat slug"}
        )
        return False
    started = time.time()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    role = f"seat-{slug}-{stamp}"
    wt: Path | None = None
    try:
        wt, seat_base = _prepare_worktree(args, slug, role)
        passed, reasons = _preflight_until_quiet(
            args, wt, slug, args.output_dir / f"seat_{slug}_preflight.log"
        )
        if not passed:
            _append_result(
                results,
                {
                    "seat": slug,
                    "status": "preflight_blocked",
                    "preflight_reasons": reasons,
                    "seat_base": seat_base,
                    "worktree": str(wt),
                    "wall_s": round(time.time() - started),
                },
            )
            return False
        report = _dispatch_and_grade(args, slug, role, wt, seat_base)
        report.update(
            {
                "seat": slug,
                "seat_base": seat_base,
                "worktree": str(wt),
                "wall_s": round(time.time() - started),
            }
        )
        _append_result(results, report)
        return bool(report.get("PASS"))
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        _append_result(
            results,
            {
                "seat": slug,
                "status": "setup_error",
                "reason": str(exc),
                "worktree": str(wt) if wt else None,
                "wall_s": round(time.time() - started),
            },
        )
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slugs", nargs="+")
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--base-commit", default=DEFAULT_BASE)
    parser.add_argument(
        "--dispatch", type=Path, default=Path.home() / ".claude/orchestrate/bin/dispatch.py"
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/seat_screen")
    parser.add_argument("--timeout", type=int, default=1500)
    parser.add_argument(
        "--quiet-poll-seconds",
        type=float,
        default=host_quiet.DEFAULT_QUIET_POLL_S,
        help="seconds between re-checks of a transient host blocker",
    )
    parser.add_argument(
        "--quiet-max-wait-seconds",
        type=float,
        default=host_quiet.DEFAULT_QUIET_MAX_WAIT_S,
        help="give up on a transient host blocker after this many seconds",
    )
    args = parser.parse_args()
    args.repo = args.repo.resolve()
    args.dispatch = args.dispatch.resolve()
    args.output_dir = args.output_dir.resolve()
    if not args.dispatch.is_file():
        parser.error(f"dispatch.py not found: {args.dispatch}")
    results = args.output_dir / "seat_results.jsonl"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    passed = True
    for slug in args.slugs:
        passed = _screen_one(args, slug, results) and passed
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
