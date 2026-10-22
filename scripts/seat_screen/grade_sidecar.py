#!/usr/bin/env python3
"""Grade one sidecar-task worktree against its setup commit."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_DEFAULT = "e75095ef"
SUITE = Path("tests/wfe/suites/reasoning_hard_production.jsonl")
ALLOWED = {
    "tests/wfe/suites/build_reasoning_hard_production.py",
    "tests/wfe/suites/data/reasoning_hard_items.json",
}
DERIVED_FILES = {
    ".mcp.json",
    "config/backends.yaml",
    "config/modules.generated.yaml",
}
DERIVED_PREFIXES = ("imports/openwebui/workspaces/",)
COPY_IGNORE = (
    ".git",
    ".venv",
    ".env",
    ".env.*",
    ".secrets",
    ".cache",
    ".claude",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "*.pyc",
    "results",
    "reports",
    "private",
    "field_journal",
)


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)


def _python(repo: Path) -> str:
    candidate = repo / ".venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


def _changed_files(repo: Path, base: str) -> set[str]:
    tracked = _run(["git", "diff", "--name-only", base, "--"], repo)
    if tracked.returncode:
        raise RuntimeError(f"git diff against {base} failed: {tracked.stderr.strip()}")
    untracked = _run(["git", "ls-files", "--others", "--exclude-standard"], repo)
    if untracked.returncode:
        raise RuntimeError(f"git ls-files failed: {untracked.stderr.strip()}")
    return {line for line in (tracked.stdout + untracked.stdout).splitlines() if line}


def _is_derived_candidate(path: str) -> bool:
    return path in DERIVED_FILES or any(path.startswith(prefix) for prefix in DERIVED_PREFIXES)


def _routing_parts(data: bytes) -> tuple[bytes, bytes] | None:
    text = data.decode("utf-8")
    match = re.search(r"(?m)^workspace_routing:[^\n]*(?:\n|$)", text)
    if match is None:
        return None
    tail = text[match.end() :]
    next_key = re.search(r"(?m)^(?=\S)(?!#)", tail)
    end = match.end() + (next_key.start() if next_key else len(tail))
    return text[: match.start()].encode(), text[match.start() : end].encode()


def _matches_generated(
    repo: Path, expected: Path, path: str, base_blob: bytes | None = None
) -> bool:
    actual_file = repo / path
    expected_file = expected / path
    if not actual_file.is_file() or not expected_file.is_file():
        return False
    actual = actual_file.read_bytes()
    generated = expected_file.read_bytes()
    if path != "config/backends.yaml":
        return actual == generated
    original = base_blob
    if original is None:
        return False
    actual_parts = _routing_parts(actual)
    expected_parts = _routing_parts(generated)
    original_parts = _routing_parts(original)
    return bool(
        actual_parts
        and expected_parts
        and original_parts
        and actual_parts[0] == original_parts[0]
        and actual_parts[1] == expected_parts[1]
    )


def _derived_regenerated(repo: Path, base: str, changed: set[str]) -> tuple[list[str], str | None]:
    candidates = sorted(path for path in changed if _is_derived_candidate(path))
    if not candidates:
        return [], None
    with tempfile.TemporaryDirectory(prefix="seat-sync-config-") as temp:
        expected = Path(temp) / "repo"
        ignored = shutil.ignore_patterns(*COPY_IGNORE)
        shutil.copytree(repo, expected, ignore=ignored)
        result = _run(
            [sys.executable, "-m", "portal.platform.inference.cli", "sync-config"], expected
        )
        if result.returncode:
            detail = (result.stdout + result.stderr).strip()
            return [], f"sync-config failed in grader copy: {detail[-1000:]}"
        show = _run(["git", "show", f"{base}:config/backends.yaml"], repo)
        if show.returncode and "config/backends.yaml" in candidates:
            return [], f"cannot read {base}:config/backends.yaml: {show.stderr.strip()}"
        base_backends = show.stdout.encode() if show.returncode == 0 else None
        matched = [
            path for path in candidates if _matches_generated(repo, expected, path, base_backends)
        ]
        return matched, None


def _stray_files(changed: set[str], derived_regenerated: list[str]) -> list[str]:
    ignored = {
        path for path in changed if path.startswith("coding_task/") or path.startswith(".venv/")
    }
    return sorted(changed - ALLOWED - set(derived_regenerated) - ignored)


def _temporary_suite_build(repo: Path, base: str) -> tuple[dict, str]:
    py = _python(repo)
    head = _run(["git", "show", f"{base}:{SUITE.as_posix()}"], repo)
    original_path = repo / SUITE
    original_exists = original_path.exists()
    original = original_path.read_bytes() if original_exists else b""
    result = _run([py, "-m", "tests.wfe.suites.build_reasoning_hard_production"], repo)
    output = (result.stdout + result.stderr).strip()
    byte_identical = bool(
        result.returncode == 0
        and head.returncode == 0
        and original_path.is_file()
        and original_path.read_bytes() == head.stdout.encode()
    )
    if original_exists:
        original_path.write_bytes(original)
    else:
        original_path.unlink(missing_ok=True)
    return {
        "builds": result.returncode == 0 and "36 tasks" in output,
        "byte_identical": byte_identical,
    }, output


def grade(repo: Path, base: str, log_path: Path | None = None) -> dict:
    g, _build_output = _temporary_suite_build(repo, base)
    py = _python(repo)
    tests = _run(
        [
            py,
            "-m",
            "pytest",
            "tests/wfe/tests/test_wfe_reasoning_hard_slice.py",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        repo,
    )
    test_output = (tests.stdout + tests.stderr).strip()
    g["slice_tests"] = test_output.splitlines()[-1] if test_output else "?"
    complexity = _run([sys.executable, "scripts/complexity_report.py", "--json"], repo)
    match = re.search(r'"data_lines":\s*(\d+)', complexity.stdout + complexity.stderr)
    g["data_lines"] = int(match.group(1)) if match else None
    g["data_ok"] = g["data_lines"] is not None and g["data_lines"] <= 12700
    lint = _run([py, "-m", "ruff", "check", "tests/wfe/suites"], repo)
    formatting = _run([py, "-m", "ruff", "format", "--check", "tests/wfe/suites"], repo)
    g["ruff_clean"] = lint.returncode == 0 and formatting.returncode == 0
    changed = _changed_files(repo, base)
    derived, derived_error = _derived_regenerated(repo, base, changed)
    g["derived_regenerated"] = derived
    g["stray_files"] = _stray_files(changed, derived)
    g["derived_check_error"] = derived_error
    commits = _run(["git", "log", "--oneline", f"{base}..HEAD"], repo)
    g["committed"] = commits.returncode == 0 and bool(commits.stdout.strip())
    if log_path is not None and log_path.is_file():
        timestamps: list[float] = []
        output_tokens = 0
        steps = 0
        with log_path.open() as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                stamp = event.get("timestamp")
                if isinstance(stamp, (int, float)):
                    timestamps.append(float(stamp))
                part = event.get("part") or {}
                if part.get("type") == "step-finish":
                    steps += 1
                    output_tokens += (part.get("tokens") or {}).get("output", 0) or 0
        g["wall_s"] = round((timestamps[-1] - timestamps[0]) / 1000) if timestamps else None
        g["steps"] = steps
        g["output_tokens"] = output_tokens
    g["PASS"] = bool(
        g["byte_identical"]
        and "passed" in g["slice_tests"]
        and "failed" not in g["slice_tests"]
        and g["data_ok"]
        and g["ruff_clean"]
        and not g["stray_files"]
        and not g["derived_check_error"]
    )
    return g


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("worktree", type=Path)
    parser.add_argument("log", nargs="?", type=Path)
    parser.add_argument("--base", default=os.environ.get("SEAT_BASE", BASE_DEFAULT))
    args = parser.parse_args()
    try:
        report = grade(args.worktree.resolve(), args.base, args.log)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"PASS": False, "grade_error": str(exc)}))
        return 1
    print(json.dumps(report))
    return 0 if report["PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
