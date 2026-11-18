"""Cross-reference workspaces ↔ models in portal.yaml.

Catches drift at PR time instead of at lifespan startup.
"""

from __future__ import annotations

from portal.platform.inference.cli._common import cross_reference_workspaces_and_models
from portal.platform.inference.config import load_portal_config


def test_no_orphan_workspace_hints() -> None:
    """Every workspace model_hint that could be served by the registry
    must round-trip cleanly. ``hf.co/...`` references are Ollama-native
    and outside the cross-reference scope.
    """
    cfg = load_portal_config()
    report = cross_reference_workspaces_and_models(cfg)
    assert not report.orphan_hints, (
        "Workspaces reference pullable model_hint values not in "
        "the registry: "
        + ", ".join(report.orphan_hints)
        + ". Add corresponding entries to portal.yaml:models or correct "
        "the workspace model_hint."
    )


def test_cross_ref_helper_is_pure() -> None:
    """The cross-reference helper must not have side effects."""
    cfg = load_portal_config()
    r1 = cross_reference_workspaces_and_models(cfg)
    r2 = cross_reference_workspaces_and_models(cfg)
    assert r1 == r2, "Helper output non-deterministic — has side effects"
