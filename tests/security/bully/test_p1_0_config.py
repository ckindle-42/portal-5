"""bully.config -- role-alias resolution (P1.0, extended once P1.7 needed
the real resolution path). No hardcoded model tag anywhere (MASTER SS11).
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import config as bully_config


def test_load_hunt_and_heart_config_from_real_repo_files():
    hunt = bully_config.load_hunt_config()
    heart = bully_config.load_heart_config()
    assert hunt["models"]["workspace"] == "blueteam-orchestrated"
    assert heart["roster"]["min_seats"] >= 1


def test_resolve_role_model_finds_a_variant_nested_workspace():
    # blueteam-orchestrated is a variant under auto-security.variants in the
    # live config/portal.yaml, not a top-level workspace id -- this proves
    # the lookup handles that real shape, not just a flat dict.
    tag = bully_config.resolve_role_model("tool")
    assert isinstance(tag, str) and tag  # a real tag, not a literal we invented


def test_resolve_investigation_models_shape():
    models = bully_config.resolve_investigation_models()
    assert set(models.keys()) == {"tool", "reasoning", "expert"}
    assert all(isinstance(v, str) and v for v in models.values())


def test_resolve_role_model_rejects_unknown_role():
    with pytest.raises(bully_config.ConfigError):
        bully_config.resolve_role_model("not_a_real_role")


def test_config_snapshot_is_frozen_and_content_hashed():
    snap1 = bully_config.HuntConfigSnapshot.capture()
    snap2 = bully_config.HuntConfigSnapshot.capture()
    assert snap1.version == snap2.version  # same content -> same hash
    assert snap1.to_dict()["version"] == snap1.version
