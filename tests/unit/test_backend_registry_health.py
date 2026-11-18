"""Tests for health hysteresis, workspace_routes property, candidate-cache
clamping, and tool-support map in BackendRegistry."""

from portal.platform.inference.cluster_backends import BackendRegistry


class TestPreferredResidents:
    """`defaults.preferred_residents`: workspace ids kept warm (2026-11-16 seat 3)."""

    def test_the_shipped_config_names_the_daily_driver(self):
        """The production roster warms auto-daily: `auto` routes ordinary chat there."""
        from portal.platform.inference.cluster_backends import DEFAULT_CONFIG_PATH

        assert (
            "auto-daily"
            in BackendRegistry(config_path=str(DEFAULT_CONFIG_PATH)).preferred_residents
        )
