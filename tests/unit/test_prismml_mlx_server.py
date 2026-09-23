"""MLX pack loader selection without importing the model runtime."""

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
    assert server._CONFIG["schema_version"] == 2
    assert server._CHAT_TEMPLATE == "template"
