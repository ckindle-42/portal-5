"""`portal models apply-renderers`: rebuilds gate-refused tags in place — mocked API."""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from portal.platform.inference.cli import renderers
from portal.platform.inference.cli._apps import models_app

TAG = "hf.co/unsloth/flint-GGUF:UD-Q4_K_XL"
ARCH = "flint"
BASE_MODELFILE = (
    "FROM /ollama/models/blobs/sha256-abc\n"
    "PARAMETER temperature 0.6\n"
    "PARAMETER num_ctx 262144\n"
    'PARAMETER stop "<|observation|>"\n'
)
PARAMS = 'temperature 0.6\nnum_ctx 262144\nstop "<|observation|>"'
LIB_TAG = "flint:latest"
LIB_MODELFILE = "FROM /ollama/models/blobs/sha256-lib\nRENDERER flint\nPARSER flint\n"
ALLOW_TAG = "allowed:Q4"
TABLE: dict[str, Any] = {
    "renderers": {ARCH: {"renderer": "flint", "parser": "flint", "source": "test"}},
    "allow": {ALLOW_TAG: "probe-verified"},
}


def _show(arch: str, modelfile: str, params: str = "") -> dict[str, Any]:
    return {
        "model_info": {"general.architecture": arch},
        "modelfile": modelfile,
        "parameters": params,
        "template": "{{ .Prompt }}",
    }


class FakeOllama:
    """In-memory /api/tags + /api/show; create rewrites the tag's modelfile."""

    def __init__(self, shows: dict[str, dict[str, Any]]) -> None:
        self.shows = dict(shows)
        self.creates: list[tuple[str, str]] = []

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        # /api/tags is GET-only on the real engine; a POST to it is a bug.
        assert path != "/api/tags", "POST /api/tags returns 405 on Ollama"
        return dict(self.shows.get(payload["model"], {}))

    def get(self, path: str) -> dict[str, Any]:
        assert path == "/api/tags"
        return {"models": [{"name": n} for n in self.shows]}

    def create(self, _ollama_cmd: str, tag: str, text: str) -> tuple[bool, str]:
        self.creates.append((tag, text))
        if tag not in self.shows:
            return False, "no such model"
        self.shows[tag]["modelfile"] = text
        return True, ""


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeOllama,
    probe_ok: bool = True,
    probe_out: str = "",
) -> list[str]:
    monkeypatch.setattr(renderers, "_post", fake.post)
    monkeypatch.setattr(renderers, "_get", fake.get)
    monkeypatch.setattr(renderers, "_create", fake.create)
    monkeypatch.setattr(renderers, "_load_table", lambda: TABLE)
    monkeypatch.setattr(renderers, "_detect_ollama_cmd", lambda: "ollama")
    calls: list[str] = []

    def fake_probe(tag: str) -> tuple[bool, str]:
        calls.append(tag)
        return probe_ok, probe_out

    monkeypatch.setattr(renderers, "_probe", fake_probe)
    return calls


def _refused_show() -> dict[str, Any]:
    return _show(ARCH, BASE_MODELFILE, PARAMS)


def _run(*args: str):
    return CliRunner().invoke(models_app, ["apply-renderers", *args])


def test_rebuild_preserves_params_and_bakes_the_pair(monkeypatch):
    fake = FakeOllama({TAG: _refused_show()})
    _wire(monkeypatch, fake)

    result = _run("--tag", TAG)

    assert result.exit_code == 0, result.output
    assert len(fake.creates) == 1
    created_tag, text = fake.creates[0]
    assert created_tag == TAG, "the tag is rebuilt in place, same name"
    assert text.startswith("FROM /ollama/models/blobs/sha256-abc\n")
    assert "PARAMETER temperature 0.6\n" in text
    assert "PARAMETER num_ctx 262144\n" in text
    assert 'PARAMETER stop "<|observation|>"\n' in text
    assert text.endswith("RENDERER flint\nPARSER flint\n")
    assert "applied" in result.output and "num_ctx" in result.output


def test_probe_failure_restores_the_original_modelfile(monkeypatch):
    fake = FakeOllama({TAG: _refused_show()})
    _wire(monkeypatch, fake, probe_ok=False, probe_out="think=false leaked thinking")

    result = _run("--tag", TAG, "--probe")

    assert result.exit_code == 1, result.output
    assert [t for t, _text in fake.creates] == [TAG, TAG]
    assert fake.creates[0][1].endswith("RENDERER flint\nPARSER flint\n")
    assert fake.creates[1][1] == BASE_MODELFILE, "the original Modelfile is restored"
    assert "restored" in result.output and "probe failed" in result.output


def test_allow_entry_is_skipped(monkeypatch):
    fake = FakeOllama({ALLOW_TAG: _show(ARCH, BASE_MODELFILE, PARAMS)})
    _wire(monkeypatch, fake)

    result = _run("--tag", ALLOW_TAG)

    assert result.exit_code == 0, result.output
    assert fake.creates == []
    assert "allow" in result.output and "skipped" in result.output


def test_dry_run_writes_nothing(monkeypatch):
    fake = FakeOllama({TAG: _refused_show()})
    probe_calls = _wire(monkeypatch, fake)

    result = _run("--tag", TAG, "--dry-run")

    assert result.exit_code == 0, result.output
    assert fake.creates == [] and probe_calls == []
    assert "would apply" in result.output and "flint/flint" in result.output
    assert "no changes written" in result.output


def test_a_tag_the_gate_passes_is_never_touched(monkeypatch):
    fake = FakeOllama({LIB_TAG: _show(ARCH, LIB_MODELFILE, "")})
    _wire(monkeypatch, fake)

    result = _run("--tag", LIB_TAG)

    assert result.exit_code == 0, result.output
    assert fake.creates == []
    assert "gate passes: renderer present" in result.output


def test_default_selection_repairs_only_the_refused_tags(monkeypatch):
    fake = FakeOllama(
        {TAG: _refused_show(), LIB_TAG: _show(ARCH, LIB_MODELFILE), ALLOW_TAG: _show(ARCH, "")}
    )
    _wire(monkeypatch, fake)

    result = _run()

    assert result.exit_code == 0, result.output
    assert [t for t, _text in fake.creates] == [TAG]
    assert "1 applied" in result.output
    assert "untouched" in result.output, "gate-passing tags are summarized, not listed"
