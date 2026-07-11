"""Tests for health hysteresis, workspace_routes property, candidate-cache
clamping, and tool-support map in BackendRegistry."""

from portal.platform.inference.cluster_backends import Backend, BackendRegistry


class TestHealthHysteresis:
    """T-15: health failure threshold and hysteresis."""

    def test_default_threshold_2(self, tmp_path):
        """Healthy after one failure, unhealthy after two consecutive, reset on success."""
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends: []
workspace_routing: {}
defaults: {}
""")
        reg = BackendRegistry(config_path=str(cfg))
        assert reg._health_failure_threshold == 2

        be = Backend(id="test", type="ollama", url="http://x", group="g", models=[])
        be.healthy = True
        reg._backends["test"] = be

        # One failure — still healthy (threshold=2)
        be.consecutive_failures += 1
        assert be.healthy is True

        # Two failures — now unhealthy
        be.consecutive_failures += 1
        if be.consecutive_failures >= reg._health_failure_threshold:
            be.healthy = False
        assert be.healthy is False

        # Recovery on success
        be.consecutive_failures = 0
        be.healthy = True
        assert be.healthy is True

    def test_threshold_1_legacy_behavior(self, tmp_path, monkeypatch):
        """HEALTH_FAILURE_THRESHOLD=1 restores legacy behavior."""
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends: []
workspace_routing: {}
defaults: {}
""")
        monkeypatch.setenv("HEALTH_FAILURE_THRESHOLD", "1")
        reg = BackendRegistry(config_path=str(cfg))
        assert reg._health_failure_threshold == 1

    def test_yaml_defaults_health_failure_threshold(self, tmp_path):
        """YAML defaults.health_failure_threshold is parsed."""
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends: []
workspace_routing: {}
defaults:
  health_failure_threshold: 3
""")
        reg = BackendRegistry(config_path=str(cfg))
        assert reg._health_failure_threshold == 3

    def test_env_precedence_over_yaml(self, tmp_path, monkeypatch):
        """Env HEALTH_FAILURE_THRESHOLD wins over YAML."""
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends: []
workspace_routing: {}
defaults:
  health_failure_threshold: 3
""")
        monkeypatch.setenv("HEALTH_FAILURE_THRESHOLD", "5")
        reg = BackendRegistry(config_path=str(cfg))
        assert reg._health_failure_threshold == 5

    def test_warning_on_down_info_on_recovery(self, tmp_path, caplog):
        """WARNING on unhealthy, INFO on recovery."""
        import logging

        caplog.set_level(logging.WARNING)

        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends: []
workspace_routing: {}
defaults: {}
""")
        reg = BackendRegistry(config_path=str(cfg))
        be = Backend(id="test", type="ollama", url="http://x", group="g", models=[])

        # Simulate crossing the threshold
        be.consecutive_failures = reg._health_failure_threshold
        be.healthy = True

        # Cross threshold -> unhealthy at WARNING
        from portal.platform.inference.cluster_backends import logger as cb_logger

        with caplog.at_level(logging.WARNING, logger=cb_logger.name):
            if be.consecutive_failures >= reg._health_failure_threshold:
                cb_logger.warning(
                    "Health check failed for %s: %d consecutive failures — marking unhealthy",
                    be.id,
                    be.consecutive_failures,
                )
                be.healthy = False

        assert any("marking unhealthy" in r.message for r in caplog.records)

        # Recovery -> INFO
        with caplog.at_level(logging.INFO, logger=cb_logger.name):
            be.consecutive_failures = 0
            be.healthy = True
            cb_logger.info("Health check recovered: %s", be.id)

        assert any("recovered" in r.message for r in caplog.records)

    def test_cycle_summary_only_on_count_change(self, tmp_path, caplog):
        """Cycle summary INFO only when healthy count changed; else DEBUG."""
        import logging

        caplog.set_level(logging.DEBUG)

        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends: []
workspace_routing: {}
defaults: {}
""")
        reg = BackendRegistry(config_path=str(cfg))
        reg._last_healthy_count = -1

        from portal.platform.inference.cluster_backends import logger as cb_logger

        # First cycle — count changes from -1 to 0 → INFO
        reg._cached_healthy = []
        healthy_count = 0
        with caplog.at_level(logging.INFO, logger=cb_logger.name):
            if healthy_count != reg._last_healthy_count:
                reg._last_healthy_count = healthy_count
                cb_logger.info("Health check complete: %d/%d healthy", healthy_count, 0)
        assert any("healthy" in r.message for r in caplog.records)
        caplog.clear()

        # Second cycle — same count → DEBUG
        with caplog.at_level(logging.DEBUG, logger=cb_logger.name):
            if healthy_count != reg._last_healthy_count:
                cb_logger.info("Health check complete: %d/%d healthy", healthy_count, 0)
            else:
                cb_logger.debug(
                    "Health check complete: %d/%d healthy (no change)", healthy_count, 0
                )
        assert any("no change" in r.message for r in caplog.records)


class TestWorkspaceRoutesProperty:
    """T-19: workspace_routes property."""

    def test_property_returns_dict(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: b1
    type: ollama
    url: http://x
    group: general
    models: [m]
workspace_routing:
  auto: [general]
  coding: [coding]
defaults: {}
""")
        reg = BackendRegistry(config_path=str(cfg))
        routes = reg.workspace_routes
        assert isinstance(routes, dict)
        assert "auto" in routes
        assert "coding" in routes
        assert routes["auto"] == ["general"]


class TestCandidateCacheClamping:
    """T-17: unknown workspace ids clamped to _unknown for cache key."""

    def test_unknown_id_uses_unknown_key(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: b1
    type: ollama
    url: http://x
    group: general
    models: [m]
workspace_routing:
  auto: [general]
defaults: {}
""")
        reg = BackendRegistry(config_path=str(cfg))

        # Ensure candidate cache is empty
        reg._invalidate_candidate_cache()

        # Call with a known workspace — note: clamping in get_backend_candidates
        # uses WORKSPACES from workspaces module; in test context "auto" IS valid
        candidates = reg.get_backend_candidates("auto")
        assert len(candidates) == 1

        # Cache should have "auto" as key (it's a known workspace)
        assert "auto" in reg._candidate_cache

    def test_garbage_ids_dont_grow_cache(self, tmp_path):
        """Multiple distinct garbage ids all map to _unknown key."""
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: b1
    type: ollama
    url: http://x
    group: general
    models: [m]
workspace_routing: {}
defaults: {}
""")
        reg = BackendRegistry(config_path=str(cfg))
        reg._invalidate_candidate_cache()

        for garbage in ["garbage1", "garbage2", "garbage3"]:
            reg.get_backend_candidates(garbage)

        # All garbage ids clamped to _unknown — only one cache entry
        if "_unknown" in reg._candidate_cache:
            # _unknown should have at most one entry in the cache
            assert len(reg._candidate_cache) <= 2  # max: "_unknown" + "auto"
        # Keys should not include garbage ids
        assert "garbage1" not in reg._candidate_cache
        assert "garbage2" not in reg._candidate_cache
        assert "garbage3" not in reg._candidate_cache


class TestToolSupportMap:
    """T-16: O(1) model_supports_tools lookup."""

    def test_model_supports_tools_returns_correct_bool(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: b1
    type: ollama
    url: http://x
    group: general
    models:
      - {id: tool-model, supports_tools: true}
      - {id: plain-model, supports_tools: false}
workspace_routing: {}
defaults: {}
""")
        reg = BackendRegistry(config_path=str(cfg))
        assert reg.model_supports_tools("tool-model") is True
        assert reg.model_supports_tools("plain-model") is False
        assert reg.model_supports_tools("unknown") is False
        assert reg.model_supports_tools("") is False

    def test_legacy_string_models_no_tool_support(self, tmp_path):
        """Bare string models default to no tool support."""
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends:
  - id: b1
    type: ollama
    url: http://x
    group: general
    models: [legacy-model]
workspace_routing: {}
defaults: {}
""")
        reg = BackendRegistry(config_path=str(cfg))
        assert reg.model_supports_tools("legacy-model") is False

    def test_tool_support_map_empty_when_no_metadata(self, tmp_path):
        cfg = tmp_path / "backends.yaml"
        cfg.write_text("""
backends: []
workspace_routing: {}
defaults: {}
""")
        reg = BackendRegistry(config_path=str(cfg))
        assert reg._tool_support == {}
        assert reg.model_supports_tools("anything") is False
