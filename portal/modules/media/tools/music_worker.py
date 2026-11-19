"""One-shot music generation subprocess. Exits so Metal memory returns to the OS."""

from __future__ import annotations

import json
import os
import platform
import sys
import wave
from pathlib import Path
from typing import Any

_TASK_OK = frozenset({"text2music", "repaint", "cover", "complete"})


def write_wav(path: str, audio: Any, sample_rate: int) -> None:
    """Write a stereo 16-bit WAV. Accepts a numpy array or anything array-like."""
    import numpy as np

    arr = np.asarray(audio, dtype="float32")
    if arr.ndim == 1:
        arr = np.stack([arr, arr], axis=1)
    elif arr.shape[0] in (1, 2) and arr.shape[-1] not in (1, 2):
        arr = arr.T
    if arr.shape[-1] == 1:
        arr = np.repeat(arr, 2, axis=1)
    pcm = np.round(np.clip(arr[:, :2], -1.0, 1.0) * 32_767).astype("<i2")
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm.tobytes())


def _instrumental(lyrics: str) -> bool:
    return lyrics.strip().lower() in {"", "[instrumental]"}


def _release_device() -> None:
    import gc

    gc.collect()
    try:
        import mlx.core as mx
    except ImportError:
        return
    metal = getattr(mx, "metal", None)
    clear = getattr(mx, "clear_cache", None) or getattr(metal, "clear_cache", None)
    if callable(clear):
        clear()


def _acestep(spec: dict[str, Any]) -> dict[str, Any]:
    from acestep.handler import AceStepHandler  # type: ignore[import-not-found]
    from acestep.inference import (  # type: ignore[import-not-found]
        GenerationConfig,
        GenerationParams,
        generate_music,
    )
    from acestep.llm_inference import LLMHandler  # type: ignore[import-not-found]

    root = Path(os.environ.get("MUSIC_ACE_ROOT", Path.home() / ".portal5/music/ACE-Step-1.5"))
    dit_name = os.environ.get("MUSIC_ACE_DIT", "acestep-v15-xl-turbo")
    dit = AceStepHandler()
    status, ok = dit.initialize_service(
        project_root=str(root),
        config_path=dit_name,
        device="auto",
        use_mlx_dit=True,
        offload_to_cpu=os.environ.get("MUSIC_ACE_OFFLOAD", "1") not in ("0", "false", "no"),
    )
    if not ok:
        return {"success": False, "error": f"ACE-Step init failed: {status}"}
    lm = LLMHandler()
    lm.initialize(
        checkpoint_dir=str(root / "checkpoints"),
        lm_model_path=os.environ.get("MUSIC_ACE_LM", "acestep-5Hz-lm-1.7B"),
        backend="mlx",
        device="auto",
    )
    seed = int(spec["seed"])
    task = str(spec["upstream_task"])
    params = GenerationParams(
        task_type=task,
        caption=str(spec["prompt"]),
        lyrics=str(spec["lyrics"]),
        duration=float(spec["seconds"]),
        inference_steps=int(spec["steps"]),
        seed=seed,
        shift=3.0,
        src_audio=spec.get("source_path") or None,
        repainting_start=float(spec.get("repaint_start") or 0.0),
        repainting_end=float(spec["repaint_end"]) if spec.get("repaint_end") is not None else -1.0,
        instrumental=_instrumental(str(spec["lyrics"])),
        chunk_mask_mode="explicit" if task == "repaint" else "auto",
    )
    config = GenerationConfig(batch_size=1, use_random_seed=False, seeds=[seed], audio_format="wav")
    result = generate_music(dit, lm, params, config, save_dir=str(Path(spec["output_path"]).parent))
    if not getattr(result, "success", False):
        return {"success": False, "error": getattr(result, "error", None) or "ACE-Step failed"}
    audios = list(getattr(result, "audios", []) or [])
    if not audios or not audios[0].get("path"):
        return {"success": False, "error": "ACE-Step returned no audio"}
    dest = Path(spec["output_path"])
    produced = Path(audios[0]["path"])
    if produced.resolve() != dest.resolve():
        dest.write_bytes(produced.read_bytes())
    return {
        "success": True,
        "artifact_path": str(dest),
        "sample_rate": int(audios[0].get("sample_rate") or 48_000),
        "model": dit_name,
        "engine": "acestep",
        "seed": seed,
    }


def _minimax(spec: dict[str, Any]) -> dict[str, Any]:
    from mlx_audio.music import load  # type: ignore[import-untyped]

    model_id = os.environ.get("MUSIC_MINIMAX_MODEL", "mlx-community/MiniMax-Music3-8bit")
    model = load(model_id)
    lyrics = str(spec["lyrics"]).strip() or "[instrumental]"
    result = next(
        model.generate(
            text=str(spec["prompt"]),
            lyrics=lyrics,
            duration=float(spec["seconds"]),
            steps=int(spec["steps"]),
            seed=int(spec["seed"]),
        )
    )
    rate = int(getattr(result, "sample_rate", 44_100))
    write_wav(str(spec["output_path"]), result.audio, rate)
    return {
        "success": True,
        "artifact_path": str(spec["output_path"]),
        "sample_rate": rate,
        "model": model_id,
        "engine": "minimax",
        "seed": int(spec["seed"]),
    }


def generate(spec: dict[str, Any]) -> dict[str, Any]:
    """Run one engine job and always clear the device cache before returning."""
    if platform.machine() != "arm64":
        return {"success": False, "error": f"music engines require arm64, not {platform.machine()}"}
    task = str(spec.get("upstream_task") or "")
    if task not in _TASK_OK:
        return {"success": False, "error": f"unsupported task {task!r}"}
    engine = str(spec.get("engine") or "")
    try:
        if engine == "acestep":
            return _acestep(spec)
        if engine == "minimax":
            return _minimax(spec)
        return {"success": False, "error": f"unknown engine {engine!r}"}
    except Exception as exc:  # noqa: BLE001 — worker boundary: the parent only sees JSON
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"[:800]}
    finally:
        _release_device()


def main() -> int:
    """Read one JSON job on stdin and write one JSON result on stdout."""
    spec = json.loads(sys.stdin.read() or "{}")
    result = generate(spec if isinstance(spec, dict) else {})
    sys.stdout.write(json.dumps(result))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
