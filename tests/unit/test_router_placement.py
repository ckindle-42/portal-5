"""Unit tests for the hot-seat placement policy (P5-OMLX-PREFIX-CACHE-001).

No network and no live engines: ``Backend`` objects and a ``BackendRegistry``
built from a tmp ``backends.yaml`` stand in for the fleet.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from portal.platform.inference import load_guard
from portal.platform.inference.cluster_backends import Backend, BackendRegistry
from portal.platform.inference.router import handlers, placement
from portal.platform.inference.router.placement import (
    HotSeatTracker,
    engine_key,
    prefer_ollama_for_compliance_council,
    prefer_resident_ollama_when_omlx_busy,
    protect_hot_seat,
)

OMLX_URL = "http://host.docker.internal:8085"

OLLAMA_URL = "http://host.docker.internal:11434"

HOT_NATIVE = "Qwen3.8-27B-oQ4e-mtp"

HOT_HINT = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx96k"

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
        assert engine_key("http://host:8085") != engine_key("http://host:8087")


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

    def test_clear_and_sync_loaded(self) -> None:
        key = engine_key(OMLX_URL)
        tracker = _hot_tracker(now=100.0)
        tracker.clear(key, "other-model")
        assert tracker.hot_model(key, 900, now=200.0) == HOT_NATIVE
        tracker.sync_loaded(key, {HOT_NATIVE})
        assert tracker.hot_model(key, 900, now=200.0) == HOT_NATIVE
        assert tracker.loaded_models(key) == {HOT_NATIVE}
        tracker.sync_loaded(key, set())
        assert tracker.hot_model(key, 900, now=200.0) is None
        assert tracker.loaded_models(key) == set()
        tracker.touch(key, HOT_NATIVE, now=300.0)
        tracker.clear(key, HOT_NATIVE)
        assert tracker.hot_model(key, 900, now=350.0) is None


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

    def test_alias_hint_stays_on_omlx_when_another_model_was_recently_hot(self) -> None:
        candidates = _coder_fleet()
        out = protect_hot_seat(
            candidates, "auto-coding", CODER_HINT, 900, tracker=_hot_tracker(), now=1_001.0
        )
        assert _ids(out) == _ids(candidates)

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

    @pytest.mark.parametrize(
        ("hint", "gguf"),
        [
            ("Inkling-2-Mini-oQ4e-mtp", "inkling-2-mini:ctx256k"),
            (
                "Inkling-2-Mini-abliterated-oQ4e-mtp",
                "portal5/orcarouter-inkling-2-mini-abliterated:mix16g-ctx32k",
            ),
        ],
    )
    def test_direct_omlx_security_hint_stays_primary_when_another_model_is_hot(
        self, hint: str, gguf: str
    ) -> None:
        omlx = Backend(
            id="omlx-security",
            type="omlx",
            url=OMLX_URL,
            group="security",
            models=[hint],
            priority=10,
        )
        ollama = Backend(
            id="ollama-security",
            type="ollama",
            url=OLLAMA_URL,
            group="security",
            models=[gguf],
            aliases={hint: gguf},
        )
        tracker = HotSeatTracker()
        tracker.touch(engine_key(OMLX_URL), "other-security-model", now=1_000.0)

        out = protect_hot_seat(
            [omlx, ollama], "auto-security", hint, 900, tracker=tracker, now=1_001.0
        )

        assert ollama.resolve_model(hint) == gguf
        assert _ids(out) == ["omlx-security", "ollama-security"]

    def test_effective_head_is_the_first_candidate_that_serves_the_hint(self) -> None:
        """2026-11-20 auto-coding: the group head could not serve the hint at all.

        ``get_backend_candidates`` leads with omlx-coding, which has no alias for
        the ctx96k hint; both dispatchers skip it. Judging the literal head's
        default model as "would swap the hot seat" demoted auto-coding to its
        Ollama GGUF copy and the load guard evicted the healthy oMLX copy.
        """
        candidates = [
            _omlx("omlx-coding", [CODER_NATIVE]),
            _ollama("ollama-coding", [CODER_HINT]),
            _omlx("omlx-general", [HOT_NATIVE], {HOT_HINT: HOT_NATIVE}),
            _ollama("ollama-general", [HOT_HINT]),
        ]
        assert _ids(
            protect_hot_seat(
                candidates, "auto-coding", HOT_HINT, 900, tracker=_hot_tracker(), now=1_001.0
            )
        ) == ["omlx-coding", "ollama-coding", "omlx-general", "ollama-general"]

    def test_a_resident_seat_copy_is_never_replaced_by_its_other_engine_copy(self) -> None:
        """A different oMLX model may be hot; the seat's own copy is still loaded."""
        key = engine_key(OMLX_URL)
        tracker = _hot_tracker(now=1_000.0)  # HOT_NATIVE served most recently
        tracker.touch(key, CODER_NATIVE, now=1_001.0)
        tracker.sync_loaded(key, {HOT_NATIVE, "some-other-model"})
        tracker.touch(key, "some-other-model", now=1_002.0)
        candidates = [
            _omlx("omlx-general", [HOT_NATIVE], {HOT_HINT: HOT_NATIVE}),
            _ollama("ollama-general", [HOT_HINT]),
        ]
        assert _ids(
            protect_hot_seat(candidates, "auto-coding", HOT_HINT, 900, tracker=tracker, now=1_003.0)
        ) == ["omlx-general", "ollama-general"]

    def test_a_different_effective_head_on_the_hot_engine_is_still_demoted(self) -> None:
        candidates = [
            _omlx("omlx-coding", [CODER_NATIVE], {CODER_HINT: CODER_NATIVE}),
            _omlx("omlx-general", [HOT_NATIVE], {HOT_HINT: HOT_NATIVE}),
            _ollama("ollama-general", [CODER_HINT]),
        ]
        out = protect_hot_seat(
            candidates, "auto-coding", CODER_HINT, 900, tracker=_hot_tracker(), now=1_001.0
        )
        assert _ids(out) == ["omlx-coding", "omlx-general", "ollama-general"]

    def test_after_the_window_order_is_normal(self) -> None:
        candidates = _coder_fleet()
        out = protect_hot_seat(
            candidates, "auto-coding", CODER_HINT, 900, tracker=_hot_tracker(now=100.0), now=1_001.0
        )
        assert _ids(out) == _ids(candidates)

    def test_internal_job_keeps_its_backend_head_while_chat_keeps_hot_seat_protection(
        self, monkeypatch
    ):
        from portal.platform.inference.config import is_job_workspace

        assert is_job_workspace("hunt-reasoning")
        assert is_job_workspace("auto-security::blueteam-council")
        assert not is_job_workspace("security-reviewer")
        monkeypatch.setitem(handlers.WORKSPACES, "hunt-reasoning", {})
        monkeypatch.setitem(handlers.WORKSPACES, "public-chat", {})
        candidates = [
            Backend(
                id="omlx-security",
                type="omlx",
                url=OMLX_URL,
                group="security",
                models=["different-model"],
            ),
            Backend(
                id="ollama-security",
                type="ollama",
                url=OLLAMA_URL,
                group="security",
                models=["chat-model"],
            ),
        ]
        tracker = HotSeatTracker()
        tracker.touch(engine_key(OMLX_URL), HOT_NATIVE, now=time.monotonic())
        monkeypatch.setattr(placement, "TRACKER", tracker)
        registry = SimpleNamespace(hot_seat_protect_s=900)

        assert _ids(handlers._order_candidates(candidates, "public-chat", registry)) == [
            "ollama-security",
            "omlx-security",
        ]
        assert _ids(handlers._order_candidates(candidates, "hunt-reasoning", registry)) == [
            "omlx-security",
            "ollama-security",
        ]

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


class TestBusyAwarePlacement:
    def test_busy_omlx_uses_an_idle_resident_ollama_copy(self) -> None:
        candidates = _coder_fleet()
        out = prefer_resident_ollama_when_omlx_busy(
            candidates,
            "auto-coding",
            CODER_HINT,
            omlx_busy=True,
            ollama_resident_idle=True,
        )
        assert _ids(out) == ["ollama-coding", "omlx-coding", "omlx-general"]

    @pytest.mark.parametrize(
        ("omlx_busy", "ollama_resident_idle"),
        [(False, True), (True, False), (False, False)],
    )
    def test_busy_rule_keeps_omlx_without_both_conditions(
        self, omlx_busy: bool, ollama_resident_idle: bool
    ) -> None:
        candidates = _coder_fleet()
        out = prefer_resident_ollama_when_omlx_busy(
            candidates,
            "auto-coding",
            CODER_HINT,
            omlx_busy=omlx_busy,
            ollama_resident_idle=ollama_resident_idle,
        )
        assert _ids(out) == _ids(candidates)

    def test_deliberate_ollama_first_order_is_preserved(self) -> None:
        candidates = [
            _omlx("omlx-general", [CODER_NATIVE], {CODER_HINT: CODER_NATIVE}),
            _ollama("ollama-general", [CODER_HINT]),
        ]
        already_ollama_first = [candidates[1], candidates[0]]
        out = prefer_resident_ollama_when_omlx_busy(
            already_ollama_first,
            "compliance-council-qwen38",
            CODER_HINT,
            omlx_busy=True,
            ollama_resident_idle=True,
        )
        assert _ids(out) == _ids(already_ollama_first)

    def test_compliance_council_is_explicitly_ollama_first(self) -> None:
        candidates = [
            _omlx("omlx-general", [CODER_NATIVE], {CODER_HINT: CODER_NATIVE}),
            _ollama("ollama-general", [CODER_HINT]),
        ]
        out = prefer_ollama_for_compliance_council(
            candidates, "compliance-council-qwen38", CODER_HINT
        )
        assert _ids(out) == ["ollama-general", "omlx-general"]

    async def test_runtime_rule_checks_status_and_residency_without_loading(
        self, monkeypatch
    ) -> None:
        requests: list[str] = []

        def responder(request: httpx.Request) -> httpx.Response:
            requests.append(request.url.path)
            if request.url.path == "/api/status":
                return httpx.Response(200, json={"active_requests": 1, "waiting_requests": 0})
            if request.url.path == "/api/ps":
                return httpx.Response(200, json={"models": [{"name": CODER_HINT}]})
            return httpx.Response(404)

        transport = httpx.MockTransport(responder)
        real_client = httpx.AsyncClient

        def client_factory(**kwargs):
            return real_client(transport=transport, **kwargs)

        monkeypatch.setattr(handlers.httpx, "AsyncClient", client_factory)
        guard = load_guard.LoadGuard(
            omlx_url=lambda: OMLX_URL,
            pinned=lambda: "router",
            client=lambda: real_client(transport=transport),
            ollama_url=lambda: OLLAMA_URL,
        )
        guard._omlx_in_flight = lambda: 0
        guard.active = lambda _engine, _model: False
        monkeypatch.setattr(load_guard, "GUARD", guard)

        candidates = _coder_fleet()
        out = await handlers._prefer_warm_ollama_if_omlx_busy(candidates, "auto-coding", CODER_HINT)

        assert _ids(out) == ["ollama-coding", "omlx-coding", "omlx-general"]
        assert requests == ["/api/status", "/api/ps"]


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
    def test_production_config_enables_a_bounded_window(self) -> None:
        # Operator enabled hot-seat placement on 2026-10-22; the window must stay finite.
        repo = Path(__file__).resolve().parents[2]
        reg = BackendRegistry(config_path=str(repo / "config" / "backends.yaml"))
        assert 0.0 < reg.hot_seat_protect_s <= 3600.0

    def test_nested_compliance_ask_default_reuses_resident_omlx_seat(self) -> None:
        from portal.platform.inference.router.preinject import (
            _resolve_workspace_variant,
            _unpack_synthetic_workspace,
        )
        from portal.platform.inference.router.workspaces import WORKSPACES

        repo = Path(__file__).resolve().parents[2]
        reg = BackendRegistry(config_path=str(repo / "config" / "backends.yaml"))
        target = WORKSPACES["auto-compliance"]["tool_model_defaults"]["compliance_ask"]
        base, variant = _unpack_synthetic_workspace(target)
        resolved_target = _resolve_workspace_variant(target, base, variant)
        caller_hint = WORKSPACES["auto-compliance"]["model_hint"]
        target_hint = WORKSPACES[resolved_target]["model_hint"]
        caller_head = handlers._order_candidates(
            reg.get_backend_candidates("auto-compliance"), "auto-compliance", reg
        )[0]
        target_head = handlers._order_candidates(
            reg.get_backend_candidates(resolved_target), resolved_target, reg
        )[0]
        assert caller_head.type == "omlx"
        assert target_head.type == "omlx"
        assert target_head.resolve_model(target_hint) == caller_head.resolve_model(caller_hint)
