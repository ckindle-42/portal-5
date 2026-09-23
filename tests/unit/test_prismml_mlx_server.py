"""MLX pack loader selection without importing the model runtime."""

import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace

from tests.benchmarks import prismml_mlx_server as server


def test_v2_vision_pack_uses_pack_loader_without_processor(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "model_type": "prism_hadamard_qwen35",
                "schema_version": 2,
                "components": {"vision": True},
            }
        )
    )
    (tmp_path / "tokenizer.json").write_text("{}")
    (tmp_path / "chat_template.jinja").write_text("template")

    language_model = object()
    calls = {}

    def load_vl_model(path, *, load_processor):
        calls["path"] = path
        calls["load_processor"] = load_processor
        return SimpleNamespace(language_model=language_model), object(), {}

    vision_artifact = ModuleType("vision_artifact")
    vision_artifact.load_vl_model = load_vl_model
    fake_tokenizers = ModuleType("tokenizers")
    fake_tokenizers.Tokenizer = SimpleNamespace(from_file=lambda _path: object())
    monkeypatch.setitem(sys.modules, "vision_artifact", vision_artifact)
    monkeypatch.setitem(sys.modules, "tokenizers", fake_tokenizers)

    server._load_pack(tmp_path)

    assert calls == {"path": tmp_path.resolve(), "load_processor": False}
    assert server._MODEL is language_model
    assert server._MODEL_API == "packed_language"
    assert server._CONFIG["schema_version"] == 2
    assert server._CHAT_TEMPLATE == "template"


def test_stock_mlx_model_uses_mlx_lm_cache_and_logits_api(monkeypatch):
    cache = object()
    logits = object()
    seen = {}

    class FakeLogits:
        def __getitem__(self, index):
            seen["logits_index"] = index
            return logits

    class FakeModel:
        layers = [object()]

        def __call__(self, tokens, *, cache):
            seen["tokens"] = tokens
            seen["cache"] = cache
            return FakeLogits()

    mlx_lm = ModuleType("mlx_lm")
    models = ModuleType("mlx_lm.models")
    cache_module = ModuleType("mlx_lm.models.cache")
    fake_model = FakeModel()
    cache_module.make_prompt_cache = lambda model: cache if model is fake_model else None
    mlx_lm.models = models
    models.cache = cache_module
    monkeypatch.setitem(sys.modules, "mlx_lm", mlx_lm)
    monkeypatch.setitem(sys.modules, "mlx_lm.models", models)
    monkeypatch.setitem(sys.modules, "mlx_lm.models.cache", cache_module)
    monkeypatch.setattr(server, "_MODEL", fake_model, raising=False)
    monkeypatch.setattr(server, "_MODEL_API", "mlx_lm", raising=False)

    tokens = object()
    actual_cache = server._make_cache()
    actual_logits = server._next_logits(tokens, actual_cache)

    assert actual_cache is cache
    assert actual_logits is logits
    assert seen == {
        "tokens": tokens,
        "cache": cache,
        "logits_index": (slice(None), -1, slice(None)),
    }


def test_streaming_response_keeps_generation_on_async_iterator(tmp_path, monkeypatch):
    class FakeRequest:
        async def json(self):
            return {"messages": [], "stream": True}

    monkeypatch.setattr(server, "_PACK", tmp_path, raising=False)
    monkeypatch.setattr(
        server,
        "_generate",
        lambda _payload: iter(["hello", {"usage": {"prompt_tokens": 2, "completion_tokens": 1}}]),
    )

    response = asyncio.run(server.chat_completions(FakeRequest()))

    assert hasattr(response.body_iterator, "__anext__")

    async def collect():
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(collect())
    assert '"content": "hello"' in chunks[0]
    assert '"prompt_tokens": 2' in chunks[1]
    assert chunks[-1] == "data: [DONE]\n\n"
