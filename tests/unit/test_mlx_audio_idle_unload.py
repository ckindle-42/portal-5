"""TASK F4: idle MLX audio models unload; the next use lazy-loads again.

No MLX, no audio: loaders are stubbed in sys.modules, loaded models are fakes,
and the idle clock is driven by writing old last-use stamps directly.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import os
import sys
import time
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SPEECH = REPO / "scripts" / "mlx-speech.py"
TRANSCRIBE = REPO / "scripts" / "mlx-transcribe.py"
CACHE = REPO / "scripts" / "mlx_cache.py"

_cache_spec = importlib.util.spec_from_file_location("mlx_cache", CACHE)
assert _cache_spec is not None and _cache_spec.loader is not None
mlx_cache = importlib.util.module_from_spec(_cache_spec)
sys.modules["mlx_cache"] = mlx_cache
_cache_spec.loader.exec_module(mlx_cache)


class _Rec:
    def __init__(self) -> None:
        self.cleared = 0

    def clear_cache(self) -> None:
        self.cleared += 1


class _FakeModel:
    def __init__(self, name: str) -> None:
        self.name = name


def _load(name: str, path: Path, env: dict[str, str]) -> types.ModuleType:
    saved = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return mod


def _speech_env(root: Path, extra: dict[str, str]) -> dict[str, str]:
    env = {"AI_OUTPUT_DIR": str(root / "out"), "VOICE_PROFILES_DIR": str(root / "voices")}
    env.update(extra)
    return env


@pytest.fixture(scope="module")
def speech(tmp_path_factory: pytest.TempPathFactory) -> types.ModuleType:
    root = tmp_path_factory.mktemp("speech-idle")
    return _load("mlx_speech_idle_test", SPEECH, _speech_env(root, {}))


@pytest.fixture(scope="module")
def speech_disabled(tmp_path_factory: pytest.TempPathFactory) -> types.ModuleType:
    root = tmp_path_factory.mktemp("speech-idle-off")
    return _load(
        "mlx_speech_idle_off_test", SPEECH, _speech_env(root, {"MLX_AUDIO_IDLE_UNLOAD_S": "0"})
    )


@pytest.fixture(scope="module")
def transcribe() -> types.ModuleType:
    return _load("mlx_transcribe_idle_test", TRANSCRIBE, {})


@pytest.fixture(scope="module")
def transcribe_disabled() -> types.ModuleType:
    return _load("mlx_transcribe_idle_off_test", TRANSCRIBE, {"MLX_AUDIO_IDLE_UNLOAD_S": "0"})


@pytest.fixture(autouse=True)
def _reset_state(
    speech: types.ModuleType,
    speech_disabled: types.ModuleType,
    transcribe: types.ModuleType,
    transcribe_disabled: types.ModuleType,
):
    yield
    for mod in (speech, speech_disabled):
        mod._tts_models.clear()
        mod._asr_model = None
        mod._clone_model = None
        mod._model_last_used.clear()
    for mod in (transcribe, transcribe_disabled):
        mod._parakeet_model = None
        mod._diarizer_model = None
        mod._model_last_used.clear()


@pytest.fixture
def fake_mx(monkeypatch: pytest.MonkeyPatch) -> _Rec:
    mx = _Rec()
    monkeypatch.setitem(sys.modules, "mlx.core", mx)
    return mx


def _age_out(mod: types.ModuleType, name: str) -> None:
    mod._model_last_used[name] = time.monotonic() - mod.MLX_AUDIO_IDLE_UNLOAD_S - 5.0


def _stub_speech_loaders(monkeypatch: pytest.MonkeyPatch, loads: list[str]) -> None:
    def _loader(loads: list[str]):
        def _load_model(model_id: str) -> _FakeModel:
            loads.append(model_id)
            return _FakeModel(model_id)

        return _load_model

    monkeypatch.setitem(sys.modules, "mlx_audio", types.ModuleType("mlx_audio"))
    monkeypatch.setitem(sys.modules, "mlx_audio.tts", types.ModuleType("mlx_audio.tts"))
    tts_utils = types.ModuleType("mlx_audio.tts.utils")
    tts_utils.load_model = _loader(loads)
    monkeypatch.setitem(sys.modules, "mlx_audio.tts.utils", tts_utils)
    stt = types.ModuleType("mlx_audio.stt")
    stt.load = _loader(loads)
    monkeypatch.setitem(sys.modules, "mlx_audio.stt", stt)


def _stub_transcribe_loaders(monkeypatch: pytest.MonkeyPatch, loads: list[str]) -> None:
    def _load_stt(model_id: str) -> _FakeModel:
        loads.append(model_id)
        return _FakeModel(model_id)

    monkeypatch.setitem(sys.modules, "mlx_audio", types.ModuleType("mlx_audio"))
    monkeypatch.setitem(sys.modules, "mlx_audio.stt", types.ModuleType("mlx_audio.stt"))
    stt_utils = types.ModuleType("mlx_audio.stt.utils")
    stt_utils.load = _load_stt
    monkeypatch.setitem(sys.modules, "mlx_audio.stt.utils", stt_utils)


# ── speech (:8918) ────────────────────────────────────────────────────────────


async def test_speech_unloads_idle_models(
    speech: types.ModuleType, fake_mx: _Rec, monkeypatch: pytest.MonkeyPatch
):
    fresh = _FakeModel("kokoro")
    speech._tts_models["kokoro"] = fresh
    speech._model_last_used["tts:kokoro"] = time.monotonic()
    speech._asr_model = _FakeModel("asr")
    _age_out(speech, "asr")
    collects: list[int] = []
    monkeypatch.setattr(speech.gc, "collect", lambda generation=2: collects.append(generation))
    unloaded = await speech._unload_idle_models()
    assert unloaded == ["asr"]
    assert speech._tts_models == {"kokoro": fresh}
    assert speech._asr_model is None
    assert list(speech._model_last_used) == ["tts:kokoro"]
    assert collects == [2]
    assert fake_mx.cleared == 1


async def test_speech_no_unload_while_a_request_holds_the_lock(
    speech: types.ModuleType, fake_mx: _Rec
):
    asr = _FakeModel("asr")
    speech._asr_model = asr
    _age_out(speech, "asr")
    async with speech._tts_lock:  # a request is mid-flight
        unloader = asyncio.create_task(speech._unload_idle_models())
        await asyncio.sleep(0.05)
        assert speech._asr_model is asr  # nothing dropped mid-request
        assert not unloader.done()
        assert fake_mx.cleared == 0
    assert await unloader == ["asr"]  # it unloads once the lock frees
    assert speech._asr_model is None


async def test_speech_request_use_renews_the_stamp(speech: types.ModuleType):
    asr = _FakeModel("asr")
    speech._asr_model = asr
    _age_out(speech, "asr")
    async with speech._tts_lock:
        speech._touch_model("asr")  # the request got the lock first and used the model
    assert await speech._unload_idle_models() == []
    assert speech._asr_model is asr


async def test_speech_reloads_on_next_use(
    speech: types.ModuleType, monkeypatch: pytest.MonkeyPatch
):
    loads: list[str] = []
    _stub_speech_loaders(monkeypatch, loads)
    first = speech._get_tts_model("Kokoro-test")
    assert loads == ["Kokoro-test"]
    assert speech._tts_models == {"Kokoro-test": first}
    _age_out(speech, "tts:Kokoro-test")
    assert await speech._unload_idle_models() == ["tts:Kokoro-test"]
    assert speech._tts_models == {}
    second = speech._get_tts_model("Kokoro-test")
    assert second is not first
    assert loads == ["Kokoro-test", "Kokoro-test"]


async def test_speech_lifespan_runs_the_idle_check(
    speech: types.ModuleType, fake_mx: _Rec, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(speech, "_IDLE_POLL_S", 0.02)
    speech._asr_model = _FakeModel("asr")
    _age_out(speech, "asr")
    async with speech._lifespan(speech.app):
        for _ in range(100):
            await asyncio.sleep(0.02)
            if speech._asr_model is None:
                break
    assert speech._asr_model is None
    assert fake_mx.cleared == 1


async def test_speech_zero_disables_unload(speech_disabled: types.ModuleType, fake_mx: _Rec):
    assert speech_disabled.MLX_AUDIO_IDLE_UNLOAD_S == 0.0
    asr = _FakeModel("asr")
    speech_disabled._asr_model = asr
    speech_disabled._model_last_used["asr"] = time.monotonic() - 10_000.0
    assert await speech_disabled._unload_idle_models() == []
    assert speech_disabled._asr_model is asr
    assert fake_mx.cleared == 0


async def test_speech_zero_disables_the_background_check(
    speech_disabled: types.ModuleType,
):
    speech_disabled._asr_model = _FakeModel("asr")
    speech_disabled._model_last_used["asr"] = time.monotonic() - 10_000.0
    async with speech_disabled._lifespan(speech_disabled.app):
        await asyncio.sleep(0.05)
        assert speech_disabled._asr_model is not None


async def test_speech_health_reports_loaded_models(speech: types.ModuleType):
    speech._tts_models["Kokoro-test"] = _FakeModel("k")
    speech._asr_model = _FakeModel("asr")
    info = await speech.health()
    assert info["loaded_models"] == ["tts:Kokoro-test", "asr"]
    assert info["idle_unload_s"] == 300.0


# ── transcribe (:8924) ────────────────────────────────────────────────────────


async def test_transcribe_unloads_idle_models(
    transcribe: types.ModuleType, fake_mx: _Rec, monkeypatch: pytest.MonkeyPatch
):
    transcribe._parakeet_model = _FakeModel("parakeet")
    transcribe._diarizer_model = _FakeModel("diarizer")
    _age_out(transcribe, "parakeet")
    _age_out(transcribe, "diarizer")
    collects: list[int] = []
    monkeypatch.setattr(transcribe.gc, "collect", lambda generation=2: collects.append(generation))
    unloaded = await transcribe._unload_idle_models()
    assert sorted(unloaded) == ["diarizer", "parakeet"]
    assert transcribe._parakeet_model is None
    assert transcribe._diarizer_model is None
    assert transcribe._model_last_used == {}
    assert collects == [2]
    assert fake_mx.cleared == 1


async def test_transcribe_no_unload_while_a_request_holds_the_lock(
    transcribe: types.ModuleType, fake_mx: _Rec
):
    parakeet = _FakeModel("parakeet")
    transcribe._parakeet_model = parakeet
    _age_out(transcribe, "parakeet")
    async with transcribe._pipeline_lock:  # a request is mid-flight
        unloader = asyncio.create_task(transcribe._unload_idle_models())
        await asyncio.sleep(0.05)
        assert transcribe._parakeet_model is parakeet  # nothing dropped mid-request
        assert not unloader.done()
        assert fake_mx.cleared == 0
    assert await unloader == ["parakeet"]  # it unloads once the lock frees
    assert transcribe._parakeet_model is None


async def test_transcribe_reloads_on_next_use(
    transcribe: types.ModuleType, monkeypatch: pytest.MonkeyPatch
):
    loads: list[str] = []
    _stub_transcribe_loaders(monkeypatch, loads)
    first = transcribe._get_parakeet()
    assert loads == [transcribe.PARAKEET_MODEL]
    _age_out(transcribe, "parakeet")
    assert await transcribe._unload_idle_models() == ["parakeet"]
    assert transcribe._parakeet_model is None
    second = transcribe._get_parakeet()
    assert second is not first
    assert loads == [transcribe.PARAKEET_MODEL, transcribe.PARAKEET_MODEL]


async def test_transcribe_idle_loop_unloads(
    transcribe: types.ModuleType, fake_mx: _Rec, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(transcribe, "_IDLE_POLL_S", 0.02)
    transcribe._diarizer_model = _FakeModel("diarizer")
    _age_out(transcribe, "diarizer")
    loop_task = asyncio.create_task(transcribe._idle_unload_loop())
    try:
        for _ in range(100):
            await asyncio.sleep(0.02)
            if transcribe._diarizer_model is None:
                break
        assert transcribe._diarizer_model is None
        assert fake_mx.cleared == 1
    finally:
        loop_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await loop_task


async def test_transcribe_zero_disables_unload(
    transcribe_disabled: types.ModuleType, fake_mx: _Rec
):
    assert transcribe_disabled.MLX_AUDIO_IDLE_UNLOAD_S == 0.0
    parakeet = _FakeModel("parakeet")
    transcribe_disabled._parakeet_model = parakeet
    transcribe_disabled._model_last_used["parakeet"] = time.monotonic() - 10_000.0
    assert await transcribe_disabled._unload_idle_models() == []
    assert transcribe_disabled._parakeet_model is parakeet
    assert fake_mx.cleared == 0


async def test_transcribe_health_reports_loaded_models(transcribe: types.ModuleType):
    transcribe._parakeet_model = _FakeModel("parakeet")
    resp = await transcribe.health()
    info = json.loads(resp.body)
    assert info["loaded_models"] == ["parakeet"]
    assert info["idle_unload_s"] == 300.0
