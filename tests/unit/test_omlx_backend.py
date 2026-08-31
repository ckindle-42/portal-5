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


def _write(tmp_path, text: str):
    cfg = tmp_path / "backends.yaml"
    cfg.write_text(text)
    return cfg


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

    def test_update_omlx_live_models_warns_on_gap(self, caplog):
        import httpx

        reg = BackendRegistry.__new__(BackendRegistry)
        be = Backend(
            id="omlx-reasoning",
            type="omlx",
            url="http://x",
            group="reasoning",
            models=["granite-4.1-30b-4bit"],
            aliases={"tongyi:ctx64k": "Tongyi-30B-4bit"},
        )
        resp = httpx.Response(
            200, json={"data": [{"id": "Qwen3.8-27B-oQ4e-mtp"}, {"id": "Laguna-XS.2-4bit"}]}
        )
        with caplog.at_level("WARNING"):
            reg._update_omlx_live_models(be, resp)
        assert be.live_models == {"Qwen3.8-27B-oQ4e-mtp", "Laguna-XS.2-4bit"}
        assert "granite-4.1-30b-4bit" in caplog.text
        assert "Tongyi-30B-4bit" in caplog.text


class TestOmlxConfigLoad:
    def test_loads_omlx_fields(self, tmp_path):
        cfg = _write(
            tmp_path,
            """
backends:
  - id: omlx-local
    type: omlx
    url: http://localhost:8085
    group: omlx
    priority: 10
    health_path: /v1/models
    models:
      - id: Native-Model-4bit
        supports_tools: true
    aliases:
      gguf-tag-ctx16k: Native-Model-4bit
workspace_routing:
  auto: [general]
defaults:
  fallback_group: general
""",
        )
        reg = BackendRegistry(config_path=str(cfg))
        be = reg.list_backends()[0]
        assert be.type == "omlx"
        assert be.priority == 10
        assert be.health_path == "/v1/models"
        assert be.aliases == {"gguf-tag-ctx16k": "Native-Model-4bit"}
        assert be.models == ["Native-Model-4bit"]
        assert be.health_url == "http://localhost:8085/v1/models"


class TestPriorityOrdering:
    def test_higher_priority_serves_first(self, tmp_path):
        cfg = _write(
            tmp_path,
            """
backends:
  - id: ollama-coding
    type: ollama
    url: http://localhost:11434
    group: coding
    priority: 0
    models: [gguf-model]
  - id: omlx-local
    type: omlx
    url: http://localhost:8085
    group: coding
    priority: 10
    models: [mlx-model]
workspace_routing:
  auto-coding: [coding]
defaults:
  fallback_group: general
""",
        )
        reg = BackendRegistry(config_path=str(cfg))
        # Priority must hold across repeated shuffles (no TTL races: build
        # fresh candidate lists several times).
        for _ in range(25):
            candidates = reg.get_backend_candidates("auto-coding")
            assert candidates[0].id == "omlx-local"
            assert candidates[1].id == "ollama-coding"

    def test_zero_priority_preserves_shuffle_semantics(self, tmp_path):
        """All-zero priorities behave exactly as before (both orders appear)."""
        cfg = _write(
            tmp_path,
            """
backends:
  - id: b1
    type: ollama
    url: http://a
    group: general
    models: [m1]
  - id: b2
    type: ollama
    url: http://b
    group: general
    models: [m2]
workspace_routing:
  auto: [general]
defaults:
  fallback_group: general
""",
        )
        reg = BackendRegistry(config_path=str(cfg))
        firsts = set()
        for _ in range(40):
            firsts.add(reg.get_backend_candidates("auto")[0].id)
            reg._invalidate_candidate_cache()
        assert firsts == {"b1", "b2"}


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

    def test_caller_values_win_and_no_mutation(self, monkeypatch):
        from portal.platform.inference.router import validation as vm

        monkeypatch.setitem(vm.WORKSPACES, "ws-omlx", {"predict_limit": 512, "temperature": 0.2})
        body = {"messages": [], "max_tokens": 99, "temperature": 0.7, "stream": False}
        out = vm._inject_omlx_options(body, "ws-omlx")
        assert out["max_tokens"] == 99
        assert out["temperature"] == 0.7
        assert "stream_options" not in out  # non-streaming
        assert "max_tokens" not in body or body["max_tokens"] == 99  # original untouched

    def test_think_profile_wins_over_flat_fields(self, monkeypatch):
        """Same think_profiles resolution as the Ollama path applies here too."""
        from portal.platform.inference.router import validation as vm

        monkeypatch.setitem(
            vm.WORKSPACES,
            "ws-omlx-think",
            {
                "temperature": 0.2,
                "think": True,
                "think_profiles": {
                    "thinking": {"temperature": 1.0, "presence_penalty": 0.0},
                    "instruct": {"temperature": 0.7, "presence_penalty": 1.5},
                },
            },
        )
        out = vm._inject_omlx_options({}, "ws-omlx-think")
        assert out["temperature"] == 1.0
        assert out["presence_penalty"] == 0.0
        assert out["chat_template_kwargs"] == {"enable_thinking": True}


class TestBackendIntrospect:
    @pytest.mark.asyncio
    async def test_omlx_reachable_means_busy(self, monkeypatch):
        from portal.platform.inference.router import backend_introspect as bi

        class _Resp:
            status_code = 200

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url):
                assert url.endswith("/v1/models")
                return _Resp()

        monkeypatch.setattr(bi.httpx, "AsyncClient", lambda *a, **k: _Client())
        monkeypatch.setattr(bi, "_backend_type_for_url", lambda base: "omlx")
        assert await bi.model_still_running("http://omlx:8085/v1/chat/completions") is True

    @pytest.mark.asyncio
    async def test_omlx_unreachable_means_down(self, monkeypatch):
        from portal.platform.inference.router import backend_introspect as bi

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url):
                raise httpx.ConnectError("down")

        import httpx

        monkeypatch.setattr(bi.httpx, "AsyncClient", lambda *a, **k: _Client())
        monkeypatch.setattr(bi, "_backend_type_for_url", lambda base: "omlx")
        assert await bi.model_still_running("http://omlx:8085/v1/chat/completions") is False

    @pytest.mark.asyncio
    async def test_ollama_path_uses_legacy_probe(self, monkeypatch):
        from portal.platform.inference.router import backend_introspect as bi

        called = {}

        async def _fake(base, timeout_s):
            called["base"] = base
            return True

        monkeypatch.setattr(bi, "_ollama_model_loaded", _fake)
        monkeypatch.setattr(bi, "_backend_type_for_url", lambda base: "ollama")
        assert await bi.model_still_running("http://localhost:11434/v1/chat/completions") is True
        assert called["base"] == "http://localhost:11434"

    def test_type_resolution_falls_back_to_ollama(self, monkeypatch):
        from portal.platform.inference.router import backend_introspect as bi
        from portal.platform.inference.router import validation

        monkeypatch.setattr(validation, "registry", None)
        assert bi._backend_type_for_url("http://anything") == "ollama"


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
            ("laguna-xs.2:Q4_K_M-ctx64k", "Laguna-XS.2-4bit"),
        ],
    )
    def test_production_hints_resolve_and_prioritize_omlx(self, coding_candidates, hint, native_id):
        from portal.platform.inference.router.handlers import _prioritize_hinted_backend

        omlx = next(c for c in coding_candidates if c.id == "omlx-coding")
        assert omlx.resolve_model(hint) == native_id

        ordered = _prioritize_hinted_backend(coding_candidates, hint)
        assert ordered[0].id == "omlx-coding"
