"""Model refresh derives targets from backends.yaml and refuses a plain hf.co pull."""

from __future__ import annotations

import subprocess

import typer

from portal.platform.inference.cli import model_refresh as refresh
from portal.platform.inference.cli import update as update_cli
from portal.platform.inference.config import Model, load_portal_config


def test_update_module_has_no_hardcoded_model_list() -> None:
    assert not hasattr(update_cli, "_DEFAULT_MODELS")
    assert not hasattr(update_cli, "_HEAVY_MODELS")


def test_catalog_entries_without_a_pin_skip() -> None:
    missing = Model(hf_id="org/Repo-GGUF", filename="model.gguf", ollama_name="local:tag")
    hf_tag = Model(hf_id="org/Repo-GGUF", ollama_name="hf.co/org/Repo-GGUF:Q4")
    library = Model(hf_id="granite4.1", ollama_name="granite4.1:8b")
    assert refresh.plan_for_catalog_model(missing).action == "skip"
    assert refresh.plan_for_catalog_model(hf_tag).action == "skip"
    assert refresh.plan_for_catalog_model(library).action == "pull"
    assert refresh.plan_for_catalog_model(library).tag == "granite4.1:8b"
    for model in load_portal_config().models:
        plan = refresh.plan_for_catalog_model(model)
        if model.filename and model.sha256 and len(model.sha256) == 64:
            assert plan.action == "create"
        else:
            assert plan.action == "skip"
        assert plan.action != "pull" or not plan.tag.startswith("hf.co/")


def test_manifest_urls_cover_library_and_namespaced_tags() -> None:
    assert refresh.ollama_manifest_url("granite4.1:8b") == (
        "https://registry.ollama.ai/v2/library/granite4.1/manifests/8b"
    )
    assert refresh.ollama_manifest_url("huihui_ai/qwen3.5-abliterated:9b") == (
        "https://registry.ollama.ai/v2/huihui_ai/qwen3.5-abliterated/manifests/9b"
    )
    assert refresh.ollama_manifest_url("meta-secalign-8b-q4_k_m") == (
        "https://registry.ollama.ai/v2/library/meta-secalign-8b-q4_k_m/manifests/latest"
    )
    assert refresh.ollama_manifest_url("meta-secalign-8b-q4_k_m:latest") == (
        refresh.ollama_manifest_url("meta-secalign-8b-q4_k_m")
    )


def test_update_downloads_no_models_unless_asked(monkeypatch, tmp_path) -> None:
    """Operator 2026-10-28: an update never downloads models unless asked; disk is finite."""

    from typer.testing import CliRunner

    from portal.platform.inference.cli import update

    calls: list[list[str]] = []

    def _run(argv, **_k):
        calls.append([str(part) for part in argv])
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "run", _run)
    app = typer.Typer()
    update.register(app)
    app.command("noop")(lambda: None)

    assert CliRunner().invoke(app, ["update", "--yes"]).exit_code == 0
    assert not any("model_autoupdate.py" in part for cmd in calls for part in cmd)
    calls.clear()
    assert CliRunner().invoke(app, ["update", "--yes", "--refresh-models"]).exit_code == 0
    assert any("model_autoupdate.py" in part for cmd in calls for part in cmd)
