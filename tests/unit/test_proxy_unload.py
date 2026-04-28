"""Unit tests for mlx-proxy perform_unload helper (P5-UAT-001 resolution)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _load_proxy_module():
    """Load scripts/mlx-proxy.py as an importable module (it is a script, not a package)."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    proxy_path = repo_root / "scripts" / "mlx-proxy.py"
    spec = importlib.util.spec_from_file_location("mlx_proxy_under_test", proxy_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["mlx_proxy_under_test"] = module
    # The proxy module starts background threads at import time (memory_monitor,
    # watchdog). Acceptable here because the threads are daemon=True.
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def proxy():
    return _load_proxy_module()


def _set_state(mlx_state, loaded_model, state, active_server=None):
    """Set MLXState private fields directly (loaded_model is a read-only property)."""
    mlx_state._loaded_model = loaded_model
    mlx_state._state = state
    mlx_state._active_server = active_server


def test_perform_unload_calls_stop_all_and_resets_state(proxy):
    """perform_unload must call stop_all and reset mlx_state to 'none'."""
    _set_state(proxy.mlx_state, "mlx-community/test-model", "ready", "lm")

    with (
        patch.object(proxy, "stop_all") as mock_stop,
        patch.object(proxy, "_evict_ollama_models") as mock_evict,
        patch.object(proxy, "_get_free_memory_gb", return_value=20.0),
    ):
        result = proxy.perform_unload(evict_ollama=False)

    mock_stop.assert_called_once()
    mock_evict.assert_not_called()  # ollama=False -> no Ollama eviction
    assert proxy.mlx_state.state == "none"
    assert proxy.mlx_state.loaded_model is None
    assert proxy.mlx_state.active_server is None
    assert result["unloaded"] is True
    assert result["loaded_model_before"] == "mlx-community/test-model"
    assert result["state_before"] == "ready"
    assert result["state_after"] == "none"
    assert result["ollama_evicted"] is False


def test_perform_unload_evicts_ollama_when_requested(proxy):
    _set_state(proxy.mlx_state, None, "none")

    with (
        patch.object(proxy, "stop_all"),
        patch.object(proxy, "_evict_ollama_models") as mock_evict,
        patch.object(proxy, "_get_free_memory_gb", return_value=30.0),
    ):
        result = proxy.perform_unload(evict_ollama=True)

    mock_evict.assert_called_once()
    assert result["ollama_evicted"] is True


def test_perform_unload_returns_wired_measurements(proxy):
    """The wired_before/after/freed fields must reflect MemoryMonitor samples."""
    _set_state(proxy.mlx_state, None, "none")

    fake_monitor = MagicMock()
    fake_monitor.to_dict.side_effect = [
        {"current": {"wired_gb": 28.0}},  # before stop_all
        {"current": {"wired_gb": 6.0}},  # after stop_all
    ]
    with (
        patch.object(proxy, "memory_monitor", fake_monitor),
        patch.object(proxy, "stop_all"),
        patch.object(proxy, "_get_free_memory_gb", return_value=40.0),
    ):
        result = proxy.perform_unload(evict_ollama=False)

    assert result["wired_before_gb"] == 28.0
    assert result["wired_after_gb"] == 6.0
    assert result["wired_freed_gb"] == 22.0


def test_perform_unload_survives_ollama_eviction_failure(proxy):
    """If Ollama is down, /unload must still succeed for the MLX side."""
    _set_state(proxy.mlx_state, None, "none")

    with (
        patch.object(proxy, "stop_all"),
        patch.object(proxy, "_evict_ollama_models", side_effect=RuntimeError("ollama down")),
        patch.object(proxy, "_get_free_memory_gb", return_value=30.0),
    ):
        # Should not raise
        result = proxy.perform_unload(evict_ollama=True)

    assert result["unloaded"] is True
    assert result["ollama_evicted"] is True  # we tried, even though it failed
