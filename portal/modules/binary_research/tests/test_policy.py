"""Policy tests including the host-exec gate."""

from pathlib import Path

import pytest

from portal.modules.binary_research.harness.policy import Policy


@pytest.fixture
def policy(tmp_path: Path) -> Policy:
    return Policy(job_root=tmp_path)


class TestPaths:
    def test_within_root(self, policy: Policy, tmp_path: Path):
        (tmp_path / "artifacts").mkdir()
        assert policy.resolve_path("artifacts") == (tmp_path / "artifacts").resolve()

    def test_reject_escape(self, policy: Policy):
        with pytest.raises(PermissionError):
            policy.resolve_path("../../etc/passwd")


class TestBash:
    def test_deny_rm(self, policy: Policy):
        assert "DENIED" in (policy.check_bash("rm -rf / x") or "")

    def test_deny_network(self, policy: Policy):
        assert "allow_network" in (policy.check_bash("curl http://x") or "")

    def test_allow_safe(self, policy: Policy):
        assert policy.check_bash("readelf -a artifacts/x") is None

    def test_network_when_enabled(self, tmp_path: Path):
        assert Policy(job_root=tmp_path, allow_network=True).check_bash("curl http://x") is None


class TestHostGate:
    def test_default_off(self, policy: Policy):
        assert policy.allow_host_exec is False

    def test_on(self, tmp_path: Path):
        assert Policy(job_root=tmp_path, allow_host_exec=True).allow_host_exec is True


class TestTruncate:
    def test_short(self, policy: Policy):
        assert policy.truncate("hi") == "hi"

    def test_long(self, tmp_path: Path):
        out = Policy(job_root=tmp_path, tool_output_chars=100).truncate("x" * 500)
        assert "TRUNCATED" in out and len(out) < 500
