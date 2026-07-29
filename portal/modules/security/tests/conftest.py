"""Keep security-module tests from writing into production runtime paths."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_security_writes(tmp_path, monkeypatch):
    """Redirect journals and engagement checkpoints for every security test."""
    journal_dir = tmp_path / "field_journal"
    checkpoint_dir = tmp_path / "checkpoints"
    canary_dir = tmp_path / "canary_baselines"
    monkeypatch.setattr(
        "portal.modules.security.core.field_journal.JOURNAL_DIR",
        journal_dir,
    )
    monkeypatch.setattr(
        "portal.modules.security.core.loop.RESULTS_DIR",
        tmp_path / "results",
    )
    monkeypatch.setattr(
        "portal.modules.security.core.loop.CHECKPOINT_DIR",
        checkpoint_dir,
    )
    monkeypatch.setattr(
        "portal.modules.security.core.drift_gate.CANARY_DIR",
        canary_dir,
    )
    return {
        "journal": journal_dir,
        "checkpoints": checkpoint_dir,
        "canaries": canary_dir,
    }
