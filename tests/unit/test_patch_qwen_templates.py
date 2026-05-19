"""Unit tests for scripts/patch-qwen-templates.py.

Uses tmp_path fixtures for isolated model-dir simulation. No real models,
no HF cache, no network — pure file-system manipulation.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
PATCH_SCRIPT = REPO / "scripts" / "patch-qwen-templates.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("patch_qwen_templates", PATCH_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_model_dir(
    tmp_path: pathlib.Path, model_id: str, template_text: str
) -> pathlib.Path:
    d = tmp_path / "models" / model_id
    d.mkdir(parents=True)
    (d / "chat_template.jinja").write_text(template_text)
    (d / "tokenizer_config.json").write_text(
        json.dumps({"chat_template": template_text})
    )
    return d


def _stub_tpl_dir(tmp_path: pathlib.Path, mod) -> pathlib.Path:
    tpl = tmp_path / "tpl"
    for fam in ("qwen3.5", "qwen3.6"):
        (tpl / fam).mkdir(parents=True)
        (tpl / fam / "chat_template.jinja").write_text(f"VENDORED_{fam.upper()}")
    mod.TPL_DIR = tpl
    return tpl


def test_patch_installs_template(tmp_path, monkeypatch):
    """Vendored template gets copied; backup of original is created."""
    mod = _load_module()
    monkeypatch.setattr(mod, "_model_dirs", lambda: [tmp_path / "models"])
    _stub_tpl_dir(tmp_path, mod)
    _fake_model_dir(tmp_path, "huihui-ai/Test-Qwen3.5", "OFFICIAL_|items_BROKEN")

    result = mod._patch_model("huihui-ai/Test-Qwen3.5", "qwen3.5", dry_run=False)
    assert result.startswith("PATCH"), result

    target = tmp_path / "models" / "huihui-ai/Test-Qwen3.5" / "chat_template.jinja"
    assert target.read_text() == "VENDORED_QWEN3.5"
    backup = target.parent / "chat_template.jinja.portal5-backup"
    assert "OFFICIAL_|items_BROKEN" in backup.read_text()


def test_patch_updates_tokenizer_config(tmp_path, monkeypatch):
    """tokenizer_config.json['chat_template'] is updated when present."""
    mod = _load_module()
    monkeypatch.setattr(mod, "_model_dirs", lambda: [tmp_path / "models"])
    _stub_tpl_dir(tmp_path, mod)
    d = _fake_model_dir(tmp_path, "test/Model", "BROKEN")

    mod._patch_model("test/Model", "qwen3.5", dry_run=False)

    tok = json.loads((d / "tokenizer_config.json").read_text())
    assert tok["chat_template"] == "VENDORED_QWEN3.5"


def test_patch_is_idempotent(tmp_path, monkeypatch):
    """Re-running on an already-patched model emits NOOP, not a second backup."""
    mod = _load_module()
    monkeypatch.setattr(mod, "_model_dirs", lambda: [tmp_path / "models"])
    _stub_tpl_dir(tmp_path, mod)
    _fake_model_dir(tmp_path, "test/Model", "VENDORED_QWEN3.5")  # already patched

    result = mod._patch_model("test/Model", "qwen3.5", dry_run=False)
    assert result.startswith("NOOP"), result
    backup = tmp_path / "models" / "test/Model" / "chat_template.jinja.portal5-backup"
    assert not backup.exists()


def test_rollback_restores_original(tmp_path, monkeypatch):
    """Rollback copies .portal5-backup over the patched file."""
    mod = _load_module()
    monkeypatch.setattr(mod, "_model_dirs", lambda: [tmp_path / "models"])

    d = _fake_model_dir(tmp_path, "test/M", "PATCHED")
    (d / "chat_template.jinja.portal5-backup").write_text("ORIGINAL")

    result = mod._rollback_model("test/M", dry_run=False)
    assert result.startswith("REVERT"), result
    assert (d / "chat_template.jinja").read_text() == "ORIGINAL"


def test_skip_when_model_absent(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "_model_dirs", lambda: [tmp_path / "models"])
    result = mod._patch_model("nope/ghost", "qwen3.5", dry_run=False)
    assert result.startswith("SKIP"), result


def test_dry_run_does_not_mutate(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "_model_dirs", lambda: [tmp_path / "models"])
    _stub_tpl_dir(tmp_path, mod)
    d = _fake_model_dir(tmp_path, "test/M", "BROKEN")

    result = mod._patch_model("test/M", "qwen3.5", dry_run=True)
    assert result.startswith("PLAN"), result
    assert (d / "chat_template.jinja").read_text() == "BROKEN"
    assert not (d / "chat_template.jinja.portal5-backup").exists()


def test_invalid_family_filtered(tmp_path, monkeypatch):
    """Unknown family in YAML is logged + skipped, not silently applied."""
    mod = _load_module()
    monkeypatch.setattr(mod, "_model_dirs", lambda: [tmp_path / "models"])

    yaml_path = tmp_path / "backends.yaml"
    yaml_path.write_text("""
backends:
  - id: mlx
    type: mlx
    url: http://x
    group: mlx
    mlx_models:
      - id: test/Good
        chat_template_override: qwen3.5
      - id: test/Bad
        chat_template_override: qwen99-future
""")
    monkeypatch.setattr(mod, "BACKENDS_YAML", yaml_path)

    overrides = mod._read_overrides()
    ids = [m[0] for m in overrides]
    assert "test/Good" in ids
    assert "test/Bad" not in ids


def test_sha_manifest_mismatch_raises(tmp_path, monkeypatch):
    """_verify_manifest exits on tampered template files."""
    mod = _load_module()
    tpl = tmp_path / "tpl"
    for fam in ("qwen3.5", "qwen3.6"):
        (tpl / fam).mkdir(parents=True)
        (tpl / fam / "chat_template.jinja").write_text("ACTUAL")
    (tpl / "SHA256SUMS").write_text(
        "deadbeef" * 8 + "  qwen3.5/chat_template.jinja\n"
        "deadbeef" * 8 + "  qwen3.6/chat_template.jinja\n"
    )
    monkeypatch.setattr(mod, "TPL_DIR", tpl)
    with pytest.raises(SystemExit, match="SHA mismatch"):
        mod._verify_manifest()
