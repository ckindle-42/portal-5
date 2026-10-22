"""Unit tests for the hot-seat placement policy (P5-OMLX-PREFIX-CACHE-001).

No network and no live engines: ``Backend`` objects and a ``BackendRegistry``
built from a tmp ``backends.yaml`` stand in for the fleet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.platform.inference.cluster_backends import Backend, BackendRegistry
from portal.platform.inference.router import placement
from portal.platform.inference.router.placement import (
    HotSeatTracker,
    engine_key,
    protect_hot_seat,
)

OMLX_URL = "http://host.docker.internal:8085"
OLLAMA_URL = "http://host.docker.internal:11434"

# The seat that is resident (and therefore hot) on the shared oMLX engine.
HOT_NATIVE = "Qwen3.8-27B-oQ4e-mtp"
HOT_HINT = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k"
# A different model a later request may ask for: the GGUF tag the Ollama copy
# carries literally, aliased to the oMLX native id on the oMLX backends.
CODER_HINT = "hf.co/unsloth/Qwen3-Coder-30B-A3B-GGUF:Q4_K_M-ctx32k"
CODER_NATIVE = "Qwen3-Coder-30B-A3B-Instruct-4bit"


def _omlx(backend_id: str, models: list[str], aliases: dict[str, str] | None = None) -> Backend:
    return Backend(
        id=backend_id,
        type="omlx",
        url=OMLX_URL,
        group="coding",
        models=models,
        aliases=aliases or {},
        priority=10,
    )


def _ollama(backend_id: str, models: list[str]) -> Backend:
    return Backend(id=backend_id, type="ollama", url=OLLAMA_URL, group="coding", models=models)


def _coder_fleet() -> list[Backend]:
    """The candidate order ``get_backend_candidates`` yields for a coding seat."""
    return [
        _omlx("omlx-coding", [CODER_NATIVE], {CODER_HINT: CODER_NATIVE}),
        _omlx("omlx-general", [HOT_NATIVE], {CODER_HINT: CODER_NATIVE}),
        _ollama("ollama-coding", [CODER_HINT]),
    ]


def _hot_tracker(now: float = 1_000.0) -> HotSeatTracker:
    tracker = HotSeatTracker()
    tracker.touch(engine_key(OMLX_URL), HOT_NATIVE, now=now)
    return tracker


def _ids(candidates: list[Backend]) -> list[str]:
    return [b.id for b in candidates]


class TestEngineKey:
    @pytest.mark.parametrize(
        "url",
        [
            OMLX_URL,
            OMLX_URL + "/",
            OMLX_URL + "/v1/chat/completions",
            "HTTP://Host.Docker.Internal:8085/v1",
        ],
    )
    def test_normalizes_to_scheme_and_netloc(self, url: str) -> None:
        assert engine_key(url) == "http://host.docker.internal:8085"

    def test_different_ports_are_different_engines(self) -> None:
        assert engine_key("http://host:8085") != engine_key("http://host:8086")


class TestHotSeatTracker:
    def test_hot_within_window(self) -> None:
        tracker = _hot_tracker(now=100.0)
        assert tracker.hot_model(engine_key(OMLX_URL), 900, now=1_000.0) == HOT_NATIVE

    def test_cold_after_window(self) -> None:
        tracker = _hot_tracker(now=100.0)
        assert tracker.hot_model(engine_key(OMLX_URL), 900, now=1_001.0) is None

    def test_window_of_zero_disables_tracking(self) -> None:
        tracker = _hot_tracker(now=100.0)
        assert tracker.hot_model(engine_key(OMLX_URL), 0, now=100.0) is None

    def test_unknown_engine_is_cold(self) -> None:
        assert HotSeatTracker().hot_model(engine_key(OMLX_URL), 900) is None

    def test_latest_model_wins(self) -> None:
        tracker = _hot_tracker(now=100.0)
        tracker.touch(engine_key(OMLX_URL), CODER_NATIVE, now=200.0)
        assert tracker.hot_model(engine_key(OMLX_URL), 900, now=250.0) == CODER_NATIVE

    def test_note_omlx_activity_records_on_the_module_tracker(self, monkeypatch) -> None:
        fresh = HotSeatTracker()
        monkeypatch.setattr(placement, "TRACKER", fresh)
        placement.note_omlx_activity(OMLX_URL + "/v1/chat/completions", HOT_NATIVE)
        assert fresh.hot_model(engine_key(OMLX_URL), 900) == HOT_NATIVE


class TestProtectHotSeat:
    def test_knob_off_keeps_order(self) -> None:
        candidates = _coder_fleet()
        assert _ids(
            protect_hot_seat(
                candidates, "auto-coding", CODER_HINT, 0.0, tracker=_hot_tracker(), now=1_001.0
            )
        ) == _ids(candidates)

    def test_unreadable_knob_means_off(self) -> None:
        candidates = _coder_fleet()
        assert _ids(
            protect_hot_seat(
                candidates, "auto-coding", CODER_HINT, None, tracker=_hot_tracker(), now=1_001.0
            )
        ) == _ids(candidates)

    def test_single_candidate_unchanged(self) -> None:
        only = [_omlx("omlx-coding", [CODER_NATIVE], {CODER_HINT: CODER_NATIVE})]
        assert _ids(
            protect_hot_seat(
                only, "auto-coding", CODER_HINT, 900, tracker=_hot_tracker(), now=1_001.0
            )
        ) == ["omlx-coding"]

    def test_promotes_candidate_that_spares_the_hot_engine(self) -> None:
        candidates = _coder_fleet()
        out = protect_hot_seat(
            candidates, "auto-coding", CODER_HINT, 900, tracker=_hot_tracker(), now=1_001.0
        )
        # The Ollama copy serves the hint and does not touch the oMLX engine;
        # the demoted head stays second and the same-engine sibling third.
        assert _ids(out) == ["ollama-coding", "omlx-coding", "omlx-general"]

    def test_hot_seats_own_request_unchanged(self) -> None:
        candidates = [
            _omlx("omlx-general", [HOT_NATIVE], {HOT_HINT: HOT_NATIVE}),
            _ollama("ollama-general", [HOT_HINT]),
        ]
        assert _ids(
            protect_hot_seat(
                candidates, "auto-coding", HOT_HINT, 900, tracker=_hot_tracker(), now=1_001.0
            )
        ) == ["omlx-general", "ollama-general"]

    def test_after_the_window_order_is_normal(self) -> None:
        candidates = _coder_fleet()
        out = protect_hot_seat(
            candidates, "auto-coding", CODER_HINT, 900, tracker=_hot_tracker(now=100.0), now=1_001.0
        )
        assert _ids(out) == _ids(candidates)

    def test_pinned_model_hint_unchanged(self) -> None:
        # ``?model=`` / persona model_pin builds a ``::model=`` synthetic workspace.
        candidates = _coder_fleet()
        pinned = f"auto-coding::model={CODER_HINT}"
        assert _ids(
            protect_hot_seat(
                candidates, pinned, CODER_HINT, 900, tracker=_hot_tracker(), now=1_001.0
            )
        ) == _ids(candidates)

    def test_alternative_that_cannot_serve_the_hint_is_skipped(self) -> None:
        candidates = [
            _omlx("omlx-coding", [CODER_NATIVE], {CODER_HINT: CODER_NATIVE}),
            _ollama("ollama-general", ["some-other-model"]),
        ]
        assert _ids(
            protect_hot_seat(
                candidates, "auto-coding", CODER_HINT, 900, tracker=_hot_tracker(), now=1_001.0
            )
        ) == ["omlx-coding", "ollama-general"]

    def test_no_alternative_never_denies_service(self) -> None:
        candidates = [
            _omlx("omlx-coding", [CODER_NATIVE], {CODER_HINT: CODER_NATIVE}),
            _omlx("omlx-general", [HOT_NATIVE], {CODER_HINT: CODER_NATIVE}),
        ]
        assert _ids(
            protect_hot_seat(
                candidates, "auto-coding", CODER_HINT, 900, tracker=_hot_tracker(), now=1_001.0
            )
        ) == ["omlx-coding", "omlx-general"]

    def test_hintless_workspace_uses_the_heads_first_model(self) -> None:
        # Regression: no model_hint must not read a non-existent ``default_model``.
        candidates = [
            _omlx("omlx-coding", [CODER_NATIVE]),
            _ollama("ollama-coding", [CODER_NATIVE]),
        ]
        out = protect_hot_seat(
            candidates, "auto-coding", "", 900, tracker=_hot_tracker(), now=1_001.0
        )
        assert _ids(out) == ["ollama-coding", "omlx-coding"]

    def test_hintless_workspace_already_on_the_hot_model_unchanged(self) -> None:
        candidates = [
            _omlx("omlx-general", [HOT_NATIVE]),
            _ollama("ollama-general", [HOT_NATIVE]),
        ]
        assert _ids(
            protect_hot_seat(
                candidates, "auto-coding", "", 900, tracker=_hot_tracker(), now=1_001.0
            )
        ) == ["omlx-general", "ollama-general"]

    def test_input_order_is_not_mutated(self) -> None:
        candidates = _coder_fleet()
        snapshot = list(candidates)
        protect_hot_seat(
            candidates, "auto-coding", CODER_HINT, 900, tracker=_hot_tracker(), now=1_001.0
        )
        assert candidates == snapshot


def _write_config(tmp_path: Path, extra_defaults: str = "") -> Path:
    cfg = tmp_path / "backends.yaml"
    cfg.write_text(
        f"""
backends:
  - id: omlx-coding
    type: omlx
    url: {OMLX_URL}
    group: coding
    priority: 10
    models: [{CODER_NATIVE}]
    aliases:
      "{CODER_HINT}": {CODER_NATIVE}
  - id: ollama-coding
    type: ollama
    url: {OLLAMA_URL}
    group: coding
    models: [{CODER_HINT}]
workspace_routing:
  auto-coding: [coding]
defaults:
  fallback_group: general
{extra_defaults}
"""
    )
    return cfg


class TestKnobWiring:
    def test_registry_defaults_to_off(self, tmp_path: Path) -> None:
        reg = BackendRegistry(config_path=str(_write_config(tmp_path)))
        assert reg.hot_seat_protect_s == 0.0

    def test_registry_reads_configured_window(self, tmp_path: Path) -> None:
        reg = BackendRegistry(
            config_path=str(_write_config(tmp_path, "  hot_seat_protect_s: 900\n"))
        )
        assert reg.hot_seat_protect_s == 900.0

    def test_production_config_enables_a_bounded_window(self) -> None:
        # Operator enabled hot-seat placement on 2026-10-22; the window must stay finite.
        repo = Path(__file__).resolve().parents[2]
        reg = BackendRegistry(config_path=str(repo / "config" / "backends.yaml"))
        assert 0.0 < reg.hot_seat_protect_s <= 3600.0

    def test_registry_candidates_and_knob_drive_the_policy(self, tmp_path: Path) -> None:
        reg = BackendRegistry(
            config_path=str(_write_config(tmp_path, "  hot_seat_protect_s: 900\n"))
        )
        candidates = reg.get_backend_candidates("auto-coding")
        assert _ids(candidates) == ["omlx-coding", "ollama-coding"]

        reordered = protect_hot_seat(
            candidates,
            "auto-coding",
            CODER_HINT,
            reg.hot_seat_protect_s,
            tracker=_hot_tracker(),
            now=1_001.0,
        )
        assert _ids(reordered) == ["ollama-coding", "omlx-coding"]
