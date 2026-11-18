"""Verifier discovery + verdict states."""

from portal.modules.binary_research.harness.verifiers import (
    Verdict,
    VerifierResult,
)


def test_all_pass() -> None:
    v = Verdict([VerifierResult("a", True, "", 0), VerifierResult("b", True, "", 0)])
    assert v.all_pass and v.label == "ALL PASS"


def test_all_fail() -> None:
    v = Verdict([VerifierResult("a", False, "", 1)])
    assert v.all_fail and v.label == "ALL FAIL"


def test_none() -> None:
    assert Verdict([]).no_verifiers
