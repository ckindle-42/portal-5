"""Tests for the oMLX backend plumbing (P5-FUT-013 Phase 1).

Covers: type-derived health URLs + health_path override, model-hint alias
resolution, within-group priority ordering, per-engine option injection, and
the backend-introspection seam used by the timeout paths. The retired
in-house MLX proxy surfaces (mlx_metadata, _MLX_PROXY_HEALTH_URL) stay absent
— see TestModelSupportsToolsRealBackend in test_pipeline.py.
"""

from __future__ import annotations

import pytest

from portal.platform.inference.cluster_backends import Backend, BackendRegistry


class TestOmlxBackendBasics:
    def test_health_url_omlx_uses_v1_models(self):
        be = Backend(id="o", type="omlx", url="http://localhost:8085", group="omlx", models=[])
        assert be.health_url == "http://localhost:8085/v1/models"

    def test_health_path_override_wins(self):
        be = Backend(
            id="o",
            type="omlx",
            url="http://localhost:8085",
            group="omlx",
            models=[],
            health_path="/healthz",
        )
        assert be.health_url == "http://localhost:8085/healthz"

    def test_health_url_ollama_unchanged(self):
        be = Backend(id="b", type="ollama", url="http://x", group="general", models=[])
        assert be.health_url == "http://x/api/tags"

    def test_resolve_model_direct_alias_and_miss(self):
        be = Backend(
            id="o",
            type="omlx",
            url="http://x",
            group="omlx",
            models=["Native-Model-4bit"],
            aliases={"gguf-tag-ctx16k": "Native-Model-4bit"},
        )
        assert be.resolve_model("Native-Model-4bit") == "Native-Model-4bit"
        assert be.resolve_model("gguf-tag-ctx16k") == "Native-Model-4bit"
        assert be.resolve_model("unknown-model") is None
        assert be.resolve_model("") is None

    def test_resolve_model_skips_unserved_live_model(self):
        """A half-migrated oMLX group aliases a model the live server does not
        actually serve — resolve_model must return None so candidate selection
        falls through instead of black-holing the request."""
        be = Backend(
            id="omlx-reasoning",
            type="omlx",
            url="http://x",
            group="reasoning",
            models=["granite-4.1-30b-4bit", "DeepSeek-R1-4bit"],
            aliases={"granite4.1:30b-ctx64k": "granite-4.1-30b-4bit"},
        )
        # Before any probe: live_models unknown, behave as before.
        assert be.resolve_model("granite4.1:30b-ctx64k") == "granite-4.1-30b-4bit"
        # After a probe that only reported a different model:
        be.live_models = {"Qwen3.8-27B-oQ4e-mtp"}
        assert be.resolve_model("granite4.1:30b-ctx64k") is None
        assert be.resolve_model("granite-4.1-30b-4bit") is None
        # A model that IS live still resolves.
        be.live_models = {"granite-4.1-30b-4bit"}
        assert be.resolve_model("granite4.1:30b-ctx64k") == "granite-4.1-30b-4bit"


class TestInjectOmlxOptions:
    def test_injects_full_sampling_surface(self, monkeypatch):
        from portal.platform.inference.router import validation as vm

        monkeypatch.setitem(
            vm.WORKSPACES,
            "ws-omlx",
            {
                "predict_limit": 512,
                "temperature": 0.2,
                "top_p": 0.9,
                "top_k": 20,
                "min_p": 0.05,
                "repeat_penalty": 1.05,
                "presence_penalty": 0.5,
                "seed": 7,
                "think": True,
            },
        )
        out = vm._inject_omlx_options({"messages": [], "stream": True}, "ws-omlx")
        assert out["max_tokens"] == 512
        assert out["stream_options"]["include_usage"] is True
        assert out["temperature"] == 0.2
        assert out["top_p"] == 0.9
        # oMLX's own ChatCompletionRequest schema wires these directly (verified
        # live against the installed omlx package, 2026-08-15) — not "extra"
        # OpenAI fields to omit, real sampler-affecting params to forward.
        assert out["top_k"] == 20
        assert out["min_p"] == 0.05
        assert out["presence_penalty"] == 0.5
        assert out["seed"] == 7
        # repeat_penalty is the Ollama idiom; oMLX's field is repetition_penalty.
        assert out["repetition_penalty"] == 1.05
        assert "repeat_penalty" not in out
        # oMLX has no bare `think` field — mapped to chat_template_kwargs.
        assert out["chat_template_kwargs"] == {"enable_thinking": True}
        assert "think" not in out
        # No Ollama-idiom anywhere: no options sub-dict, no keep_alive, no num_ctx
        assert "options" not in out
        assert "keep_alive" not in out


class TestOmlxTemplateParityEffort:
    """P5-OMLX-QWEN38-MTP-001: checkpoints whose chat template defaults
    reasoning_effort=xhigh must render the prompt their evaluated Ollama arm
    renders (Ollama sends no effort preamble when a request omits one). The
    parity tier is declared per model in config/backends.yaml — request and
    seat efforts always win over it.
    """

    def test_parity_default_and_precedence(self, monkeypatch):
        from portal.platform.inference.router import validation as vm

        reg = BackendRegistry(config_path="config/backends.yaml")
        monkeypatch.setattr(vm, "registry", reg)
        # The audited checkpoint (live A/B 2026-11-27: xhigh 169 tok 0/3 stop
        # vs medium-parity 131 tok 3/3 stop) declares the parity tier.
        assert reg.model_reasoning_effort_default("Qwen3.8-27B-oQ4e-mtp") == "medium"
        assert reg.model_reasoning_effort_default("qwen3-coder:30b-a3b-q4_K_M") is None

        # 1. Nothing declared — parity tier injected.
        out = vm._inject_omlx_options(
            {"model": "Qwen3.8-27B-oQ4e-mtp", "messages": [], "stream": True}
        )
        assert out["chat_template_kwargs"]["reasoning_effort"] == "medium"

        # 2. Caller top-level effort wins.
        out = vm._inject_omlx_options(
            {
                "model": "Qwen3.8-27B-oQ4e-mtp",
                "messages": [],
                "stream": True,
                "reasoning_effort": "low",
            }
        )
        assert out["chat_template_kwargs"]["reasoning_effort"] == "low"

        # 3. Caller chat_template_kwargs wins.
        out = vm._inject_omlx_options(
            {
                "model": "Qwen3.8-27B-oQ4e-mtp",
                "messages": [],
                "stream": True,
                "chat_template_kwargs": {"reasoning_effort": "xhigh"},
            }
        )
        assert out["chat_template_kwargs"]["reasoning_effort"] == "xhigh"

        # 4. Seat-declared effort wins; an explicit caller "none" suppresses it.
        monkeypatch.setitem(vm.WORKSPACES, "ws-parity", {"reasoning_effort": "low"})
        out = vm._inject_omlx_options(
            {"model": "Qwen3.8-27B-oQ4e-mtp", "messages": [], "stream": True},
            "ws-parity",
        )
        assert out["chat_template_kwargs"]["reasoning_effort"] == "low"
        out = vm._inject_omlx_options(
            {
                "model": "Qwen3.8-27B-oQ4e-mtp",
                "messages": [],
                "stream": True,
                "reasoning_effort": "none",
            }
        )
        assert "reasoning_effort" not in (out.get("chat_template_kwargs") or {})
        assert out["think"] is False

        # 5. Models without the template default get nothing.
        out = vm._inject_omlx_options(
            {"model": "Qwen3-Coder-30B-A3B-Instruct-4bit", "messages": [], "stream": True}
        )
        assert "reasoning_effort" not in (out.get("chat_template_kwargs") or {})


class TestAutoCodingOmlxShadowRouting:
    """PUNCHLIST B2: auto-coding's `coding` group carries both omlx-coding
    (priority 10) and ollama-coding (priority 0) against the real
    config/backends.yaml. Guards against alias/priority drift breaking the
    shadow-then-shift routing without a config-load error to flag it.
    """

    @pytest.fixture
    def coding_candidates(self):
        reg = BackendRegistry(config_path="config/backends.yaml")
        for b in reg.list_backends():
            if b.group == "coding":
                b.healthy = True
        return [c for c in reg.get_backend_candidates("auto-coding") if c.group == "coding"]

    def test_omlx_coding_outranks_ollama_coding(self, coding_candidates):
        assert [c.id for c in coding_candidates] == ["omlx-coding", "ollama-coding"]

    @pytest.mark.parametrize(
        ("hint", "native_id"),
        [
            ("qwen3-coder:30b-a3b-q4_K_M-ctx16k", "Qwen3-Coder-30B-A3B-Instruct-4bit"),
            ("portal5/laguna-xs21:q4_K_M-ctx128k", "Laguna-XS-2.1-4bit"),
        ],
    )
    def test_production_hints_resolve_and_prioritize_omlx(self, coding_candidates, hint, native_id):
        from portal.platform.inference.router.handlers import _prioritize_hinted_backend

        omlx = next(c for c in coding_candidates if c.id == "omlx-coding")
        assert omlx.resolve_model(hint) == native_id

        ordered = _prioritize_hinted_backend(coding_candidates, hint)
        assert ordered[0].id == "omlx-coding"

    def test_auto_coding_base_seat_restored_to_omlx_mtp_with_gguf_fallback(self):
        """P5-OMLX-QWEN38-MTP-001 resolved (template parity default): auto-coding
        serves the oMLX MTP seat again, with the evaluated Ollama GGUF tag as its
        fallback; general-deep, auto-compliance, and auto-coding variants keep
        their serving unchanged."""
        import yaml

        from portal.platform.inference.router.handlers import _prioritize_hinted_backend

        reg = BackendRegistry(config_path="config/backends.yaml")
        for b in reg.list_backends():
            b.healthy = True
        reg._refresh_healthy_cache()

        portal = yaml.safe_load(open("config/portal.yaml", encoding="utf-8"))
        workspaces = portal["workspaces"]

        def _first(ws_id: str, hint: str) -> tuple[str, str | None]:
            ordered = _prioritize_hinted_backend(reg.get_backend_candidates(ws_id), hint)
            return ordered[0].id, ordered[0].resolve_model(hint)

        base_hint = workspaces["auto-coding"]["model_hint"]
        _primary_id, _primary_model = _first("auto-coding", base_hint)
        assert (_primary_id, _primary_model) == ("omlx-coding", "Qwen3.8-27B-oQ4e-mtp")
        # The evaluated GGUF arm stays reachable as the same seat's fallback.
        coding = [c for c in reg.get_backend_candidates("auto-coding") if c.group == "coding"]
        fallback = next(c for c in coding if c.id == "ollama-coding")
        assert fallback.resolve_model(base_hint) == base_hint
        assert _first(
            "auto-daily::deep", workspaces["auto-daily"]["variants"]["deep"]["model_hint"]
        ) == ("omlx-general", "Qwen3.8-27B-oQ4e-mtp")
        assert _first("auto-compliance", workspaces["auto-compliance"]["model_hint"]) == (
            "omlx-reasoning",
            "Qwen3.8-27B-oQ4e-mtp",
        )
        assert _first(
            "auto-coding::heavy", workspaces["auto-coding"]["variants"]["heavy"]["model_hint"]
        ) == ("omlx-coding", "Qwen3.8-27B-oQ4e-mtp")
        assert _first(
            "auto-coding::qwen38coder",
            workspaces["auto-coding"]["variants"]["qwen38coder"]["model_hint"],
        ) == ("omlx-coding", "Qwen3.8-27B-oQ4e-mtp")


class TestAutoSecurityOmlxRouting:
    """The security seats use direct oMLX ids and retain their Ollama aliases."""

    _HINTS = {
        "Inkling-2-Mini-oQ4e-mtp": "inkling-2-mini:ctx256k",
        "Inkling-2-Mini-abliterated-oQ4e-mtp": (
            "portal5/orcarouter-inkling-2-mini-abliterated:mix16g-ctx32k"
        ),
    }

    @pytest.fixture
    def security_registry(self):
        return BackendRegistry(config_path="config/backends.yaml")

    def test_healthy_omlx_security_backend_is_first_and_both_aliases_resolve(
        self, security_registry
    ):
        candidates = [
            candidate
            for candidate in security_registry.get_backend_candidates("auto-security")
            if candidate.group == "security"
        ]

        assert [candidate.id for candidate in candidates] == ["omlx-security", "ollama-security"]
        omlx, ollama = candidates
        for hint, gguf in self._HINTS.items():
            assert omlx.resolve_model(hint) == hint
            assert ollama.resolve_model(hint) == gguf

    def test_unhealthy_omlx_security_backend_leaves_ollama_alias_as_candidate(
        self, security_registry
    ):
        omlx = next(b for b in security_registry.list_backends() if b.id == "omlx-security")
        omlx.healthy = False
        security_registry._invalidate_candidate_cache()

        candidates = [
            candidate
            for candidate in security_registry.get_backend_candidates("auto-security")
            if candidate.group == "security"
        ]

        assert [candidate.id for candidate in candidates] == ["ollama-security"]
        for hint, gguf in self._HINTS.items():
            assert candidates[0].resolve_model(hint) == gguf
