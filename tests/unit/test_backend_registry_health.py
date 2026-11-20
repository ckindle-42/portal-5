"""Tests for health hysteresis, workspace_routes property, candidate-cache
clamping, and tool-support map in BackendRegistry."""

from portal.platform.inference.cluster_backends import BackendRegistry


class TestPreferredResidents:
    """`defaults.preferred_residents`: workspace ids kept warm (2026-11-16 seat 3)."""

    def test_the_shipped_config_holds_no_resident(self):
        """2026-11-20: a permanent Ollama resident shrank oMLX's ceiling; none ship."""
        from portal.platform.inference.cluster_backends import DEFAULT_CONFIG_PATH

        assert BackendRegistry(config_path=str(DEFAULT_CONFIG_PATH)).preferred_residents == []
