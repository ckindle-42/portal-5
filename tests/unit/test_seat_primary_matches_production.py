"""N-8: the WFE harness's seat_primary names the model production serves.

Offline: production's choice is the first backend in candidate order that resolves the hint
(BackendRegistry.resolve_model). Candidate shuffles are pinned so the comparison is deterministic.
"""

from __future__ import annotations

import importlib
import random
from pathlib import Path

import pytest
import yaml

from portal.platform.inference.cluster_backends import BackendRegistry

campaign = importlib.import_module("tests.wfe.campaign")
REAL_CONFIG = Path(__file__).resolve().parents[2] / "config" / "backends.yaml"


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> BackendRegistry:
    monkeypatch.setattr(random, "shuffle", lambda _xs: None)
    return BackendRegistry(config_path=str(REAL_CONFIG))


def _hints(cfg: dict) -> set[str]:
    hints: set[str] = set()
    for b in cfg.get("backends") or []:
        for m in b.get("models") or []:
            hints.add(m.get("id") if isinstance(m, dict) else m)
        hints.update((b.get("aliases") or {}).keys())
    hints.discard(None)
    return hints


def _production_choice(reg: BackendRegistry, workspace: str, hint: str) -> str | None:
    for backend in reg.get_backend_candidates(workspace):
        resolved = backend.resolve_model(hint)
        if resolved is not None:
            return resolved
    return None


def test_seat_primary_matches_production_for_every_routed_hint(registry: BackendRegistry) -> None:
    cfg = yaml.safe_load(REAL_CONFIG.read_text()) or {}
    mismatches: list[str] = []
    for workspace in cfg.get("workspace_routing") or {}:
        for hint in sorted(_hints(cfg)):
            prod = _production_choice(registry, workspace, hint)
            if prod is None:
                continue
            seat = campaign.seat_primary(workspace, hint)
            if seat != prod:
                mismatches.append(f"{workspace} {hint}: seat_primary={seat} production={prod}")
    assert not mismatches, "\n".join(mismatches[:20])
