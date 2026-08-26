"""Verifier framework. Discover scripts in verifiers/, run each, grade the aggregate."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VerifierResult:
    name: str
    passed: bool
    output: str
    exit_code: int


@dataclass
class Verdict:
    results: list[VerifierResult]

    @property
    def all_pass(self) -> bool:
        return bool(self.results) and all(r.passed for r in self.results)

    @property
    def all_fail(self) -> bool:
        return bool(self.results) and all(not r.passed for r in self.results)

    @property
    def partial_pass(self) -> bool:
        if not self.results:
            return False
        return any(r.passed for r in self.results) and any(not r.passed for r in self.results)

    @property
    def no_verifiers(self) -> bool:
        return len(self.results) == 0

    @property
    def label(self) -> str:
        if self.no_verifiers:
            return "NO VERIFIERS REGISTERED"
        if self.all_pass:
            return "ALL PASS"
        if self.all_fail:
            return "ALL FAIL"
        return "PARTIAL PASS"

    def __str__(self) -> str:
        if self.no_verifiers:
            return "VERDICT: NO VERIFIERS REGISTERED — not success; treat as incomplete."
        lines = [f"VERDICT: {self.label}"]
        for r in self.results:
            lines.append(f"  {r.name}: {'PASS' if r.passed else 'FAIL'}")
        if self.partial_pass:
            failed = [r.name for r in self.results if not r.passed]
            lines.append(f"\nFailed: {', '.join(failed)}")
            lines.append("A single passing check is not completion.")
            lines.append("Revise the hypothesis that explains the failures.")
        return "\n".join(lines)


def discover_verifiers(job_dir: Path) -> list[Path]:
    vdir = job_dir / "verifiers"
    if not vdir.is_dir():
        return []
    return [
        f
        for f in sorted(vdir.iterdir())
        if f.is_file() and f.suffix in {".sh", ".py"} and not f.name.startswith(".")
    ]


def run_verifier(script: Path, job_dir: Path, *, timeout: int = 30) -> VerifierResult:
    if not os.access(script, os.X_OK):
        os.chmod(script, 0o755)
    try:
        proc = subprocess.run(
            [str(script)],
            cwd=str(job_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "JOB_DIR": str(job_dir)},
        )
        return VerifierResult(
            name=script.stem,
            passed=proc.returncode == 0,
            output=(proc.stdout + proc.stderr).strip(),
            exit_code=proc.returncode,
        )
    except subprocess.TimeoutExpired:
        return VerifierResult(script.stem, False, f"TIMEOUT after {timeout}s", -1)
    except Exception as exc:  # noqa: BLE001
        return VerifierResult(script.stem, False, f"ERROR: {exc}", -1)


def run_all(job_dir: Path, *, timeout: int = 30) -> Verdict:
    return Verdict([run_verifier(s, job_dir, timeout=timeout) for s in discover_verifiers(job_dir)])
