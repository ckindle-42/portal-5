"""Model refresh derives targets from backends.yaml and refuses a plain hf.co pull."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import httpx
import pytest

from portal.platform.inference.cli import model_refresh as refresh
from portal.platform.inference.cli import update as update_cli
from portal.platform.inference.cluster_backends import BackendRegistry
from portal.platform.inference.config import Model, load_portal_config

_BODY = b"gguf-bytes"
_SHA = hashlib.sha256(_BODY).hexdigest()
_TAG = "hf.co/org/Model-GGUF:Q4_K_M"
_BAKED = re.compile(r"-ctx\d+k(?:-[A-Za-z0-9]+)?$")


class _Runner:
    def __init__(self, show: str = "FROM blob\n") -> None:
        self.calls: list[list[str]] = []
        self.modelfiles: list[str] = []
        self.show = show

    def __call__(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        if "create" in argv:
            self.modelfiles.append(Path(argv[argv.index("-f") + 1]).read_text(encoding="utf-8"))
        stdout = self.show if "show" in argv else ""
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")


def _client(body: bytes, seen: list[httpx.Request], status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _pin(**overrides: object) -> refresh.GGUFPin:
    raw: dict[str, object] = {
        "tag": _TAG,
        "repo": "org/Model-GGUF",
        "filename": "model.gguf",
        "sha256": _SHA,
        "num_ctx": 4096,
        "stops": (),
    }
    raw.update(overrides)
    return refresh.GGUFPin(**raw)  # type: ignore[arg-type]


def _install(
    tmp_path: Path,
    *,
    body: bytes = _BODY,
    show: str = "FROM blob\nPARAMETER num_ctx 4096\n",
    pin: refresh.GGUFPin | None = None,
) -> tuple[refresh.InstallResult, _Runner, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    runner = _Runner(show)
    result = refresh.install_pinned(
        pin or _pin(),
        "ollama",
        runner=runner,
        client=_client(body, seen),
        dest_dir=tmp_path,
    )
    return result, runner, seen


def test_update_module_has_no_hardcoded_model_list() -> None:
    assert not hasattr(update_cli, "_DEFAULT_MODELS")
    assert not hasattr(update_cli, "_HEAVY_MODELS")


def test_registry_targets_dedupe_ollama_ids_and_skip_omlx(tmp_path: Path) -> None:
    pinned = "a" * 64
    bare = "hf.co/org/Bare-GGUF:Q4"
    later = "hf.co/org/Later-GGUF:Q4"
    (tmp_path / "backends.yaml").write_text(
        f"""
backends:
- id: ol
  type: ollama
  url: http://127.0.0.1:9
  group: general
  models:
  - id: granite4.1:8b
    supports_tools: true
  - id: huihui_ai/qwen3.5-abliterated:9b
    supports_tools: true
  - id: {_TAG}
    supports_tools: true
    filename: model.gguf
    sha256: "{pinned}"
    num_ctx: 4096
    stops: ["<|im_end|>"]
  - id: {bare}
    supports_tools: false
  - id: {later}
    supports_tools: true
  - granite-string-legacy
- id: ox
  type: omlx
  url: http://127.0.0.1:9
  group: omlx
  models:
  - id: Only-MLX-4bit
    supports_tools: true
- id: ol2
  type: ollama
  url: http://127.0.0.1:9
  group: coding
  models:
  - id: granite4.1:8b
    supports_tools: true
  - id: {later}
    supports_tools: true
    filename: later.gguf
    sha256: "{pinned}"
    repo: org/Later-GGUF
""",
        encoding="utf-8",
    )
    plans = refresh.plans_from_registry(BackendRegistry(str(tmp_path / "backends.yaml")))
    by_tag = {plan.tag: plan for plan in plans}
    assert [plan.tag for plan in plans] == list(by_tag)
    assert "Only-MLX-4bit" not in by_tag
    assert by_tag["granite4.1:8b"].action == "pull"
    assert by_tag["huihui_ai/qwen3.5-abliterated:9b"].action == "pull"
    assert by_tag["granite-string-legacy"].action == "pull"
    assert by_tag[bare].action == "skip"
    assert "filename" in by_tag[bare].reason
    created = by_tag[_TAG]
    assert created.action == "create"
    assert created.pin is not None
    assert created.pin.sha256 == pinned
    assert created.pin.num_ctx == 4096
    assert created.pin.stops == ("<|im_end|>",)
    assert created.pin.repo == "org/Model-GGUF"
    filled = by_tag[later]
    assert filled.action == "create"
    assert filled.pin is not None
    assert filled.pin.filename == "later.gguf"


def _assert_base(plan: refresh.RefreshPlan, tag: str, action: str, num_ctx: int) -> None:
    assert plan.action == "derive"
    assert plan.num_ctx == num_ctx
    assert plan.base_plan is not None
    assert plan.base_plan.tag == tag
    assert plan.base_plan.action == action


def _assert_fleet_examples(by_tag: dict[str, refresh.RefreshPlan]) -> None:
    _assert_base(
        by_tag["qwen3-coder:30b-a3b-q4_K_M-ctx32k"], "qwen3-coder:30b-a3b-q4_K_M", "pull", 32768
    )
    _assert_base(by_tag["gemma4:31b-it-qat-ctx8k"], "gemma4:31b-it-qat", "pull", 8192)
    _assert_base(
        by_tag["glm-4.7-flash:Q4_K_M-ctx64k-agentic"], "glm-4.7-flash:Q4_K_M", "pull", 65536
    )
    _assert_base(
        by_tag["huihui_ai/qwen3.5-abliterated:9b-ctx8k"],
        "huihui_ai/qwen3.5-abliterated:9b",
        "pull",
        8192,
    )
    local = by_tag["portal5/laguna-xs21:q4_K_M-ctx128k"]
    assert local.action == "skip"
    assert local.reason == "local tag, no upstream"
    drafted = by_tag["portal5/qwen3.6-27b-mtp:q8_0-drafted"]
    assert drafted.action == "skip"
    assert drafted.reason == "local tag, no upstream"
    _assert_base(
        by_tag["hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"],
        "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M",
        "skip",
        32768,
    )


def test_live_backends_keep_library_tags_and_do_not_pull_hf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BACKEND_CONFIG_PATH", raising=False)
    plans = refresh.plans_from_registry(BackendRegistry())
    tags = [plan.tag for plan in plans]
    by_tag = {plan.tag: plan for plan in plans}
    assert tags == list(dict.fromkeys(tags))
    assert "Qwen3-Coder-30B-A3B-Instruct-4bit" not in tags
    granite = by_tag["granite4.1:8b"]
    assert granite.action == "pull"
    assert granite.tag == "granite4.1:8b"
    hf = [plan for plan in plans if plan.tag.startswith("hf.co/")]
    assert hf
    assert all(plan.action != "pull" for plan in hf)
    _assert_fleet_examples(by_tag)
    for plan in plans:
        qual = plan.tag.rpartition(":")[2]
        if plan.tag.startswith("portal5/"):
            assert plan.action == "skip"
            assert plan.reason == "local tag, no upstream"
        elif _BAKED.search(qual):
            assert plan.action == "derive"
            assert plan.base_plan is not None
            assert plan.base_plan.action != "derive"
    counts = refresh.plan_counts(plans)
    assert sum(counts.values()) == len(plans)
    assert counts["pull"] > 0
    assert counts["derive"] > 0
    assert counts["skip"] > 0


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


def test_missing_pin_does_not_call_ollama_or_http(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    runner = _Runner()
    plan = refresh.RefreshPlan(
        "hf.co/org/Bare-GGUF:Q4", "skip", reason="missing pinned filename+sha256"
    )
    result = refresh.execute_plan(
        plan, "ollama", runner=runner, client=_client(_BODY, seen), dest_dir=tmp_path
    )
    assert result.status == "skipped"
    assert runner.calls == []
    assert seen == []


def test_sha_mismatch_refuses_create(tmp_path: Path) -> None:
    result, runner, seen = _install(tmp_path, body=b"not-the-file")
    assert result.ok is False
    assert result.status == "failed"
    assert "sha256 mismatch" in result.message
    assert all(call[1] != "create" for call in runner.calls)
    assert all(call[1] != "pull" for call in runner.calls)
    assert seen[0].url.host == "huggingface.co"
    assert seen[0].url.path == "/org/Model-GGUF/resolve/main/model.gguf"
    assert not (tmp_path / "model.gguf").exists()


def test_pinned_create_writes_from_and_num_ctx_only(tmp_path: Path) -> None:
    show = "FROM blob\nPARAMETER num_ctx 4096\nPARAMETER stop <|im_end|>\n"
    result, runner, _seen = _install(tmp_path, show=show, pin=_pin(stops=("<|im_end|>",)))
    assert result.status == "created"
    text = runner.modelfiles[0]
    assert text.splitlines() == [
        f"FROM {(tmp_path / 'model.gguf').resolve()}",
        "PARAMETER num_ctx 4096",
    ]
    assert "temperature" not in text
    assert "PARAMETER stop" not in text
    assert runner.calls[0][:3] == ["ollama", "create", _TAG]
    assert runner.calls[1][:4] == ["ollama", "show", _TAG, "--modelfile"]


def test_think_stop_fails_render_check(tmp_path: Path) -> None:
    show = (
        'TEMPLATE """{{ if .Think }}<think>{{ end }}"""\n'
        'PARAMETER stop "<think>"\n'
        "PARAMETER stop </think>\n"
    )
    result, runner, _seen = _install(tmp_path, show=show)
    assert result.ok is False
    assert "<think>" in result.message
    assert "</think>" in result.message
    assert any(call[1] == "create" for call in runner.calls)
    assert all(call[1] != "pull" for call in runner.calls)


def test_template_think_text_is_not_a_stop(tmp_path: Path) -> None:
    show = 'TEMPLATE """{{ if .Think }}<think>{{ end }}"""\nPARAMETER num_ctx 4096\n'
    result, _runner, _seen = _install(tmp_path, show=show)
    assert result.status == "created"


def test_undeclared_stop_fails_and_declared_stop_passes(tmp_path: Path) -> None:
    show = "PARAMETER stop <|im_end|>\n"
    refused, _runner, _seen = _install(tmp_path, show=show)
    assert refused.status == "failed"
    assert "<|im_end|>" in refused.message
    allowed, _runner2, _seen2 = _install(tmp_path, show=show, pin=_pin(stops=("<|im_end|>",)))
    assert allowed.status == "created"
    think_allowed, _runner3, _seen3 = _install(
        tmp_path,
        show='PARAMETER stop "<think>"\n',
        pin=_pin(stops=("<think>",)),
    )
    assert think_allowed.status == "failed"
    assert "<think>" in think_allowed.message


def test_fleet_shaped_ids_prefer_configured_num_ctx_and_pinned_base(tmp_path: Path) -> None:
    pinned = "b" * 64
    (tmp_path / "backends.yaml").write_text(
        f"""
backends:
- id: ol
  type: ollama
  url: http://127.0.0.1:9
  group: general
  models:
  - id: gemma4:31b-it-qat-ctx8k
    num_ctx: 2048
  - id: qwen3-coder:30b-a3b-q4_K_M-ctx32k
  - id: portal5/laguna-xs21:q4_K_M-ctx128k
  - id: hf.co/org/Pinned-GGUF:Q4_K_M
    filename: model.gguf
    sha256: "{pinned}"
    repo: org/Pinned-GGUF
  - id: hf.co/org/Pinned-GGUF:Q4_K_M-ctx8k
  - id: portal5/deepwen-3.6:q4.5-moq
    filename: deepwen.gguf
    sha256: "{pinned}"
    repo: org/Deepwen-GGUF
""",
        encoding="utf-8",
    )
    plans = {
        plan.tag: plan
        for plan in refresh.plans_from_registry(BackendRegistry(str(tmp_path / "backends.yaml")))
    }
    override = plans["gemma4:31b-it-qat-ctx8k"]
    assert override.action == "derive"
    assert override.num_ctx == 2048
    assert override.base_plan is not None
    assert override.base_plan.action == "pull"
    assert override.base_plan.tag == "gemma4:31b-it-qat"
    coder = plans["qwen3-coder:30b-a3b-q4_K_M-ctx32k"]
    assert coder.action == "derive"
    assert coder.num_ctx == 32768
    assert plans["portal5/laguna-xs21:q4_K_M-ctx128k"].action == "skip"
    assert plans["portal5/laguna-xs21:q4_K_M-ctx128k"].reason == "local tag, no upstream"
    derived = plans["hf.co/org/Pinned-GGUF:Q4_K_M-ctx8k"]
    assert derived.action == "derive"
    assert derived.num_ctx == 8192
    assert derived.base_plan is not None
    assert derived.base_plan.action == "create"
    assert derived.base_plan.pin is not None
    assert derived.base_plan.pin.repo == "org/Pinned-GGUF"
    assert plans["portal5/deepwen-3.6:q4.5-moq"].action == "create"


def test_derive_pulls_the_base_and_creates_the_ctx_tag(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    runner = _Runner()
    plan = refresh.RefreshPlan(
        "qwen3-coder:30b-a3b-q4_K_M-ctx32k",
        "derive",
        base_plan=refresh.RefreshPlan("qwen3-coder:30b-a3b-q4_K_M", "pull"),
        num_ctx=32768,
    )
    result = refresh.execute_plan(
        plan, "ollama", runner=runner, client=_client(_BODY, seen), dest_dir=tmp_path
    )
    assert result.status == "created"
    assert runner.calls[0] == ["ollama", "pull", "qwen3-coder:30b-a3b-q4_K_M"]
    assert runner.calls[1][:3] == ["ollama", "create", "qwen3-coder:30b-a3b-q4_K_M-ctx32k"]
    assert runner.modelfiles == [
        "FROM qwen3-coder:30b-a3b-q4_K_M\nPARAMETER num_ctx 32768\n",
    ]
    assert all(call[1:] != ["pull", plan.tag] for call in runner.calls)
    assert seen == []
    assert refresh.ctx_modelfile_text("gemma4:31b-it-qat", 8192) == (
        "FROM gemma4:31b-it-qat\nPARAMETER num_ctx 8192\n"
    )


def test_local_and_unpinned_hf_derive_do_not_call_ollama(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    runner = _Runner()
    local = refresh.RefreshPlan(
        "portal5/laguna-xs21:q4_K_M-ctx128k",
        "skip",
        reason="local tag, no upstream",
    )
    hf = refresh.RefreshPlan(
        "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k",
        "derive",
        base_plan=refresh.RefreshPlan(
            "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M",
            "skip",
            reason="missing pinned filename+sha256",
        ),
        num_ctx=32768,
    )
    client = _client(_BODY, seen)
    local_result = refresh.execute_plan(
        local, "ollama", runner=runner, client=client, dest_dir=tmp_path
    )
    hf_result = refresh.execute_plan(hf, "ollama", runner=runner, client=client, dest_dir=tmp_path)
    assert local_result.status == "skipped"
    assert hf_result.status == "skipped"
    assert "missing pinned filename+sha256" in hf_result.message
    assert runner.calls == []
    assert seen == []


def test_library_pull_keeps_the_tag(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    runner = _Runner()
    plan = refresh.RefreshPlan("granite4.1:8b", "pull")
    result = refresh.execute_plan(
        plan, "ollama", runner=runner, client=_client(_BODY, seen), dest_dir=tmp_path
    )
    assert result.status == "pulled"
    assert runner.calls == [["ollama", "pull", "granite4.1:8b"]]
    assert seen == []


def test_pull_hf_model_skips_unpinned_without_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(subprocess, "run", explode)
    from portal.platform.inference.cli.models import _pull_hf_model

    model = Model(hf_id="org/Repo-GGUF", filename="model.gguf", ollama_name="local:tag")
    assert _pull_hf_model(model, "ollama") is True


def test_pull_hf_model_library_tag_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    from portal.platform.inference.cli.models import _pull_hf_model

    model = Model(hf_id="granite4.1", ollama_name="granite4.1:8b")
    assert _pull_hf_model(model, "ollama") is True
    assert calls == [["ollama", "pull", "granite4.1:8b"]]
