#!/usr/bin/env python3
"""
Register a trainer-voice profile with the host MLX speech server (voice clone).

Cleans a raw recording (downmix to mono, trim leading/trailing silence, optional
[start, start+duration] window, peak-normalise) and POSTs it to the speech server's
POST /v1/voices endpoint. The clone engine only consults the first ~10-15s of the
reference, so a tight, expressive 12-15s clip beats a long flat one.

Accepts wav/flac/ogg/mp3 directly; m4a/aac/mov are converted via ffmpeg first.

    python scripts/register_trainer_voice.py \
        --audio ~/chris-ref-2.wav --name chris \
        --text "Okay, here's the plan for this walkthrough. ..." \
        --test

Env: MLX_SPEECH_URL (default http://localhost:8918).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf

SPEECH_URL = os.getenv("MLX_SPEECH_URL", "http://localhost:8918").rstrip("/")
_FFMPEG_EXT = {".m4a", ".aac", ".mov", ".mp4", ".caf", ".aiff", ".aif"}


def _load_audio(path: Path) -> tuple[np.ndarray, int]:
    """Return (mono float32, sr). Falls back to ffmpeg for containers libsndfile can't read."""
    if path.suffix.lower() in _FFMPEG_EXT:
        if not shutil.which("ffmpeg"):
            sys.exit(f"{path.suffix} needs ffmpeg on PATH (brew install ffmpeg) or supply a WAV.")
        tmp = Path(tempfile.mkdtemp()) / "conv.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-ac", "1", "-c:a", "pcm_s16le", str(tmp)],
            check=True,
            capture_output=True,
        )
        path = tmp
    audio, sr = sf.read(str(path))
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio.astype(np.float32), sr


def _trim_silence(audio: np.ndarray, sr: int, thresh_db: float = -40.0) -> np.ndarray:
    """Drop leading/trailing samples below thresh_db relative to peak."""
    if not len(audio):
        return audio
    peak = float(np.max(np.abs(audio))) or 1.0
    gate = peak * (10.0 ** (thresh_db / 20.0))
    win = max(1, sr // 100)  # 10ms RMS window
    energy = np.convolve(np.abs(audio), np.ones(win) / win, mode="same")
    voiced = np.where(energy > gate)[0]
    if not len(voiced):
        return audio
    pad = sr // 20  # keep 50ms on each side
    return audio[max(0, voiced[0] - pad) : min(len(audio), voiced[-1] + pad)]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--audio", required=True, type=Path, help="Raw recording (wav/flac/mp3/m4a/...)"
    )
    ap.add_argument("--name", required=True, help="Profile name (lowercase, digits, _ or -)")
    ap.add_argument("--text", required=True, help="Exact transcript of the clip that will be used")
    ap.add_argument("--start", type=float, default=0.0, help="Seconds to skip from the start")
    ap.add_argument("--duration", type=float, default=18.0, help="Max seconds to keep (default 18)")
    ap.add_argument("--no-trim", action="store_true", help="Skip silence trimming")
    ap.add_argument(
        "--speech-url", default=SPEECH_URL, help=f"Speech server (default {SPEECH_URL})"
    )
    ap.add_argument("--test", action="store_true", help="Generate a test clone after registering")
    ap.add_argument("--keep", action="store_true", help="Keep the cleaned WAV next to the source")
    args = ap.parse_args()

    if not args.audio.exists():
        sys.exit(f"Not found: {args.audio}")

    audio, sr = _load_audio(args.audio)
    if args.start:
        audio = audio[int(args.start * sr) :]
    if not args.no_trim:
        audio = _trim_silence(audio, sr)
    audio = audio[: int(args.duration * sr)]
    dur = len(audio) / sr
    if dur < 5.0:
        sys.exit(f"Cleaned clip is {dur:.1f}s; need >=5s (10-15s of clean speech is ideal).")
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = (audio / peak) * 0.89  # ~ -1 dBFS

    out = (
        args.audio.with_name(f"{args.name}_ref_clean.wav")
        if args.keep
        else Path(tempfile.mkdtemp()) / f"{args.name}_ref_clean.wav"
    )
    sf.write(str(out), audio, sr)
    print(f"cleaned reference: {dur:.1f}s @ {sr} Hz -> {out}")
    if dur > 16:
        print("  note: the clone engine only uses the first ~10-15s of the reference.")

    url = f"{args.speech_url.rstrip('/')}/v1/voices"
    r = httpx.post(
        url,
        json={
            "name": args.name,
            "reference_audio": str(out.resolve()),
            "reference_text": args.text,
        },
        timeout=60,
    )
    print(f"register: HTTP {r.status_code}  {r.text}")
    if r.status_code != 200:
        return 1

    if args.test:
        sentence = (
            "This is a Portal 5 training session. In this module we cover detection, "
            "containment, and recovery, with a short exercise at the end."
        )
        tr = httpx.post(
            f"{args.speech_url.rstrip('/')}/v1/audio/speech",
            json={"input": sentence, "voice": f"trainer:{args.name}"},
            timeout=180,
        )
        if tr.status_code == 200:
            tp = Path(tempfile.gettempdir()) / f"clone_{args.name}_test.wav"
            tp.write_bytes(tr.content)
            print(f"test clone: {tp}")
        else:
            print(f"test clone failed: HTTP {tr.status_code} {tr.text[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
