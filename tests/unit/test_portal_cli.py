"""Smoke tests for the portal CLI skeleton (M5 Stage 2).

Verifies:
- portal --help exits 0 and mentions the 'config' command group.
- portal config show exits 0 and emits valid JSON with expected keys.
- portal config show output reflects the production portal.yaml values.
"""

from __future__ import annotations


def test_models_pull_reads_from_config_not_hardcoded() -> None:
    """Regression — registry must come from PortalConfig.models, not
    a module-level dict. If this fails, someone re-introduced the
    hardcoded `_HF_MODEL_SPECS` shape and undid the M1 follow-up.
    """
    from portal.platform.inference.cli import models as cli_models

    forbidden = ("_HF_MODEL_SPECS", "_HF_MODELS", "HF_MODEL_SPECS")
    for name in forbidden:
        assert not hasattr(cli_models, name), (
            f"portal.platform.inference.cli.models has reacquired a hardcoded "
            f"registry attribute {name!r}. The pull registry must come "
            f"from PortalConfig.models loaded from config/portal.yaml. "
            f"See TASK_LIFT_HF_REGISTRY_TO_PORTAL_YAML_V1.md."
        )


def test_models_pull_default_excludes_retired() -> None:
    """Default pull (no args, no --include-retired) excludes retired entries."""
    from portal.platform.inference.cli.models import _select_pull_targets
    from portal.platform.inference.config import load_portal_config

    cfg = load_portal_config()
    assert cfg.models, "portal.yaml has no models: block"
    assert any(m.retired for m in cfg.models), (
        "portal.yaml has no retired models — this regression test "
        "needs a retired fixture to be meaningful"
    )

    default_targets = _select_pull_targets(
        cfg.models,
        requested_ids=None,
        include_retired=False,
        skip_gated=False,
    )
    for m in default_targets:
        assert not m.retired, (
            f"Default pull targets include retired model {m.ollama_name!r}. "
            f"The --include-retired flag must gate retired entries."
        )

    include_retired_targets = _select_pull_targets(
        cfg.models,
        requested_ids=None,
        include_retired=True,
        skip_gated=False,
    )
    assert len(include_retired_targets) >= len(default_targets), (
        "--include-retired must broaden, not narrow, the target set"
    )
    assert any(m.retired for m in include_retired_targets), (
        "--include-retired pulled no retired models; flag is not wired"
    )


def test_models_pull_explicit_id_overrides_retired_filter() -> None:
    """A user who explicitly names a retired model in args should
    still get it — the retired filter is for the default-everything path.
    """
    import pytest as _pytest

    from portal.platform.inference.cli.models import _select_pull_targets
    from portal.platform.inference.config import load_portal_config

    cfg = load_portal_config()
    retired = next((m for m in cfg.models if m.retired), None)
    if retired is None:
        _pytest.skip("no retired fixtures in portal.yaml")

    targets = _select_pull_targets(
        cfg.models,
        requested_ids=[retired.ollama_name],
        include_retired=False,
        skip_gated=False,
    )
    assert any(m.ollama_name == retired.ollama_name for m in targets), (
        "Explicit ollama_name in args should override default-retired filter"
    )
