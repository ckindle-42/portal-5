"""Stage-2 tail fixes: TTS speech, vision PNG, persona timeout, artifact URLs."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from tests.qat import runner as rn
from tests.qat import scenarios
from tests.qat.config import Settings, discover
from tests.qat.models import Status
from tests.qat.owui_client import artifact_urls
from tests.qat.scenarios import INLINE_VISION_PNG, TTS_SPEECH_BODY

from .test_config_and_scenarios import make_discovery, make_settings
from .test_report_and_runner import FakeOWUI, _chat_opts, _client_factory

_FILE = "/api/v1/files/a7a504af-2dde-49b7-8be4-ad6c754a2975/content/report.docx"
_WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 8
_SLOW_WORKSPACES = frozenset({"auto-security", "auto-reasoning"})


def _registry() -> list:
    return scenarios.build_registry(Settings.load(env_file=Path("/nonexistent")), discover())


def _by_id() -> dict:
    return {scenario.scenario_id: scenario for scenario in _registry()}


def test_artifact_urls_strip_markdown_wrappers() -> None:
    bold = f"**([doc]({_FILE}))**"
    italic = f"([doc]({_FILE}))*"
    assert artifact_urls({"content": bold}) == (_FILE,)
    assert artifact_urls({"content": italic}) == (_FILE,)
    kyoto = (
        "/api/v1/files/a7a504af-2dde-49b7-8be4-ad6c754a2975/content/"
        "Kyoto_Two-Day_Itinerary___Packing_List_28e1a49d.docx"
    )
    assert artifact_urls({"content": f'**([doc]({kyoto}))***"'}) == (kyoto,)
    balanced = "/api/v1/files/a7a504af-2dde-49b7-8be4-ad6c754a2975/content/report_(final).docx"
    assert artifact_urls({"content": f"**([doc]({balanced}))**"}) == (balanced,)


def test_artifact_urls_label_is_url_markdown_link() -> None:
    # s2-p3-auto-coding::cad: the link label IS the URL; matching must stop at ']'.
    path = "/api/v1/files/57e58ee5-2dde-49b7-8be4-ad6c754a2975/content/part_0d6b5f.stl"
    content = f"[{path}](https://chat.intoodeep.systems{path})"
    urls = artifact_urls({"content": content})
    assert urls == (path,)
    assert Path(urlsplit(urls[0]).path).suffix.lower() == ".stl"
    three = "\n".join(
        f"[/api/v1/files/57e58ee5-2dde-49b7-8be4-ad6c754a2975/content/part_{i}.stl]"
        f"(https://chat.intoodeep.systems/api/v1/files/57e58ee5-2dde-49b7-8be4-ad6c754a2975/content/part_{i}.stl)"
        for i in range(3)
    )
    assert artifact_urls({"content": three}) == tuple(
        f"/api/v1/files/57e58ee5-2dde-49b7-8be4-ad6c754a2975/content/part_{i}.stl" for i in range(3)
    )


def test_phase5_slow_personas_timeout_and_vision_prompts() -> None:
    registry = _registry()
    phase5 = [scenario for scenario in registry if scenario.scenario_id.startswith("s2-p5-")]
    slow = [scenario for scenario in phase5 if scenario.model_slug in _SLOW_WORKSPACES]
    fast = [scenario for scenario in phase5 if scenario.model_slug not in _SLOW_WORKSPACES]
    assert any(scenario.scenario_id == "s2-p5-adversarysimulator" for scenario in slow)
    assert slow and all(scenario.timeout_s >= 360.0 for scenario in slow)
    assert fast and all(scenario.timeout_s == 180.0 for scenario in fast)
    chart = _by_id()["s2-p5-chartanalyst"]
    assert chart.model_slug == "auto-vision"
    assert chart.attachment == INLINE_VISION_PNG
    assert "image" in chart.prompts[0].casefold()
    stage4 = [
        scenario for scenario in registry if scenario.scenario_id.startswith("s4-auto-vision-")
    ]
    assert {scenario.scenario_id for scenario in stage4} >= {
        "s4-auto-vision-core",
        "s4-auto-vision-continuity",
        "s4-auto-vision-edge",
    }
    for scenario in stage4:
        assert scenario.attachment == INLINE_VISION_PNG
        assert scenario.prompts
        assert all("image" in prompt.casefold() for prompt in scenario.prompts)


def test_vision_scenarios_send_png_on_every_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    FakeOWUI.instances = []
    FakeOWUI.mode = "valid"
    monkeypatch.setattr(rn, "OWUIClient", FakeOWUI)
    settings = make_settings(tmp_path)
    state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
    by_id = _by_id()
    for scenario_id in ("s2-p5-chartanalyst", "s4-auto-vision-core", "s4-auto-vision-edge"):
        FakeOWUI.instances.clear()
        result = rn._execute_one(settings, by_id[scenario_id], state, _chat_opts())
        assert result.status is Status.PASS, result.detail
        sent = FakeOWUI.instances[0].sent_images
        assert sent
        assert all(blob is not None and blob.startswith(b"\x89PNG\r\n\x1a\n") for blob in sent)
    continuity = by_id["s4-auto-vision-continuity"]
    assert "ORCHID-9" in continuity.prompts[0]
    first = rn._chat_turn_extras(FakeOWUI(settings), "token", continuity, 1, 0.0)[1]
    second = rn._chat_turn_extras(FakeOWUI(settings), "token", continuity, 2, 0.0)[1]
    assert first is not None and second is not None
    assert first.startswith(b"\x89PNG") and second.startswith(b"\x89PNG")
    daily = next(
        scenario for scenario in by_id.values() if scenario.scenario_id == "s2-p5-dailydriver"
    )
    assert rn._chat_turn_extras(FakeOWUI(settings), "token", daily, 1, 0.0)[1] is None


@pytest.mark.parametrize(
    "blob",
    [
        _WAV,
        b"ID3" + b"\x00" * 8,
        b"\xff\xfb" + b"\x00" * 8,
        b"\xff\xf3" + b"\x00" * 8,
        b"OggS" + b"\x00" * 8,
        b"fLaC" + b"\x00" * 8,
    ],
)
def test_tts_owui_200_accepts_audio_magic(
    blob: bytes, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[tuple[int | None, str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.url.port,
                request.headers.get("authorization", ""),
                json.loads(request.content),
            )
        )
        return httpx.Response(200, content=blob)

    monkeypatch.setattr(rn.httpx, "Client", _client_factory(httpx.MockTransport(handler)))
    result = _run_tts(tmp_path)
    assert result.status is Status.PASS, result.detail
    assert seen == [(8080, "Bearer qat-token", TTS_SPEECH_BODY)]
    assert "/api/v1/audio/speech" in result.detail


def test_tts_falls_back_to_mcp_when_owui_is_not_audio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[int | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.port)
        if request.url.port == 8080:
            return httpx.Response(200, content=b"<html>not audio</html>")
        assert json.loads(request.content) == TTS_SPEECH_BODY
        assert not request.headers.get("authorization")
        return httpx.Response(200, content=b"ID3" + b"\x00" * 4)

    monkeypatch.setattr(rn.httpx, "Client", _client_factory(httpx.MockTransport(handler)))
    result = _run_tts(tmp_path)
    assert result.status is Status.PASS, result.detail
    assert seen == [8080, 8916]
    assert ":8916" in result.detail or "8916" in result.detail


@pytest.mark.parametrize("blob", [b"", b"<html></html>", b"not-audio"])
def test_tts_rejects_empty_html_and_non_audio(
    blob: bytes, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=blob)

    monkeypatch.setattr(rn.httpx, "Client", _client_factory(httpx.MockTransport(handler)))
    result = _run_tts(tmp_path)
    assert result.status is Status.FAIL
    assert "empty audio" in result.detail or "not audio magic" in result.detail


def _run_tts(tmp_path: Path) -> rn.QATResult:
    settings = make_settings(tmp_path, OWUI_API_KEY="qat-token")
    scenario = _by_id()["s2-p6-auto-audio-tts"]
    assert scenario.kind == "tts"
    assert scenario.prompts == (TTS_SPEECH_BODY["input"],)
    state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
    return rn._execute_one(settings, scenario, state, _chat_opts())
