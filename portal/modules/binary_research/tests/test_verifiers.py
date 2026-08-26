"""Verifier discovery + verdict states."""

from pathlib import Path

import pytest

from portal.modules.binary_research.harness.verifiers import (
    Verdict,
    VerifierResult,
    discover_verifiers,
    run_all,
)


@pytest.fixture
def job(tmp_path: Path) -> Path:
    v = tmp_path / "verifiers"
    v.mkdir()
    (v / "p.sh").write_text("#!/bin/bash\necho PASS\nexit 0\n")
    (v / "p.sh").chmod(0o755)
    (v / "f.sh").write_text("#!/bin/bash\necho FAIL\nexit 1\n")
    (v / "f.sh").chmod(0o755)
    return tmp_path


def test_discover(job: Path):
    assert len(discover_verifiers(job)) == 2


def test_partial(job: Path):
    v = run_all(job)
    assert v.partial_pass and v.label == "PARTIAL PASS"


def test_all_pass():
    v = Verdict([VerifierResult("a", True, "", 0), VerifierResult("b", True, "", 0)])
    assert v.all_pass and v.label == "ALL PASS"


def test_all_fail():
    v = Verdict([VerifierResult("a", False, "", 1)])
    assert v.all_fail and v.label == "ALL FAIL"


def test_none():
    assert Verdict([]).no_verifiers
