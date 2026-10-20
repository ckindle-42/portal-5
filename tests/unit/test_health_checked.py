"""/health distinguishes assumed backend counts from measured ones."""

from __future__ import annotations

from pathlib import Path

from portal.platform.inference.cluster_backends import Backend, BackendRegistry


def _registry(tmp_path: Path) -> BackendRegistry:
    cfg = tmp_path / "backends.yaml"
    cfg.write_text("backends: []\nworkspace_routing: {}\ndefaults: {}\n")
    reg = BackendRegistry(config_path=str(cfg))
    reg._backends["down"] = Backend(
        id="down", type="omlx", url="http://127.0.0.1:9", group="g", models=[]
    )
    return reg


def test_counts_are_assumed_until_a_cycle_completes(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    assert reg.health_checked is False
    assert len(reg.list_healthy_backends()) == 1


def test_counts_are_measured_after_a_cycle(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg._backends["down"].healthy = False
    reg._refresh_healthy_cache()
    assert reg.health_checked is True
    assert reg.list_healthy_backends() == []
