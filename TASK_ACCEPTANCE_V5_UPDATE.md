# TASK_ACCEPTANCE_V5_UPDATE.md — Acceptance Test Updates for Frontier Models + Speech Pipeline
# Coding Agent Execution File

**Version**: 1.0  
**Date**: April 9, 2026  
**Scope**: Update `portal5_acceptance_v4.py` to test embedding service, reranker, GLM-OCR, GLM-5.1, and MLX speech pipeline  
**Depends on**: TASK_FRONTIER_MODELS.md and TASK_SPEECH_PIPELINE_UPGRADE.md (execute those first)

---

## Pre-Flight

```bash
# Clone fresh
git clone https://github.com/ckindle-42/portal-5.git && cd portal-5

# Read before writing
cat CLAUDE.md
head -350 portal5_acceptance_v4.py   # Read header + changelog + conventions
grep -n "^# S[0-9]" portal5_acceptance_v4.py  # Section map
grep -n "SECTIONS =" portal5_acceptance_v4.py  # Registry
grep -n "ALL_ORDER" portal5_acceptance_v4.py   # Execution order
grep -n "MCP =" portal5_acceptance_v4.py       # Port config
```

---

## Scope Boundaries

### IN SCOPE — new tests to add
1. **S1 additions**: Static config checks for new models (GLM-5.1 in backends.yaml, GLM-5.1 in MODEL_MEMORY, embedding service in docker-compose, reranker config)
2. **S2 additions**: Health checks for embedding service (:8917) and MLX speech server (:8918)
3. **S8 rewrite**: TTS tests updated to target MLX speech server (:8918), test Kokoro backward compat + Qwen3-TTS CustomVoice + VoiceDesign
4. **S9 rewrite**: ASR tests updated to target MLX speech server (:8918), Qwen3-ASR round-trip
5. **S24 (NEW)**: RAG embedding pipeline validation — test embedding endpoint, reranker config, document ingest round-trip
6. **S38 (NEW)**: GLM-5.1 MLX HEAVY model test (same pattern as S30-S37 model-grouped sections)
7. **S16 additions**: CLI command checks for `start-speech` / `stop-speech` in launch.sh

### OUT OF SCOPE
- No changes to existing MLX model-grouped tests (S30-S37)
- No changes to workspace routing tests (S3) — no workspace routing was modified
- No changes to persona tests (S11) — no personas were modified

### CONVENTIONS (from existing test suite)
- Use `record(section, tid, name, status, detail, evidence, fix, t0)` for all assertions
- Status values: PASS, FAIL, WARN, BLOCKED, INFO
- Sleep delays: 1s between sequential requests, 2s between workspace switches, 3s between heavy switches
- Signal-driven checks preferred over blind waits
- Async throughout — `async def` for all section functions
- `httpx.AsyncClient` for HTTP calls

---

## File Modification Summary

| # | File | Action | Description |
|---|------|--------|-------------|
| 1 | `portal5_acceptance_v4.py` | EDIT | Add port configs, new section functions, update S8/S9, register sections |

This is a single-file edit (the test suite is one monolithic file). All changes go into `portal5_acceptance_v4.py`.

---

## Implementation

### 1. Add port configs and URL constants

**Find** the MCP port dictionary (around line 380):

```python
MCP = {
    "documents": int(os.environ.get("DOCUMENTS_HOST_PORT", "8913")),
    "music": int(os.environ.get("MUSIC_HOST_PORT", "8912")),
    "tts": int(os.environ.get("TTS_HOST_PORT", "8916")),
    "whisper": int(os.environ.get("WHISPER_HOST_PORT", "8915")),
    "sandbox": int(os.environ.get("SANDBOX_HOST_PORT", "8914")),
    "video": int(os.environ.get("VIDEO_MCP_HOST_PORT", "8911")),
}
```

**Replace with:**

```python
MCP = {
    "documents": int(os.environ.get("DOCUMENTS_HOST_PORT", "8913")),
    "music": int(os.environ.get("MUSIC_HOST_PORT", "8912")),
    "tts": int(os.environ.get("TTS_HOST_PORT", "8916")),
    "whisper": int(os.environ.get("WHISPER_HOST_PORT", "8915")),
    "sandbox": int(os.environ.get("SANDBOX_HOST_PORT", "8914")),
    "video": int(os.environ.get("VIDEO_MCP_HOST_PORT", "8911")),
    "embedding": int(os.environ.get("EMBEDDING_HOST_PORT", "8917")),
}

# MLX Speech server (host-native, replaces Docker TTS/ASR on Apple Silicon)
MLX_SPEECH_PORT = int(os.environ.get("MLX_SPEECH_PORT", "8918"))
MLX_SPEECH_URL = f"http://localhost:{MLX_SPEECH_PORT}"
```

---

### 2. Add changelog entry

**Find** the docstring header (top of file, inside the triple-quote block). Find the last `Changes from v4` block and **add after** the last changelog entry:

```python
Changes from v5 (this run):
    - S1-12/13/14/15: Static config checks for embedding service, reranker, GLM-5.1,
      GLM-OCR, and MLX speech server additions from TASK_FRONTIER_MODELS + TASK_SPEECH_PIPELINE
    - S2-17/18: Health checks for portal5-embedding (:8917) and mlx-speech (:8918)
    - S8: Rewritten for MLX speech server (:8918). Tests Kokoro backward compat,
      Qwen3-TTS CustomVoice (preset speakers), VoiceDesign (text description → voice).
      Falls back to Docker mcp-tts (:8916) if MLX speech not running.
    - S9: Rewritten for Qwen3-ASR via MLX speech server (:8918). Round-trip: TTS → WAV → ASR.
      Falls back to Docker mcp-whisper (:8915) if MLX speech not running.
    - S24 (NEW): RAG embedding pipeline — embedding endpoint health, vector generation,
      reranker config validation, Open WebUI RAG env var consistency
    - S38 (NEW): GLM-5.1 HEAVY MLX model test — model load, inference, MODEL_MEMORY check
    - S16: Added start-speech/stop-speech CLI command checks
```

---

### 3. S1 additions — Static config checks for new models

**Find** the end of the `S1()` function (the last `record(sec, ...)` call before `S2`). **Add before** the closing of `S1`:

```python
    # ── S1-12: Embedding service in docker-compose ────────────────────────────
    t0 = time.time()
    dc_src = (ROOT / "deploy/portal-5/docker-compose.yml").read_text()
    has_embed_svc = "portal5-embedding" in dc_src
    has_harrier = "harrier-oss-v1-0.6b" in dc_src
    has_rag_openai = "RAG_EMBEDDING_ENGINE=openai" in dc_src
    has_reranker = "bge-reranker-v2-m3" in dc_src
    all_ok = has_embed_svc and has_harrier and has_rag_openai and has_reranker
    record(
        sec,
        "S1-12",
        "docker-compose: embedding service + RAG config (Harrier + bge-reranker)",
        "PASS" if all_ok else "FAIL",
        "✓ portal5-embedding service, Harrier model, RAG_EMBEDDING_ENGINE=openai, reranker configured"
        if all_ok
        else f"svc={has_embed_svc} harrier={has_harrier} rag_openai={has_rag_openai} reranker={has_reranker}",
        t0=t0,
    )

    # ── S1-13: GLM-5.1 in backends.yaml ──────────────────────────────────────
    t0 = time.time()
    backends_src = (ROOT / "config/backends.yaml").read_text()
    has_glm51 = "GLM-5.1" in backends_src
    record(
        sec,
        "S1-13",
        "backends.yaml contains GLM-5.1 model entry",
        "PASS" if has_glm51 else "FAIL",
        "✓ GLM-5.1-DQ4plus-q8 in MLX models" if has_glm51 else "GLM-5.1 not found in backends.yaml",
        t0=t0,
    )

    # ── S1-14: GLM-5.1 in MODEL_MEMORY (mlx-proxy.py) ────────────────────────
    t0 = time.time()
    has_glm51_mem = "GLM-5.1-DQ4plus-q8" in proxy_src
    record(
        sec,
        "S1-14",
        "mlx-proxy.py MODEL_MEMORY includes GLM-5.1",
        "PASS" if has_glm51_mem else "FAIL",
        "✓ admission control entry present" if has_glm51_mem else "GLM-5.1 not in MODEL_MEMORY",
        t0=t0,
    )

    # ── S1-15: MLX speech server script exists ────────────────────────────────
    t0 = time.time()
    speech_script = ROOT / "scripts/mlx-speech.py"
    has_speech = speech_script.exists()
    has_qwen3_tts = has_speech and "Qwen3-TTS" in speech_script.read_text()
    has_qwen3_asr = has_speech and "Qwen3-ASR" in speech_script.read_text()
    record(
        sec,
        "S1-15",
        "scripts/mlx-speech.py exists with Qwen3-TTS + Qwen3-ASR",
        "PASS" if has_speech and has_qwen3_tts and has_qwen3_asr else "FAIL",
        "✓ speech server with TTS + ASR backends"
        if has_speech and has_qwen3_tts and has_qwen3_asr
        else f"exists={has_speech} tts={has_qwen3_tts} asr={has_qwen3_asr}",
        t0=t0,
    )

    # ── S1-16: GLM-OCR in MLX pull list (launch.sh) ──────────────────────────
    t0 = time.time()
    launch_src = (ROOT / "launch.sh").read_text()
    has_glm_ocr = "GLM-OCR" in launch_src
    has_glm51_launch = "GLM-5.1" in launch_src
    has_speech_cmd = "start-speech" in launch_src and "stop-speech" in launch_src
    has_speech_models = "Qwen3-TTS" in launch_src and "Qwen3-ASR" in launch_src
    record(
        sec,
        "S1-16",
        "launch.sh: GLM-OCR, GLM-5.1, speech commands, speech models in pull list",
        "PASS" if has_glm_ocr and has_glm51_launch and has_speech_cmd and has_speech_models else "FAIL",
        f"ocr={has_glm_ocr} glm51={has_glm51_launch} speech_cmd={has_speech_cmd} speech_models={has_speech_models}",
        t0=t0,
    )
```

---

### 4. S2 additions — Health checks for new services

**Find** the end of `S2()` (after the last `record(sec, ...)` call, before `S3`). **Add:**

```python
    # ── S2-17: Embedding service health ───────────────────────────────────────
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"http://localhost:{MCP['embedding']}/health")
            record(
                sec,
                "S2-17",
                "Embedding service (portal5-embedding :8917)",
                "PASS" if r.status_code == 200 else "WARN",
                f"HTTP {r.status_code}" if r.status_code != 200 else "✓ Harrier-0.6B serving",
                t0=t0,
            )
    except Exception as e:
        record(
            sec, "S2-17", "Embedding service (portal5-embedding :8917)",
            "WARN", f"not reachable: {str(e)[:60]} — run: docker compose up portal5-embedding",
            t0=t0,
        )

    # ── S2-18: MLX Speech server health ───────────────────────────────────────
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{MLX_SPEECH_URL}/health")
            if r.status_code == 200:
                data = r.json()
                record(
                    sec,
                    "S2-18",
                    "MLX Speech server (:8918)",
                    "PASS",
                    f"backends={data.get('backends', [])} cloning={data.get('voice_cloning', '?')}",
                    t0=t0,
                )
            else:
                record(sec, "S2-18", "MLX Speech server (:8918)", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception:
        record(
            sec, "S2-18", "MLX Speech server (:8918)",
            "INFO", "not running — run: ./launch.sh start-speech (Apple Silicon only)",
            t0=t0,
        )
```

---

### 5. Rewrite S8 — TTS tests for MLX Speech server

**Find** the entire `S8()` function (from `async def S8():` through to the line before `# S9`). **Replace** the entire function with:

```python
async def S8() -> None:
    """TTS tests — targets MLX speech server (:8918) primary, Docker mcp-tts (:8916) fallback."""
    print("\n━━━ S8. TEXT-TO-SPEECH ━━━")
    sec = "S8"

    # Determine which TTS endpoint to test
    tts_url = MLX_SPEECH_URL
    tts_label = "MLX speech"
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{MLX_SPEECH_URL}/health")
            if r.status_code != 200:
                raise ConnectionError("MLX speech not healthy")
    except Exception:
        tts_url = f"http://localhost:{MCP['tts']}"
        tts_label = "Docker mcp-tts (fallback)"
        record(sec, "S8-00", "MLX speech server check", "INFO",
               f"MLX speech (:8918) not available, falling back to Docker mcp-tts (:{MCP['tts']})")

    record(sec, "S8-00b", "TTS target endpoint", "INFO", f"using {tts_label} at {tts_url}")

    # ── S8-01: List voices endpoint ───────────────────────────────────────────
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{tts_url}/v1/voices")
            if r.status_code == 200:
                body = r.json()
                has_kokoro = "kokoro" in str(body).lower()
                record(
                    sec, "S8-01", "GET /v1/voices includes Kokoro voices",
                    "PASS" if has_kokoro else "WARN",
                    "✓ voices listed" if has_kokoro else f"unexpected: {str(body)[:80]}",
                    t0=t0,
                )
            elif r.status_code == 404:
                # Docker fallback doesn't have /v1/voices — try MCP list_voices tool
                await _mcp(
                    MCP["tts"], "list_voices", {},
                    section=sec, tid="S8-01",
                    name="list_voices includes af_heart (Docker fallback)",
                    ok_fn=lambda t: "af_heart" in t,
                    detail_fn=lambda t: "✓ voices listed (Docker)" if "af_heart" in t else t[:80],
                    timeout=15,
                )
            else:
                record(sec, "S8-01", "List voices", "FAIL", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S8-01", "List voices", "FAIL", str(e)[:80], t0=t0)

    # ── S8-02: Kokoro TTS (backward compatibility) ────────────────────────────
    kokoro_voices = [
        ("af_heart", "US-F default"),
        ("bm_george", "British male"),
        ("am_adam", "US male"),
        ("bf_emma", "British female"),
    ]
    async with httpx.AsyncClient(timeout=60) as c:
        for voice, desc in kokoro_voices:
            t0 = time.time()
            try:
                r = await c.post(
                    f"{tts_url}/v1/audio/speech",
                    json={"input": _TTS_TEXT, "voice": voice, "model": "kokoro"},
                )
                if r.status_code == 200:
                    info = _wav_info(r.content)
                    is_wav = info is not None
                    duration_ok = is_wav and info["duration_s"] >= 1.0
                    record(
                        sec, "S8-02",
                        f"Kokoro TTS: {voice} ({desc})",
                        "PASS" if is_wav and duration_ok else ("WARN" if is_wav else "FAIL"),
                        (
                            f"✓ WAV {len(r.content):,}B {info['duration_s']:.1f}s {info['sample_rate']}Hz"
                            if info else f"not WAV {len(r.content):,}B"
                        ),
                        t0=t0,
                    )
                else:
                    record(sec, "S8-02", f"Kokoro TTS: {voice}", "FAIL", f"HTTP {r.status_code}", t0=t0)
            except Exception as e:
                record(sec, "S8-02", f"Kokoro TTS: {voice}", "FAIL", str(e)[:80], t0=t0)
            await asyncio.sleep(1)

    # ── S8-03: Qwen3-TTS CustomVoice (preset speaker + style) ────────────────
    # Only available on MLX speech server, not Docker fallback
    if "MLX" in tts_label:
        qwen3_voices = [
            ("Chelsie", ""),
            ("Ryan", "Professional news anchor tone."),
            ("Vivian", "Whisper softly."),
        ]
        async with httpx.AsyncClient(timeout=90) as c:
            for speaker, instruct in qwen3_voices:
                t0 = time.time()
                desc = f"{speaker}" + (f" ({instruct[:30]})" if instruct else "")
                try:
                    payload = {"input": "Welcome to Portal Five.", "voice": speaker}
                    if instruct:
                        payload["instruct"] = instruct
                    r = await c.post(f"{tts_url}/v1/audio/speech", json=payload)
                    if r.status_code == 200:
                        info = _wav_info(r.content)
                        is_wav = info is not None
                        record(
                            sec, "S8-03",
                            f"Qwen3-TTS CustomVoice: {desc}",
                            "PASS" if is_wav else "WARN",
                            f"✓ WAV {len(r.content):,}B {info['duration_s']:.1f}s" if info else f"not WAV {len(r.content):,}B",
                            t0=t0,
                        )
                    else:
                        record(sec, "S8-03", f"Qwen3-TTS: {desc}", "FAIL", f"HTTP {r.status_code}", t0=t0)
                except Exception as e:
                    record(sec, "S8-03", f"Qwen3-TTS: {desc}", "FAIL", str(e)[:80], t0=t0)
                await asyncio.sleep(2)  # Qwen3-TTS is heavier, allow cooldown

        # ── S8-04: Qwen3-TTS VoiceDesign (create voice from description) ─────
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(
                    f"{tts_url}/v1/audio/speech",
                    json={
                        "input": "This is a test of voice design.",
                        "voice": "design:A warm male narrator with a calm British accent",
                    },
                )
                if r.status_code == 200:
                    info = _wav_info(r.content)
                    record(
                        sec, "S8-04",
                        "Qwen3-TTS VoiceDesign: text description → generated voice",
                        "PASS" if info else "WARN",
                        f"✓ WAV {len(r.content):,}B {info['duration_s']:.1f}s" if info else f"not WAV {len(r.content):,}B",
                        t0=t0,
                    )
                else:
                    record(sec, "S8-04", "Qwen3-TTS VoiceDesign", "FAIL", f"HTTP {r.status_code}", t0=t0)
        except Exception as e:
            record(sec, "S8-04", "Qwen3-TTS VoiceDesign", "FAIL", str(e)[:80], t0=t0)
    else:
        record(sec, "S8-03", "Qwen3-TTS CustomVoice", "INFO", "skipped — MLX speech not running")
        record(sec, "S8-04", "Qwen3-TTS VoiceDesign", "INFO", "skipped — MLX speech not running")
```

---

### 6. Rewrite S9 — ASR tests for MLX Speech server

**Find** the entire `S9()` function. **Replace** with:

```python
async def S9() -> None:
    """STT tests — targets MLX speech server (:8918) primary, Docker mcp-whisper (:8915) fallback."""
    print("\n━━━ S9. SPEECH-TO-TEXT ━━━")
    sec = "S9"

    # Determine which ASR endpoint to test
    asr_url = MLX_SPEECH_URL
    asr_label = "MLX speech (Qwen3-ASR)"
    tts_url = MLX_SPEECH_URL
    use_mlx = True
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{MLX_SPEECH_URL}/health")
            if r.status_code != 200:
                raise ConnectionError()
    except Exception:
        asr_url = f"http://localhost:{MCP['whisper']}"
        tts_url = f"http://localhost:{MCP['tts']}"
        asr_label = "Docker mcp-whisper (fallback)"
        use_mlx = False
        record(sec, "S9-00", "MLX speech server check", "INFO",
               f"falling back to Docker whisper (:{MCP['whisper']})")

    # ── S9-01: ASR health / reachability ──────────────────────────────────────
    t0 = time.time()
    if use_mlx:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{asr_url}/health")
                record(sec, "S9-01", f"ASR health ({asr_label})", "PASS" if r.status_code == 200 else "FAIL",
                       f"HTTP {r.status_code}", t0=t0)
        except Exception as e:
            record(sec, "S9-01", "ASR health", "FAIL", str(e)[:80], t0=t0)
    else:
        # Docker fallback — use docker exec like the original test
        r = subprocess.run(
            ["docker", "exec", "portal5-mcp-whisper", "python3", "-c",
             "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8915/health').read().decode())"],
            capture_output=True, text=True, timeout=15,
        )
        record(sec, "S9-01", f"ASR health ({asr_label})",
               "PASS" if r.returncode == 0 and "ok" in r.stdout.lower() else "FAIL",
               r.stdout.strip()[:80] or r.stderr.strip()[:80], t0=t0)

    # ── S9-02: ASR endpoint reachable (error response confirms connectivity) ──
    if use_mlx:
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                # Send empty form to trigger a validation error (confirms endpoint exists)
                r = await c.post(f"{asr_url}/v1/audio/transcriptions")
                # Any response (even 4xx) means the endpoint is reachable
                record(sec, "S9-02", "ASR endpoint reachable (/v1/audio/transcriptions)",
                       "PASS", f"HTTP {r.status_code} — endpoint responds", t0=t0)
        except Exception as e:
            record(sec, "S9-02", "ASR endpoint reachable", "FAIL", str(e)[:80], t0=t0)
    else:
        await _mcp(
            MCP["whisper"], "transcribe_audio", {"file_path": "/nonexistent_portal5_test.wav"},
            section=sec, tid="S9-02",
            name="transcribe_audio tool reachable (file-not-found confirms connectivity)",
            ok_fn=lambda t: True,
            detail_fn=lambda t: "✓ tool responds" if any(x in t.lower() for x in ["not found", "error"]) else t[:80],
            timeout=15,
        )

    # ── S9-03: Full round-trip: TTS → WAV → ASR ──────────────────────────────
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            tts_r = await c.post(
                f"{tts_url}/v1/audio/speech",
                json={"input": "Hello from Portal Five.", "voice": "af_heart", "model": "kokoro"},
            )
        if tts_r.status_code == 200 and _is_wav(tts_r.content):
            if use_mlx:
                # MLX path: POST wav bytes directly to /v1/audio/transcriptions
                import io
                wav_bytes = tts_r.content
                async with httpx.AsyncClient(timeout=90) as c:
                    files = {"file": ("roundtrip.wav", io.BytesIO(wav_bytes), "audio/wav")}
                    data = {"language": "English"}
                    asr_r = await c.post(f"{asr_url}/v1/audio/transcriptions", files=files, data=data)
                if asr_r.status_code == 200:
                    text = asr_r.json().get("text", "")
                    has_keywords = any(x in text.lower() for x in ["hello", "portal", "five"])
                    record(sec, "S9-03", "STT round-trip: TTS → WAV → Qwen3-ASR",
                           "PASS" if has_keywords else "WARN",
                           f"transcribed: '{text[:80]}'" if text else "empty transcription", t0=t0)
                else:
                    record(sec, "S9-03", "STT round-trip", "FAIL", f"ASR HTTP {asr_r.status_code}", t0=t0)
            else:
                # Docker fallback: copy WAV into container, call MCP tool
                wav = Path("/tmp/portal5_stt_roundtrip.wav")
                wav.write_bytes(tts_r.content)
                cp = subprocess.run(
                    ["docker", "cp", str(wav), "portal5-mcp-whisper:/tmp/stt_roundtrip.wav"],
                    capture_output=True, text=True,
                )
                if cp.returncode == 0:
                    await _mcp(
                        MCP["whisper"], "transcribe_audio",
                        {"file_path": "/tmp/stt_roundtrip.wav"},
                        section=sec, tid="S9-03",
                        name="STT round-trip: TTS → WAV → Whisper (Docker fallback)",
                        ok_fn=lambda t: any(x in t.lower() for x in ["hello", "portal", "five", "text"]),
                        detail_fn=lambda t: f"✓ transcribed: {t[:80]}" if any(x in t.lower() for x in ["hello", "portal"]) else t[:80],
                        timeout=60,
                    )
                else:
                    record(sec, "S9-03", "STT round-trip", "FAIL", f"docker cp failed: {cp.stderr[:80]}", t0=t0)
        else:
            record(sec, "S9-03", "STT round-trip", "WARN",
                   f"TTS HTTP {tts_r.status_code} or non-WAV — skipping STT", t0=t0)
    except Exception as e:
        record(sec, "S9-03", "STT round-trip", "FAIL", str(e)[:80], t0=t0)
```

---

### 7. NEW SECTION: S24 — RAG Embedding Pipeline

**Add** this new section function before the `# S16` section (or after `S23`). Place it logically with other non-LLM-dependent sections:

```python
# ═══════════════════════════════════════════════════════════════════════════════
# S24 — RAG EMBEDDING PIPELINE (Harrier + bge-reranker)
# ═══════════════════════════════════════════════════════════════════════════════
async def S24() -> None:
    print("\n━━━ S24. RAG EMBEDDING PIPELINE ━━━")
    sec = "S24"

    # ── S24-01: Embedding service health ──────────────────────────────────────
    embed_port = MCP["embedding"]
    t0 = time.time()
    embed_ok = False
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"http://localhost:{embed_port}/health")
            embed_ok = r.status_code == 200
            record(
                sec, "S24-01", "Embedding service health (Harrier-0.6B via TEI)",
                "PASS" if embed_ok else "FAIL",
                f"HTTP {r.status_code}" if not embed_ok else "✓ healthy",
                t0=t0,
            )
    except Exception as e:
        record(sec, "S24-01", "Embedding service health", "FAIL",
               f"not reachable: {str(e)[:60]}", t0=t0)

    # ── S24-02: Generate embeddings (OpenAI-compatible API) ───────────────────
    t0 = time.time()
    if embed_ok:
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(
                    f"http://localhost:{embed_port}/v1/embeddings",
                    json={"input": "NERC CIP compliance requires critical infrastructure protection.", "model": "microsoft/harrier-oss-v1-0.6b"},
                    headers={"Authorization": "Bearer portal-embedding"},
                )
                if r.status_code == 200:
                    data = r.json()
                    embeddings = data.get("data", [])
                    if embeddings and "embedding" in embeddings[0]:
                        dim = len(embeddings[0]["embedding"])
                        record(sec, "S24-02", "Generate embedding vector (Harrier-0.6B)",
                               "PASS", f"✓ {dim}-dim vector returned", t0=t0)
                    else:
                        record(sec, "S24-02", "Generate embedding", "FAIL",
                               f"unexpected response structure: {str(data)[:80]}", t0=t0)
                else:
                    record(sec, "S24-02", "Generate embedding", "FAIL", f"HTTP {r.status_code}", t0=t0)
        except Exception as e:
            record(sec, "S24-02", "Generate embedding", "FAIL", str(e)[:80], t0=t0)
    else:
        record(sec, "S24-02", "Generate embedding", "INFO", "skipped — embedding service not healthy")

    # ── S24-03: Docker-compose RAG env vars consistent ────────────────────────
    t0 = time.time()
    dc_src = (ROOT / "deploy/portal-5/docker-compose.yml").read_text()
    checks = {
        "RAG_EMBEDDING_ENGINE=openai": "RAG_EMBEDDING_ENGINE=openai" in dc_src,
        "harrier model ref": "harrier-oss-v1-0.6b" in dc_src,
        "reranker model ref": "bge-reranker-v2-m3" in dc_src,
        "embedding URL points to TEI": "portal5-embedding" in dc_src or "8917" in dc_src,
    }
    all_ok = all(checks.values())
    failed = [k for k, v in checks.items() if not v]
    record(
        sec, "S24-03", "docker-compose RAG env vars consistent",
        "PASS" if all_ok else "FAIL",
        "✓ all RAG config references present" if all_ok else f"missing: {failed}",
        t0=t0,
    )

    # ── S24-04: Open WebUI RAG config reachable ──────────────────────────────
    t0 = time.time()
    try:
        token = _owui_token()
        if token:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    f"{OPENWEBUI_URL}/api/v1/retrieval/config",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if r.status_code == 200:
                    rag_cfg = r.json()
                    record(sec, "S24-04", "Open WebUI RAG config endpoint reachable",
                           "PASS", f"config keys: {list(rag_cfg.keys())[:5]}", t0=t0)
                else:
                    record(sec, "S24-04", "OWU RAG config", "WARN", f"HTTP {r.status_code}", t0=t0)
        else:
            record(sec, "S24-04", "OWU RAG config", "WARN", "no auth token — skipping")
    except Exception as e:
        record(sec, "S24-04", "OWU RAG config", "WARN", str(e)[:80], t0=t0)
```

---

### 8. NEW SECTION: S38 — GLM-5.1 HEAVY MLX Model

**Add** after the S37 section (the last MLX model-grouped section), before S22:

```python
# ═══════════════════════════════════════════════════════════════════════════════
# S38 — GLM-5.1 HEAVY MLX Model (frontier agentic coder, Zhipu lineage)
# ═══════════════════════════════════════════════════════════════════════════════
# NOTE: This is a HEAVY model (~38GB). It may not fit alongside other loaded models.
# Only runs if PULL_HEAVY=true models have been downloaded.
# Same pattern as S30-S37 but with explicit memory pre-check.

async def S38() -> None:
    print("\n━━━ S38. GLM-5.1 HEAVY MLX (FRONTIER AGENTIC CODER) ━━━")
    sec = "S38"
    model_tag = "mlx-community/GLM-5.1-DQ4plus-q8"

    # ── S38-01: Model present in HuggingFace cache ────────────────────────────
    t0 = time.time()
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    # HF cache uses -- separator for org/model
    cache_dir_pattern = f"models--mlx-community--GLM-5.1-DQ4plus-q8"
    model_cached = any(
        d.name == cache_dir_pattern for d in hf_cache.iterdir()
    ) if hf_cache.exists() else False

    if not model_cached:
        record(sec, "S38-01", "GLM-5.1 model in HF cache",
               "INFO", "not downloaded — run: PULL_HEAVY=true ./launch.sh pull-mlx-models",
               t0=t0)
        record(sec, "S38-02", "GLM-5.1 inference test", "INFO", "skipped — model not cached")
        return

    record(sec, "S38-01", "GLM-5.1 model in HF cache", "PASS", "✓ cached", t0=t0)

    # ── S38-02: Memory pre-check ─────────────────────────────────────────────
    t0 = time.time()
    mem_check = _check_memory_pressure()
    record(sec, "S38-02", "Memory pre-check for HEAVY model (~38GB)",
           "INFO", mem_check, t0=t0)

    # ── S38-03: GLM-5.1 in MODEL_MEMORY dict ─────────────────────────────────
    t0 = time.time()
    proxy_src = (ROOT / "scripts/mlx-proxy.py").read_text()
    has_entry = "GLM-5.1-DQ4plus-q8" in proxy_src
    record(sec, "S38-03", "GLM-5.1 in mlx-proxy.py MODEL_MEMORY",
           "PASS" if has_entry else "FAIL",
           "✓ admission control entry present" if has_entry else "missing — proxy will use unknown default",
           t0=t0)

    # ── S38-04: Load and inference (only if user opts in) ─────────────────────
    # HEAVY models are not auto-tested to avoid disrupting other loaded models.
    # Set TEST_HEAVY_MLX=true to enable.
    if os.environ.get("TEST_HEAVY_MLX", "").lower() != "true":
        record(sec, "S38-04", "GLM-5.1 inference test",
               "INFO", "skipped — set TEST_HEAVY_MLX=true to enable (will unload current MLX model)")
        return

    t0 = time.time()
    try:
        loaded = await _load_mlx_model(model_tag, timeout=300)
        if not loaded:
            record(sec, "S38-04", "GLM-5.1 model load", "FAIL",
                   "failed to load within 300s — may exceed memory", t0=t0)
            return
        record(sec, "S38-04", "GLM-5.1 model load", "PASS",
               f"✓ loaded in {time.time() - t0:.0f}s", t0=t0)
    except Exception as e:
        record(sec, "S38-04", "GLM-5.1 model load", "FAIL", str(e)[:80], t0=t0)
        return

    # ── S38-05: Inference test ────────────────────────────────────────────────
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                f"{MLX_URL}/v1/chat/completions",
                json={
                    "model": model_tag,
                    "messages": [{"role": "user", "content": "Write a Python function to reverse a linked list. Be concise."}],
                    "max_tokens": 400,
                    "temperature": 0.2,
                },
            )
            if r.status_code == 200:
                data = r.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                has_code = any(kw in content.lower() for kw in ["def ", "node", "next", "reverse", "class"])
                record(
                    sec, "S38-05", "GLM-5.1 coding inference",
                    "PASS" if has_code else "WARN",
                    f"✓ code response ({len(content)} chars)" if has_code else f"response lacks code keywords: {content[:80]}",
                    t0=t0,
                )
            else:
                record(sec, "S38-05", "GLM-5.1 inference", "FAIL",
                       f"HTTP {r.status_code}: {r.text[:80]}", t0=t0)
    except Exception as e:
        record(sec, "S38-05", "GLM-5.1 inference", "FAIL", str(e)[:80], t0=t0)
```

---

### 9. S16 additions — CLI command checks

**Find** the `S16()` function. Find where it checks for launch.sh commands (likely a list of command names grepped from launch.sh). **Add** these to whatever command-presence check exists:

```python
    # ── S16-XX: Speech server CLI commands ────────────────────────────────────
    t0 = time.time()
    launch_src = (ROOT / "launch.sh").read_text()
    has_start = "start-speech)" in launch_src
    has_stop = "stop-speech)" in launch_src
    record(
        sec, "S16-10", "launch.sh has start-speech / stop-speech commands",
        "PASS" if has_start and has_stop else "FAIL",
        "✓ both commands present" if has_start and has_stop else f"start={has_start} stop={has_stop}",
        t0=t0,
    )
```

---

### 10. Register new sections

**Find** the `SECTIONS` dictionary (around line 7362). **Add** entries for the new sections:

```python
    "S24": S24,
    "S38": S38,
```

Add `S24` after `S23` and `S38` after `S37` in the dict.

**Find** the `ALL_ORDER` list (around line 7395). **Add** the new sections in the correct execution order:

- Add `"S24",` after `"S15",` (in the "No LLM dependency" group, since embedding/reranker tests don't need an LLM)
- Add `"S38",` after `"S37",` (in the MLX model-grouped section, before S22)

The updated ALL_ORDER should look like:

```python
ALL_ORDER = [
    "S17",  # Rebuild & restart first
    "S0",   # Version state
    "S1",   # Static config
    "S2",   # Service health
    # ── No LLM dependency (can run anytime) ────────────────────────────────
    "S8",   # TTS (MLX speech / kokoro fallback)
    "S9",   # STT (Qwen3-ASR / Whisper fallback)
    "S12",  # Metrics (Prometheus/Grafana)
    "S13",  # GUI (Playwright/Chromium)
    "S14",  # HOWTO audit (static file checks)
    "S16",  # CLI commands (launch.sh)
    "S21",  # Notifications & alerts
    "S24",  # RAG embedding pipeline (Harrier + bge-reranker)
    # ── Ollama workspaces + personas (no MLX needed) ───────────────────────
    ... (existing entries unchanged)
    # ── MLX models — grouped by model ──────────────────────────────────────
    ... (existing S30-S37 unchanged)
    "S38",  # GLM-5.1 HEAVY: frontier agentic coder (Zhipu lineage, optional)
    "S22",  # MLX model switching
    ... (rest unchanged)
]
```

---

## Post-Implementation Validation

```bash
# 1. Syntax check
python3 -c "import ast; ast.parse(open('portal5_acceptance_v4.py').read()); print('✅ syntax valid')"

# 2. Section registration check
python3 -c "
import re
src = open('portal5_acceptance_v4.py').read()
sections = re.findall(r'\"(S\d+)\"\s*:', src[src.index('SECTIONS ='):src.index('ALL_ORDER')])
order = re.findall(r'\"(S\d+)\"', src[src.index('ALL_ORDER'):src.index('ALL_ORDER') + 2000])
print(f'Registered sections: {len(sections)}')
print(f'Execution order entries: {len(order)}')
for s in ['S24', 'S38']:
    assert s in sections, f'{s} not in SECTIONS dict'
    assert s in order, f'{s} not in ALL_ORDER'
    print(f'  ✅ {s} registered and ordered')
"

# 3. New test ID check
python3 -c "
import re
src = open('portal5_acceptance_v4.py').read()
new_tids = ['S1-12', 'S1-13', 'S1-14', 'S1-15', 'S1-16', 'S2-17', 'S2-18',
            'S24-01', 'S24-02', 'S24-03', 'S24-04', 'S38-01', 'S38-02', 'S38-03',
            'S38-04', 'S38-05', 'S16-10']
for tid in new_tids:
    assert tid in src, f'{tid} not found in test suite'
print(f'✅ All {len(new_tids)} new test IDs present')
"

# 4. Port config check
python3 -c "
src = open('portal5_acceptance_v4.py').read()
assert '\"embedding\"' in src, 'embedding port not in MCP dict'
assert 'MLX_SPEECH_PORT' in src, 'MLX_SPEECH_PORT not defined'
assert 'MLX_SPEECH_URL' in src, 'MLX_SPEECH_URL not defined'
print('✅ port configs present')
"
```

---

## Commit Message

```
test: add acceptance tests for embedding, speech, GLM-5.1 (S24, S38)

Update portal5_acceptance_v4.py for frontier model + speech pipeline changes:

- S1-12..16: Static config checks for embedding service, reranker,
  GLM-5.1 (backends.yaml + MODEL_MEMORY), GLM-OCR, mlx-speech.py,
  launch.sh commands
- S2-17/18: Health checks for portal5-embedding (:8917) and
  mlx-speech (:8918)
- S8: Rewritten for MLX speech server. Tests Kokoro backward compat,
  Qwen3-TTS CustomVoice (preset speakers + style), VoiceDesign
  (text → voice). Falls back to Docker mcp-tts if MLX unavailable.
- S9: Rewritten for Qwen3-ASR via MLX speech. Round-trip TTS→WAV→ASR.
  Falls back to Docker faster-whisper if MLX unavailable.
- S24 (NEW): RAG embedding pipeline — Harrier-0.6B health, vector
  generation, docker-compose RAG env consistency, OWU config endpoint
- S38 (NEW): GLM-5.1 HEAVY MLX — cache check, MODEL_MEMORY validation,
  opt-in inference test (TEST_HEAVY_MLX=true). Skips gracefully if
  model not downloaded.
- S16-10: start-speech / stop-speech CLI command presence
- MCP port dict: added embedding (8917)
- MLX_SPEECH_PORT / MLX_SPEECH_URL constants for host-native speech

New test IDs: S1-12..16, S2-17/18, S8-03/04, S24-01..04, S38-01..05, S16-10
```

---

## Rollback

```bash
git checkout -- portal5_acceptance_v4.py
```

---

## Test Execution Examples

```bash
# Run only the new sections
python3 portal5_acceptance_v4.py --section S1,S2,S8,S9,S24

# Run S38 (GLM-5.1 HEAVY — requires model download + opt-in)
PULL_HEAVY=true ./launch.sh pull-mlx-models
TEST_HEAVY_MLX=true python3 portal5_acceptance_v4.py --section S38

# Full suite (all sections including new ones)
python3 portal5_acceptance_v4.py
```

---

*Task file for Claude Code execution. All find/replace blocks reference portal5_acceptance_v4.py from v6.0.0 + changes from TASK_FRONTIER_MODELS.md and TASK_SPEECH_PIPELINE_UPGRADE.md.*
