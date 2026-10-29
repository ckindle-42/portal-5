"""POST_EG2 F4: MLX free-cache cap and per-request release.

A fake mlx.core stands in for the installed package. Model weights are never
touched — release only calls the cache API.
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import os
import sys
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

_LOG = logging.getLogger("test.mlx_cache")


class _Rec:
    def __init__(self) -> None:
        self.cleared = 0
        self.limits: list[int] = []

    def clear_cache(self) -> None:
        self.cleared += 1

    def set_cache_limit(self, nbytes: int) -> int:
        self.limits.append(nbytes)
        return 0


class _Body:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def json(self) -> dict:
        return self._payload


class _Upload:
    filename = "clip.wav"

    async def read(self) -> bytes:
        return b"not-audio"


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


@pytest.fixture(autouse=True)
def _reset_notes():
    mlx_cache._noted.clear()
    yield
    mlx_cache._noted.clear()


@pytest.fixture
def fake_mx(monkeypatch: pytest.MonkeyPatch) -> _Rec:
    mx = _Rec()
    monkeypatch.setitem(sys.modules, "mlx.core", mx)
    return mx


@pytest.fixture(scope="module")
def speech(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("speech-out")
    return _load(
        "mlx_speech_cache_test",
        SPEECH,
        {
            "AI_OUTPUT_DIR": str(root / "out"),
            "VOICE_PROFILES_DIR": str(root / "voices"),
        },
    )


@pytest.fixture(scope="module")
def transcribe():
    return _load("mlx_transcribe_cache_test", TRANSCRIBE, {})


def _gib(n: float) -> int:
    return int(n * 1024**3)


def test_limit_comes_from_env(monkeypatch: pytest.MonkeyPatch, fake_mx: _Rec):
    monkeypatch.setenv("MLX_SPEECH_CACHE_LIMIT_GB", "3")
    mlx_cache.apply_cache_limit("MLX_SPEECH_CACHE_LIMIT_GB", _LOG)
    assert fake_mx.limits == [_gib(3)]


def test_limit_default_when_env_unset(monkeypatch: pytest.MonkeyPatch, fake_mx: _Rec):
    monkeypatch.delenv("MLX_TRANSCRIBE_CACHE_LIMIT_GB", raising=False)
    mlx_cache.apply_cache_limit("MLX_TRANSCRIBE_CACHE_LIMIT_GB", _LOG)
    assert fake_mx.limits == [_gib(mlx_cache.DEFAULT_LIMIT_GB)]


def test_zero_leaves_the_limit_unlimited(monkeypatch: pytest.MonkeyPatch, fake_mx: _Rec, caplog):
    monkeypatch.setenv("MLX_SPEECH_CACHE_LIMIT_GB", "0")
    caplog.set_level(logging.INFO, logger=_LOG.name)
    mlx_cache.apply_cache_limit("MLX_SPEECH_CACHE_LIMIT_GB", _LOG)
    assert fake_mx.limits == []
    assert "unlimited" in caplog.text


def test_top_level_api_wins_over_metal(monkeypatch: pytest.MonkeyPatch):
    top = _Rec()
    metal = _Rec()
    mx = types.SimpleNamespace(
        clear_cache=top.clear_cache,
        set_cache_limit=top.set_cache_limit,
        metal=metal,
    )
    monkeypatch.setitem(sys.modules, "mlx.core", mx)
    monkeypatch.setenv("MLX_SPEECH_CACHE_LIMIT_GB", "1")
    mlx_cache.apply_cache_limit("MLX_SPEECH_CACHE_LIMIT_GB", _LOG)
    mlx_cache.release_cache(_LOG)
    assert top.limits == [_gib(1)]
    assert top.cleared == 1
    assert metal.limits == []
    assert metal.cleared == 0


def test_metal_fallback_when_top_level_api_is_absent(monkeypatch: pytest.MonkeyPatch):
    metal = _Rec()
    mx = types.SimpleNamespace(metal=metal)
    monkeypatch.setitem(sys.modules, "mlx.core", mx)
    monkeypatch.setenv("MLX_TRANSCRIBE_CACHE_LIMIT_GB", "1.5")
    mlx_cache.apply_cache_limit("MLX_TRANSCRIBE_CACHE_LIMIT_GB", _LOG)
    mlx_cache.release_cache(_LOG)
    assert metal.limits == [_gib(1.5)]
    assert metal.cleared == 1


def test_missing_api_is_a_logged_noop(monkeypatch: pytest.MonkeyPatch, caplog):
    monkeypatch.setitem(
        sys.modules, "mlx.core", types.SimpleNamespace(metal=types.SimpleNamespace())
    )
    monkeypatch.setenv("MLX_SPEECH_CACHE_LIMIT_GB", "2")
    caplog.set_level(logging.INFO, logger=_LOG.name)
    mlx_cache.apply_cache_limit("MLX_SPEECH_CACHE_LIMIT_GB", _LOG)
    mlx_cache.release_cache(_LOG)
    mlx_cache.release_cache(_LOG)
    assert "no set_cache_limit" in caplog.text
    assert "no clear_cache" in caplog.text
    assert caplog.text.count("cache release is a no-op") == 1


def test_missing_mlx_is_a_logged_noop(monkeypatch: pytest.MonkeyPatch, caplog):
    import builtins

    monkeypatch.delitem(sys.modules, "mlx.core", raising=False)
    real_import = builtins.__import__

    def _blocked(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "mlx" or name.startswith("mlx."):
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    caplog.set_level(logging.INFO, logger=_LOG.name)
    mlx_cache.apply_cache_limit("MLX_SPEECH_CACHE_LIMIT_GB", _LOG)
    mlx_cache.release_cache(_LOG)
    assert "not installed" in caplog.text
    assert "no-op" in caplog.text


def test_clear_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch, caplog):
    def _boom() -> None:
        raise RuntimeError("metal")

    monkeypatch.setitem(sys.modules, "mlx.core", types.SimpleNamespace(clear_cache=_boom))
    caplog.set_level(logging.WARNING, logger=_LOG.name)
    mlx_cache.release_cache(_LOG)
    assert "cache release failed" in caplog.text


def _main_applies(path: Path, env_var: str) -> bool:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
        ):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call) or not isinstance(sub.func, ast.Attribute):
                continue
            if sub.func.attr != "apply_cache_limit" or not sub.args:
                continue
            arg = sub.args[0]
            if isinstance(arg, ast.Constant) and arg.value == env_var:
                return True
    return False


def test_startup_applies_the_service_limit():
    assert _main_applies(SPEECH, "MLX_SPEECH_CACHE_LIMIT_GB")
    assert _main_applies(TRANSCRIBE, "MLX_TRANSCRIBE_CACHE_LIMIT_GB")


async def test_speech_clears_after_success(speech, fake_mx: _Rec, tmp_path: Path, monkeypatch):
    wav = tmp_path / "out.wav"
    wav.write_bytes(b"RIFF")

    def _ok(*_a, **_k):
        return {"status": "success", "file_path": str(wav)}

    monkeypatch.setattr(speech, "_generate_speech", _ok)
    resp = await speech.openai_audio_speech(_Body({"input": "hello", "voice": "af_heart"}))
    assert resp.status_code == 200
    assert fake_mx.cleared == 1


async def test_speech_clears_after_exception(speech, fake_mx: _Rec, monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("gpu")

    monkeypatch.setattr(speech, "_generate_speech", _boom)
    resp = await speech.openai_audio_speech(_Body({"input": "hello", "voice": "af_heart"}))
    assert resp.status_code == 500
    assert fake_mx.cleared == 1


async def test_speech_asr_clears_after_success_and_exception(speech, fake_mx: _Rec, monkeypatch):
    monkeypatch.setattr(speech, "_transcribe", lambda *_a, **_k: {"text": "hi"})
    ok = await speech.openai_audio_transcriptions(_Upload(), language="auto")
    assert ok.status_code == 200
    assert fake_mx.cleared == 1

    def _boom(*_a, **_k):
        raise RuntimeError("asr")

    monkeypatch.setattr(speech, "_transcribe", _boom)
    bad = await speech.openai_audio_transcriptions(_Upload(), language="auto")
    assert bad.status_code == 500
    assert fake_mx.cleared == 2


async def test_transcribe_tool_clears_after_success_and_exception(
    transcribe, fake_mx: _Rec, tmp_path: Path, monkeypatch
):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"wav")
    monkeypatch.setattr(transcribe, "_run_plain_pipeline", lambda *_a, **_k: {"text": "hi"})
    ok = await transcribe._dispatch_tool("transcribe_audio", {"file": str(audio)})
    assert ok.status_code == 200
    assert fake_mx.cleared == 1

    def _boom(*_a, **_k):
        raise RuntimeError("oom")

    monkeypatch.setattr(transcribe, "_run_plain_pipeline", _boom)
    bad = await transcribe._dispatch_tool("transcribe_audio", {"file": str(audio)})
    assert bad.status_code == 500
    assert fake_mx.cleared == 2


async def test_transcribe_mcp_and_http_clear(
    transcribe, fake_mx: _Rec, tmp_path: Path, monkeypatch
):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"wav")
    monkeypatch.setattr(transcribe, "_run_plain_pipeline", lambda *_a, **_k: {"text": "hi"})
    monkeypatch.setattr(
        transcribe,
        "_run_pipeline",
        lambda *_a, **_k: {"text": "hi", "segments": []},
    )
    plain = await transcribe.transcribe_audio(file=str(audio))
    speakers = await transcribe.transcribe_with_speakers(file=str(audio))
    http = await transcribe.http_transcribe(_Upload(), language="auto", num_speakers=None)
    assert plain["engine"] == "parakeet-tdt-v3"
    assert speakers["engine"] == "parakeet+sortformer"
    assert http.status_code == 200
    assert fake_mx.cleared == 3
