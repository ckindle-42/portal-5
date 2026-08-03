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
    def test_injects_openai_surface_only(self, monkeypatch):
        from portal.platform.inference.router import validation as vm

        monkeypatch.setitem(
            vm.WORKSPACES,
            "ws-omlx",
            {"predict_limit": 512, "temperature": 0.2, "top_p": 0.9, "top_k": 20},
        )
        out = vm._inject_omlx_options({"messages": [], "stream": True}, "ws-omlx")
        assert out["max_tokens"] == 512
        assert out["stream_options"]["include_usage"] is True
        assert out["temperature"] == 0.2
        assert out["top_p"] == 0.9
        # No Ollama-idiom anywhere: no options sub-dict, no keep_alive, no num_ctx
        assert "options" not in out
        assert "keep_alive" not in out
        assert "top_k" not in out  # not an OpenAI field — left to server-side settings

    def test_caller_values_win_and_no_mutation(self, monkeypatch):
        from portal.platform.inference.router import validation as vm

        monkeypatch.setitem(vm.WORKSPACES, "ws-omlx", {"predict_limit": 512, "temperature": 0.2})
        body = {"messages": [], "max_tokens": 99, "temperature": 0.7, "stream": False}
        out = vm._inject_omlx_options(body, "ws-omlx")
        assert out["max_tokens"] == 99
        assert out["temperature"] == 0.7
        assert "stream_options" not in out  # non-streaming
        assert "max_tokens" not in body or body["max_tokens"] == 99  # original untouched


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
