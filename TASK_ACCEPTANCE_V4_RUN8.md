# TASK_ACCEPTANCE_V4_RUN8 — Acceptance Suite & Execute Guide Updates

**Repo**: https://github.com/ckindle-42/portal-5/  
**Base SHA**: 64de992 (HEAD as of 2026-04-07)  
**Last run**: Run 7 — 204 PASS · 1 WARN · 9 INFO · 0 FAIL · 0 BLOCKED (SHA 9ae765a)  
**Target**: Run 8 — **215+ PASS · 0 WARN · 0 INFO · 0 FAIL · 0 BLOCKED**  
**Prerequisite**: `TASK_V6_RELEASE.md` must be committed to `main` before running
this task. That task implements P5-FUT-006 (LLM intent routing) and P5-FUT-009 (MLX
admission control) and bumps the version to 6.0.0. This task adds acceptance test
coverage for those features and all other infra changes since Run 7.

**Files to modify** (safe to edit):
- `portal5_acceptance_v4.py`
- `PORTAL5_ACCEPTANCE_V4_EXECUTE.md`

**Protected — never touch**:
- `portal_pipeline/**`, `portal_mcp/**`, `config/personas/**`, `deploy/`, `Dockerfile.*`
- `scripts/openwebui_init.py`, `docs/HOWTO.md`, `imports/openwebui/**`, `config/backends.yaml`

---

## Why This Task Exists

Six distinct changes since Run 7 require test suite updates:

| # | Source | Change | Gap |
|---|--------|--------|-----|
| 1 | `13db076` | `dispatcher.py` default → `localhost:9099` | S20-02/S20-05 DNS-fallback dead code still present |
| 2 | `13db076` | 6 INFO records converted to PASS/FAIL/WARN | First clean run will be Run 8 |
| 3 | `c01485f` | `ENABLE_REMOTE_ACCESS` / `WEBUI_LISTEN_ADDR` toggle | Zero test coverage |
| 4 | `42fecfd` | Content-aware routing call has no `record()` — result never emitted | S3-17 is a dead call |
| 5 | `TASK_V6_RELEASE.md` | P5-FUT-006 LLM intent routing in `router_pipe.py` | Zero acceptance coverage |
| 6 | `TASK_V6_RELEASE.md` | P5-FUT-009 `MODEL_MEMORY` admission control in `mlx-proxy.py` | Zero acceptance coverage |

---

## Pre-Flight

```bash
git clone https://github.com/ckindle-42/portal-5/ && cd portal-5

# Verify TASK_V6_RELEASE.md has been applied
grep "6.0.0" pyproject.toml
python3 -c "from portal_pipeline.router_pipe import _route_with_llm; print('FUT-006 OK')"
python3 -c "
import importlib.util
m = importlib.util.spec_from_file_location('p', 'scripts/mlx-proxy.py')
mod = importlib.util.module_from_spec(m); m.loader.exec_module(mod)
print('MODEL_MEMORY entries:', len(mod.MODEL_MEMORY))
"

# Baseline unit tests must pass before any edits
pip install -e ".[dev]" --quiet
pytest tests/ -q --tb=short
```

If `_route_with_llm` import fails or `MODEL_MEMORY` is missing, stop — apply
`TASK_V6_RELEASE.md` first, then return here.

---

## Change 1 — Fix S20-02: remove stale DNS-fallback (Telegram dispatcher)

**File**: `portal5_acceptance_v4.py`

`dispatcher.py` now uses `localhost:9099` by default. The `"nodename"` / `"servname"`
exception branch is dead code that silently upgrades a real failure to PASS.

**Find this entire block** (search for the comment anchor):

```
        # Verify dispatcher call_pipeline_async works with Telegram workspace
        # Note: dispatcher uses Docker-internal PIPELINE_URL (portal-pipeline:9099),
```

The block ends with:

```python
            else:
                record(
                    sec,
                    "S20-02",
                    "Telegram dispatcher: call_pipeline_async",
                    "FAIL",
                    err_str,
                    t0=t0,
                )
```

**Replace the entire block** (from the comment through the closing `record`) with:

```python
        # dispatcher.py uses localhost:9099 by default (fixed in commit 13db076).
        # Direct pipeline call — same path the dispatcher uses at runtime.
        t0 = time.time()
        try:
            from portal_channels.dispatcher import VALID_WORKSPACES, _build_payload

            assert "auto" in VALID_WORKSPACES
            assert "auto-coding" in VALID_WORKSPACES
            payload = _build_payload([{"role": "user", "content": "test"}], "auto")
            assert "model" in payload and "messages" in payload

            code, text = await _chat(
                "auto", "Say 'ok' and nothing else.", max_tokens=20, timeout=30
            )
            record(
                sec,
                "S20-02",
                "Telegram dispatcher: pipeline reachable via localhost",
                "PASS"
                if code == 200 and text.strip()
                else ("WARN" if code in (503, 408) else "FAIL"),
                f"reply length: {len(text)}" if text else f"HTTP {code}",
                t0=t0,
            )
        except Exception as e:
            record(
                sec,
                "S20-02",
                "Telegram dispatcher: pipeline reachable via localhost",
                "FAIL",
                str(e)[:120],
                t0=t0,
            )
```

---

## Change 2 — Fix S20-05: remove stale DNS-fallback (Slack dispatcher)

**File**: `portal5_acceptance_v4.py`

Same root cause as Change 1. Find the anchor:

```
        # Verify dispatcher works with Slack workspace routing
        # Note: dispatcher uses Docker-internal PIPELINE_URL (portal-pipeline:9099),
```

The block ends with:

```python
            else:
                record(
                    sec, "S20-05", "Slack dispatcher: call_pipeline_sync", "FAIL", err_str, t0=t0
                )
```

**Replace the entire block** with:

```python
        # dispatcher.py uses localhost:9099 by default (fixed in commit 13db076).
        t0 = time.time()
        try:
            from portal_channels.dispatcher import call_pipeline_sync

            reply = call_pipeline_sync("Say 'ok' and nothing else.", "auto")
            record(
                sec,
                "S20-05",
                "Slack dispatcher: call_pipeline_sync returns response",
                "PASS" if reply and len(reply.strip()) > 0 else "FAIL",
                f"reply length: {len(reply)}" if reply else "empty response",
                t0=t0,
            )
        except Exception as e:
            record(
                sec,
                "S20-05",
                "Slack dispatcher: call_pipeline_sync",
                "FAIL",
                str(e)[:120],
                t0=t0,
            )
```

---

## Change 3 — Add S2-16: ENABLE_REMOTE_ACCESS bind-address check

**File**: `portal5_acceptance_v4.py`

**Location**: After the S2-15 MLX proxy block, immediately before the `# ═══` S3 header.

Find this exact line (end of S2-15 exception handler):

```python
        # MLX proxy loads on-demand — not running at test start is expected; skip record
        pass
```

**Insert after that `pass`**:

```python
    # S2-16: ENABLE_REMOTE_ACCESS / WEBUI_LISTEN_ADDR — default must be localhost-only.
    # docker-compose binds Open WebUI to ${WEBUI_LISTEN_ADDR:-127.0.0.1}:8080:8080.
    t0 = time.time()
    try:
        env_val = os.environ.get("ENABLE_REMOTE_ACCESS", "").lower()
        if not env_val:
            dot_env = ROOT / ".env"
            if dot_env.exists():
                for line in dot_env.read_text().splitlines():
                    if line.strip().startswith("ENABLE_REMOTE_ACCESS"):
                        env_val = line.split("=", 1)[-1].strip().lower()
                        break

        insp = subprocess.run(
            ["docker", "inspect", "--format",
             "{{range $p, $c := .NetworkSettings.Ports}}{{$p}}={{range $c}}{{.HostIp}}:{{.HostPort}}{{end}} {{end}}",
             "portal5-open-webui"],
            capture_output=True, text=True, timeout=10,
        )
        binding_raw = insp.stdout.strip()

        if env_val in ("", "false"):
            if "0.0.0.0:8080" in binding_raw:
                record(sec, "S2-16", "Open WebUI bind address (ENABLE_REMOTE_ACCESS=false)",
                       "FAIL",
                       "bound to 0.0.0.0:8080 but ENABLE_REMOTE_ACCESS is false — "
                       "restart: ./launch.sh down && ./launch.sh up",
                       t0=t0)
            elif "127.0.0.1:8080" in binding_raw:
                record(sec, "S2-16", "Open WebUI bind address (ENABLE_REMOTE_ACCESS=false)",
                       "PASS", "correctly bound to 127.0.0.1:8080 (localhost-only)", t0=t0)
            else:
                record(sec, "S2-16", "Open WebUI bind address (ENABLE_REMOTE_ACCESS=false)",
                       "WARN", f"unexpected binding: {binding_raw[:80]}", t0=t0)
        else:
            record(sec, "S2-16", "Open WebUI bind address (ENABLE_REMOTE_ACCESS=true)",
                   "PASS" if "0.0.0.0:8080" in binding_raw else "WARN",
                   f"binding: {binding_raw[:80]}", t0=t0)
    except Exception as e:
        record(sec, "S2-16", "Open WebUI bind address check", "WARN", str(e)[:80], t0=t0)
```

---

## Change 4 — Fix S3-17: restore missing record() on content-aware routing

**File**: `portal5_acceptance_v4.py`

Commit `42fecfd` left this `_chat()` call with no `record()` — the request fires but
the result is never captured. Find this exact block:

```python
    # ── Content-aware routing: security keywords → auto-redteam ──────────────
    # Weighted scoring: exploit(3) + payload(3) + shellcode(3) + reverse shell(3) + bypass(2) + evasion(2) = 16
    # Threshold for auto-redteam is 4, so this easily exceeds it.
    t0 = time.time()
    code, _ = await _chat(
        "auto",
        "exploit vulnerability payload shellcode reverse shell bypass evasion",
        max_tokens=5,
        timeout=30,
    )
```

**Replace with**:

```python
    # ── S3-17: Content-aware routing — weighted keyword scoring → auto-redteam ──
    # exploit(3)+payload(3)+shellcode(3)+reverse shell(3)+bypass(2)+evasion(2)=16
    # Threshold for auto-redteam is 4. Verify pipeline log shows security workspace.
    t0 = time.time()
    code, _ = await _chat(
        "auto",
        "exploit vulnerability payload shellcode reverse shell bypass evasion",
        max_tokens=5,
        timeout=30,
    )
    _s3_17_logs = _grep_logs(
        "portal5-pipeline",
        r"Auto-routing.*auto-redteam|Auto-routing.*auto-security|"
        r"detected workspace.*auto-redteam|detected workspace.*auto-security",
        lines=50,
    )
    record(
        sec,
        "S3-17",
        "Content-aware routing (keyword): security prompt → auto-redteam or auto-security",
        "PASS" if code == 200 and _s3_17_logs else "WARN",
        "pipeline log confirmed routing to security workspace"
        if _s3_17_logs
        else f"HTTP {code} — no routing log match (non-streaming may not emit log)",
        t0=t0,
    )
```

---

## Change 5 — Add S3-20: SPL keyword routing boundary test

**File**: `portal5_acceptance_v4.py`

`'splunk'` and `'spl query'` were removed from `_CODING_KEYWORDS` in commit `42fecfd`.
No test verifies that a SPL-heavy prompt routes to `auto-spl` and not `auto-coding`.

**Location**: After the S3-19 routing log cross-check. Find the end of S3-19:

```python
        [f"{len(log_lines)} routing-related log lines"],
    )
```

**Insert after**:

```python
    # ── S3-20: Content-aware routing — SPL prompt must route to auto-spl not auto-coding ──
    # tstats(3) + correlation search(3) = 6, exceeds auto-spl threshold (3).
    # 'splunk' and 'spl query' removed from _CODING_KEYWORDS in commit 42fecfd.
    t0 = time.time()
    code, _ = await _chat(
        "auto",
        "write a tstats correlation search to detect brute force in Splunk ES",
        max_tokens=5,
        timeout=30,
    )
    _s3_20_spl_logs = _grep_logs(
        "portal5-pipeline",
        r"Auto-routing.*auto-spl|detected workspace.*auto-spl",
        lines=50,
    )
    _s3_20_coding_logs = _grep_logs(
        "portal5-pipeline",
        r"Auto-routing.*auto-coding|detected workspace.*auto-coding",
        lines=50,
    )
    if _s3_20_spl_logs and not _s3_20_coding_logs:
        _s3_20_status, _s3_20_detail = "PASS", "pipeline log confirmed routing to auto-spl"
    elif _s3_20_coding_logs:
        _s3_20_status = "FAIL"
        _s3_20_detail = "routed to auto-coding — 'tstats'/'splunk' must not match _CODING_KEYWORDS"
    else:
        _s3_20_status = "WARN"
        _s3_20_detail = (
            f"HTTP {code} — no routing log match "
            "(non-streaming may not emit log; response served)"
        )
    record(sec, "S3-20",
           "Content-aware routing (keyword): SPL prompt → auto-spl, not auto-coding",
           _s3_20_status, _s3_20_detail, t0=t0)
```

---

## Change 6 — Add S1-08/S1-09: LLM router config files (P5-FUT-006)

**File**: `portal5_acceptance_v4.py`

**Location**: After the S1-07 Magistral block. Find the end of S1-07:

```python
            "Add 'lmstudio-community/Magistral-Small-2509-MLX-8bit' to ALL_MODELS "
            "only (not VLM_MODELS) in scripts/mlx-proxy.py"
        ),
    )
```

**Insert after**:

```python
    # S1-08: config/routing_descriptions.json — present and covers routable workspaces (P5-FUT-006)
    t0 = time.time()
    desc_path = ROOT / "config" / "routing_descriptions.json"
    if desc_path.exists():
        try:
            desc_data = json.loads(desc_path.read_text())
            desc_ws = {k for k in desc_data if not k.startswith("_")}
            routable = {"auto-coding", "auto-spl", "auto-security", "auto-redteam",
                        "auto-reasoning", "auto-compliance"}
            missing_descs = routable - desc_ws
            record(
                sec, "S1-08",
                f"config/routing_descriptions.json — {len(desc_ws)} workspaces described",
                "PASS" if not missing_descs else "WARN",
                "all routable workspaces described"
                if not missing_descs
                else f"missing descriptions for: {missing_descs}",
                t0=t0,
            )
        except Exception as e:
            record(sec, "S1-08", "config/routing_descriptions.json valid JSON",
                   "FAIL", str(e)[:80], t0=t0)
    else:
        record(sec, "S1-08", "config/routing_descriptions.json present",
               "FAIL", "not found — TASK_V6_RELEASE.md must run first", t0=t0)

    # S1-09: config/routing_examples.json — present, non-empty, well-formed (P5-FUT-006)
    t0 = time.time()
    ex_path = ROOT / "config" / "routing_examples.json"
    if ex_path.exists():
        try:
            ex_data = json.loads(ex_path.read_text())
            examples = ex_data.get("examples", [])
            malformed = [i for i, e in enumerate(examples)
                         if not all(k in e for k in ("message", "workspace", "confidence"))]
            record(
                sec, "S1-09",
                f"config/routing_examples.json — {len(examples)} examples",
                "PASS" if examples and not malformed else ("WARN" if examples else "FAIL"),
                f"{len(examples)} examples, all well-formed"
                if not malformed
                else f"malformed entries at indices: {malformed[:5]}",
                t0=t0,
            )
        except Exception as e:
            record(sec, "S1-09", "config/routing_examples.json valid JSON",
                   "FAIL", str(e)[:80], t0=t0)
    else:
        record(sec, "S1-09", "config/routing_examples.json present",
               "FAIL", "not found — TASK_V6_RELEASE.md must run first", t0=t0)
```

---

## Change 7 — Add S1-10: MODEL_MEMORY covers ALL_MODELS (P5-FUT-009)

**File**: `portal5_acceptance_v4.py`

**Location**: Immediately after the S1-09 block from Change 6.

```python
    # S1-10: MODEL_MEMORY in mlx-proxy.py covers all models in ALL_MODELS (P5-FUT-009)
    t0 = time.time()
    proxy_src = (ROOT / "scripts" / "mlx-proxy.py").read_text()
    has_model_memory = "MODEL_MEMORY" in proxy_src
    has_headroom = "MEMORY_HEADROOM_GB" in proxy_src
    has_check_fn = "_check_memory_for_model" in proxy_src
    if has_model_memory and has_headroom and has_check_fn:
        import re as _re2
        all_models_m = _re2.search(r"ALL_MODELS\s*=\s*\[(.*?)\]", proxy_src, _re2.DOTALL)
        model_memory_m = _re2.search(
            r"MODEL_MEMORY\s*:\s*dict.*?=\s*\{(.*?)\n\}", proxy_src, _re2.DOTALL
        )
        if all_models_m and model_memory_m:
            all_listed = _re2.findall(r'"([^"]+)"', all_models_m.group(1))
            mem_text = model_memory_m.group(1)
            missing_from_dict = [m for m in all_listed if m not in mem_text]
            record(
                sec, "S1-10",
                f"mlx-proxy.py MODEL_MEMORY covers all {len(all_listed)} models in ALL_MODELS",
                "PASS" if not missing_from_dict else "FAIL",
                "all models have memory estimates"
                if not missing_from_dict
                else f"missing from MODEL_MEMORY: {missing_from_dict}",
                t0=t0,
            )
        else:
            record(sec, "S1-10", "mlx-proxy.py MODEL_MEMORY structure parseable",
                   "WARN", "could not parse ALL_MODELS or MODEL_MEMORY block", t0=t0)
    else:
        missing_pieces = [x for x, ok in [
            ("MODEL_MEMORY", has_model_memory),
            ("MEMORY_HEADROOM_GB", has_headroom),
            ("_check_memory_for_model", has_check_fn),
        ] if not ok]
        record(sec, "S1-10", "mlx-proxy.py MODEL_MEMORY admission control present",
               "FAIL", f"missing: {missing_pieces} — run TASK_V6_RELEASE.md", t0=t0)
```

---

## Change 8 — Add S1-11: LLM router wired into router_pipe.py

**File**: `portal5_acceptance_v4.py`

**Location**: Immediately after the S1-10 block from Change 7.

```python
    # S1-11: LLM intent router wired into router_pipe.py auto-routing path (P5-FUT-006)
    t0 = time.time()
    router_src = (ROOT / "portal_pipeline" / "router_pipe.py").read_text()
    has_fn = "_route_with_llm" in router_src
    has_await = "await _route_with_llm" in router_src
    has_fallback = "_detect_workspace" in router_src
    env_example = (ROOT / ".env.example").read_text() \
        if (ROOT / ".env.example").exists() else ""
    has_env_doc = "LLM_ROUTER_ENABLED" in env_example
    all_ok = has_fn and has_await and has_fallback and has_env_doc
    record(
        sec, "S1-11",
        "LLM intent router wired into router_pipe.py (P5-FUT-006)",
        "PASS" if all_ok else "FAIL",
        "LLM router present, wired, keyword fallback retained, env var documented"
        if all_ok
        else f"missing: fn={has_fn} await={has_await} fallback={has_fallback} env={has_env_doc}",
        t0=t0,
    )
```

---

## Change 9 — Add S14-13/S14-14: .env.example coverage for v6.0 features

**File**: `portal5_acceptance_v4.py`

**Location**: After the S14-12 block. Find:

```python
        "found" if "auto-spl" in howto else "missing — add auto-spl to workspace table",
    )
```

**Insert after**:

```python
    # S14-13: .env.example documents ENABLE_REMOTE_ACCESS (commit c01485f)
    env_example_text = (ROOT / ".env.example").read_text() \
        if (ROOT / ".env.example").exists() else ""
    record(
        sec, "S14-13",
        ".env.example documents ENABLE_REMOTE_ACCESS",
        "PASS" if "ENABLE_REMOTE_ACCESS" in env_example_text else "FAIL",
        "found" if "ENABLE_REMOTE_ACCESS" in env_example_text
        else "missing — add ENABLE_REMOTE_ACCESS to .env.example",
    )

    # S14-14: .env.example documents LLM_ROUTER_ENABLED (P5-FUT-006)
    record(
        sec, "S14-14",
        ".env.example documents LLM_ROUTER_ENABLED (P5-FUT-006)",
        "PASS" if "LLM_ROUTER_ENABLED" in env_example_text else "FAIL",
        "found" if "LLM_ROUTER_ENABLED" in env_example_text
        else "missing — add LLM router env block (see TASK_V6_RELEASE.md)",
    )
```

---

## Change 10 — Add S22-05/S22-06: admission control and LLM router live checks

**File**: `portal5_acceptance_v4.py`

**Location**: After the S22-04 watchdog block. Find:

```python
        record(sec, "S22-04", "MLX watchdog not running (correct for testing)",
               "PASS", "watchdog absent — no interference with MLX model switching", t0=t0)
```

**Insert after** (note the `if/else` closes here so insert is at the same indentation
level as the S22-04 block, not inside it):

```python
    # S22-05: MODEL_MEMORY admission control — source present + /health/memory live (P5-FUT-009)
    t0 = time.time()
    _proxy_src_22 = (ROOT / "scripts" / "mlx-proxy.py").read_text()
    _has_admission = all(
        tok in _proxy_src_22
        for tok in ("MODEL_MEMORY", "MEMORY_HEADROOM_GB", "_check_memory_for_model")
    )
    if _has_admission:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{MLX_URL}/health/memory")
            if r.status_code == 200:
                mem = r.json()
                free_gb = mem.get("current", {}).get("free_gb", -1)
                record(
                    sec, "S22-05",
                    "MLX proxy admission control present + /health/memory live",
                    "PASS",
                    f"MODEL_MEMORY dict present, /health/memory reachable, free={free_gb:.1f}GB",
                    t0=t0,
                )
            else:
                record(sec, "S22-05", "MLX proxy admission control present",
                       "WARN", f"source OK but /health/memory returned HTTP {r.status_code}",
                       t0=t0)
        except Exception as e:
            record(sec, "S22-05", "MLX proxy admission control (proxy offline)",
                   "WARN", f"source has MODEL_MEMORY but proxy unreachable: {str(e)[:60]}",
                   t0=t0)
    else:
        record(sec, "S22-05", "MLX proxy admission control (P5-FUT-009)",
               "FAIL",
               "MODEL_MEMORY or _check_memory_for_model missing from mlx-proxy.py "
               "— run TASK_V6_RELEASE.md", t0=t0)

    # S22-06: LLM router live — hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF responds with valid workspace ID (P5-FUT-006)
    t0 = time.time()
    _llm_router_enabled = os.environ.get("LLM_ROUTER_ENABLED", "true").lower()
    if _llm_router_enabled == "false":
        print("  ⏭  LLM_ROUTER_ENABLED=false — skipping S22-06")
    else:
        _llm_model = os.environ.get("LLM_ROUTER_MODEL", "hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF")
        _llm_url = os.environ.get("LLM_ROUTER_OLLAMA_URL", "http://localhost:11434")
        _valid_ws_ids = {
            "auto", "auto-coding", "auto-spl", "auto-security", "auto-redteam",
            "auto-blueteam", "auto-creative", "auto-reasoning", "auto-documents",
            "auto-video", "auto-music", "auto-research", "auto-vision",
            "auto-data", "auto-compliance", "auto-mistral",
        }
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.post(
                    f"{_llm_url}/api/generate",
                    json={
                        "model": _llm_model,
                        "prompt": (
                            "You are an intent router. Classify: "
                            "'write a tstats query to count failed logins by user in Splunk ES' "
                            'Respond ONLY with JSON: {"workspace": "<id>", "confidence": <0-1>}'
                        ),
                        "stream": False,
                        "options": {"temperature": 0, "num_predict": 40},
                    },
                )
            if r.status_code == 200:
                raw = r.json().get("response", "").strip()
                try:
                    parsed = json.loads(raw)
                    ws = parsed.get("workspace", "")
                    conf = float(parsed.get("confidence", 0))
                    record(
                        sec, "S22-06",
                        f"LLM router ({_llm_model}) returns valid workspace",
                        "PASS" if ws in _valid_ws_ids and conf >= 0.5 else "WARN",
                        f"workspace={ws!r} confidence={conf:.2f}"
                        + ("" if ws in _valid_ws_ids else " — unknown workspace ID"),
                        t0=t0,
                    )
                except (json.JSONDecodeError, ValueError):
                    record(sec, "S22-06", "LLM router response parseable",
                           "WARN", f"non-JSON response: {raw[:80]}", t0=t0)
            else:
                record(sec, "S22-06", "LLM router reachable",
                       "WARN",
                       f"Ollama HTTP {r.status_code} — pull: ollama pull {_llm_model}",
                       t0=t0)
        except Exception as e:
            record(sec, "S22-06", "LLM router reachable",
                   "WARN", f"Ollama unreachable at {_llm_url}: {str(e)[:80]}", t0=t0)
```

---

## Change 11 — Update module docstring changelog

**File**: `portal5_acceptance_v4.py`

Find the last changelog block ending with "Post-run assertion fixes (2026-04-06)".
Append after its final bullet:

```
Run 8 fixes (2026-04-07):
    - S20-02/S20-05: Removed stale DNS-fallback exception branches. dispatcher.py
      default changed from portal-pipeline:9099 to localhost:9099 (commit 13db076).
      Real failures now surface as FAIL rather than silently downgrading to PASS.
    - S3-17: Restored missing record() on content-aware routing dead call. Request was
      firing but result never recorded. Now asserts pipeline log confirms security routing.
    - S3-20: New test — SPL keyword prompt sent to auto workspace must route to auto-spl
      (not auto-coding). Validates _CODING_KEYWORDS/SPL boundary from commit 42fecfd.
    - S2-16: New test — Open WebUI bind address matches ENABLE_REMOTE_ACCESS setting.
      Inspects live container port via docker inspect (commit c01485f).
    - S1-08/S1-09: routing_descriptions.json and routing_examples.json present and
      well-formed (P5-FUT-006, TASK_V6_RELEASE.md).
    - S1-10: MODEL_MEMORY covers all ALL_MODELS entries (P5-FUT-009). Fails immediately
      when new models are added to ALL_MODELS without corresponding memory estimates.
    - S1-11: _route_with_llm wired into router_pipe.py; keyword fallback retained;
      LLM_ROUTER_ENABLED documented in .env.example.
    - S14-13: .env.example documents ENABLE_REMOTE_ACCESS.
    - S14-14: .env.example documents LLM_ROUTER_ENABLED.
    - S22-05: MODEL_MEMORY present in proxy source + /health/memory endpoint live (P5-FUT-009).
    - S22-06: LLM router live classification via hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF (P5-FUT-006). WARN (not FAIL)
      if model not pulled, so suite does not fail on environments without the model.
    - PORTAL5_ACCEPTANCE_V4_EXECUTE.md: target 215+ P/0W/0F, step 2/3 notes, quick-ref.
```

---

## Change 12 — Update PORTAL5_ACCEPTANCE_V4_EXECUTE.md

### 12a — Most recent run block

**Find and replace the entire block** starting with `## Most recent run`:

```markdown
## Most recent run

**Date:** 2026-04-07 14:08:14  
**Git SHA:** 9ae765a  
**Result:** 204 PASS · 1 WARN · 9 INFO · 0 FAIL · 0 BLOCKED  
**Runtime:** ~63 min (3785s)

**Post-run fixes applied (target for Run 8 — requires TASK_V6_RELEASE.md first):**
- `13db076`: dispatcher default `portal-pipeline:9099` → `localhost:9099`.
  S20-02/S20-05 DNS-fallback dead code removed. 1 WARN (S20-02) eliminated.
- `13db076`: 6 INFO records converted to PASS/FAIL/WARN. INFO count 9 → 3.
- S3-17: record() restored on dead content-aware routing call.
- S3-20 added: SPL keyword routing boundary test (auto-spl, not auto-coding).
- S2-16 added: Open WebUI bind address / ENABLE_REMOTE_ACCESS check.
- S1-08/09 added: routing config JSON files present and well-formed (P5-FUT-006).
- S1-10 added: MODEL_MEMORY covers all ALL_MODELS entries (P5-FUT-009).
- S1-11 added: LLM router wired into router_pipe.py.
- S14-13/14 added: .env.example documents ENABLE_REMOTE_ACCESS and LLM_ROUTER_ENABLED.
- S22-05 added: admission control source + /health/memory live (P5-FUT-009).
- S22-06 added: LLM router live classification via hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF (P5-FUT-006).

**Run 8 target: 215+ PASS · 0 WARN · 0 INFO · 0 FAIL · 0 BLOCKED**

*Pre-run: pull the LLM router model or S22-06 will WARN instead of PASS:*
```bash
ollama pull hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF
```
```

### 12b — Step 2: add bind-address and LLM router pre-flight

After the existing workspace count verification paragraph, add:

```markdown
Verify Open WebUI bind address matches `ENABLE_REMOTE_ACCESS`:
```bash
docker inspect --format \
  '{{range $p, $c := .NetworkSettings.Ports}}{{$p}}={{range $c}}{{.HostIp}}:{{.HostPort}}{{end}} {{end}}' \
  portal5-open-webui
# Default (ENABLE_REMOTE_ACCESS=false): 127.0.0.1:8080
# Remote enabled:                       0.0.0.0:8080
```
If wrong, the stack was started with `docker compose up` directly. Fix:
`./launch.sh down && ./launch.sh up`.

Verify LLM router model is available (required for S22-06 PASS):
```bash
ollama list | grep QuantFactory
# If missing: ollama pull hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF
```
```

### 12c — Quick reference table: remove resolved row, add new rows

**Remove** (if present):
```
| S20-02 WARN | Telegram dispatcher DNS failure (portal-pipeline:9099 not resolvable from host) | ...
```

**Update**:
```
| S20-01 / S20-04 INFO | → | S20-01 / S20-04 skip | Silently skipped — no record emitted |
```

**Add**:
```markdown
| S22-06 WARN | hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF not pulled | `ollama pull hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` then re-run S22 |
| S2-16 FAIL | Open WebUI bound to 0.0.0.0 with ENABLE_REMOTE_ACCESS=false | Stack not launched via ./launch.sh. Fix: `./launch.sh down && ./launch.sh up` |
| S1-10 FAIL | Model in ALL_MODELS missing from MODEL_MEMORY | Add `"model/path": GB_estimate` to MODEL_MEMORY in scripts/mlx-proxy.py |
| S1-08/S1-09 FAIL | routing_descriptions.json or routing_examples.json missing | TASK_V6_RELEASE.md not applied — apply it first |
```

---

## Validation Steps

```bash
cd portal-5

# 1. Syntax
python3 -m py_compile portal5_acceptance_v4.py && echo "syntax OK"

# 2. All new test IDs present
python3 -c "
text = open('portal5_acceptance_v4.py').read()
ids = ['S2-16','S3-17','S3-20','S1-08','S1-09','S1-10','S1-11',
       'S14-13','S14-14','S22-05','S22-06']
for tid in ids:
    assert tid in text, f'MISSING: {tid}'
    print(f'  {tid}: found')
print('All new test IDs present')
"

# 3. Stale DNS-fallback references gone
python3 -c "
text = open('portal5_acceptance_v4.py').read()
assert 'portal-pipeline:9099' not in text, 'STALE: portal-pipeline:9099 still present'
assert 'Docker-internal hostname' not in text, 'STALE: Docker-internal hostname comment'
print('Stale DNS-fallback references cleared')
"

# 4. S3-17 now has a record() call
python3 -c "
import re
text = open('portal5_acceptance_v4.py').read()
assert re.search(r'record\([^)]*\"S3-17\"', text, re.DOTALL), 'S3-17 record() missing'
print('S3-17 has record() call')
"

# 5. ID ordering correct (each new ID after its predecessor)
python3 -c "
text = open('portal5_acceptance_v4.py').read()
pairs = [('S2-15','S2-16'),('S1-07','S1-08'),('S1-08','S1-09'),
         ('S1-09','S1-10'),('S1-10','S1-11'),('S3-19','S3-20'),
         ('S14-12','S14-13'),('S14-13','S14-14'),
         ('S22-04','S22-05'),('S22-05','S22-06')]
for a,b in pairs:
    ia = text.index(f'\"{ a }\"'); ib = text.index(f'\"{ b }\"')
    assert ia < ib, f'{b} must come after {a}'
print('All test ID ordering correct')
"

# 6. Execute guide has target and new test refs
python3 -c "
text = open('PORTAL5_ACCEPTANCE_V4_EXECUTE.md').read()
for s in ['215', 'S22-06', 'S1-10', 'hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF', 'localhost:9099']:
    assert s in text, f'MISSING in execute guide: {s}'
print('Execute guide updated correctly')
"

# 7. Run 8 changelog entry in docstring
python3 -c "
text = open('portal5_acceptance_v4.py').read()
assert 'Run 8 fixes (2026-04-07)' in text
print('Changelog entry present')
"
```

---

## Expected Run 8 Delta from Run 7

| Section | Change | Delta |
|---|---|---|
| S0 | S0-01/S0-03/S0-04 INFO→PASS | +3 PASS −3 INFO |
| S1 | S1-05 INFO→PASS; S1-08/09/10/11 new | +5 PASS −1 INFO |
| S2 | S2-15 INFO→PASS (or silent); S2-16 new | +2 PASS −1 INFO |
| S3 | S3-17 now records; S3-20 new | +2 PASS |
| S11 | S11-01b INFO removed | −1 INFO |
| S12 | S12-04 INFO→PASS | +1 PASS −1 INFO |
| S14 | S14-13/S14-14 new | +2 PASS |
| S17 | S17-00 INFO removed (silent when no --rebuild) | −1 INFO |
| S20 | S20-01/04 silent (was INFO); S20-02 WARN→PASS | +1 PASS −2 INFO −1 WARN |
| S22 | S22-05/S22-06 new | +2 PASS |

**Net: +18 PASS −1 WARN −9 INFO → 222 PASS · 0 WARN · 0 INFO · 0 FAIL · 0 BLOCKED**

> S22-06 records WARN if `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` is not pulled.
> Pull it before Run 8 to reach the full PASS count.

---

## Commit Message

```
test(acceptance): run 8 prep — v6.0 feature coverage + infra fixes

- S20-02/05: remove DNS-fallback dead code (dispatcher localhost:9099)
- S3-17: restore missing record() on content-aware routing dead call
- S3-20: SPL keyword routing boundary test (auto-spl not auto-coding)
- S2-16: Open WebUI bind address / ENABLE_REMOTE_ACCESS assertion
- S1-08/09: routing_descriptions.json + routing_examples.json checks (P5-FUT-006)
- S1-10: MODEL_MEMORY covers ALL_MODELS assertion (P5-FUT-009)
- S1-11: LLM router wired into router_pipe.py static check
- S14-13/14: .env.example ENABLE_REMOTE_ACCESS + LLM_ROUTER_ENABLED
- S22-05: admission control source + /health/memory live (P5-FUT-009)
- S22-06: LLM router live classification via hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF (P5-FUT-006)
- PORTAL5_ACCEPTANCE_V4_EXECUTE.md: target 222P/0W/0F, step 2/3 notes

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

## Scope Boundary

| In scope | Out of scope |
|---|---|
| `portal5_acceptance_v4.py` | `portal_pipeline/**` |
| `PORTAL5_ACCEPTANCE_V4_EXECUTE.md` | `portal_mcp/**`, `config/personas/**` |
| | `scripts/mlx-proxy.py` |
| | `portal_pipeline/router_pipe.py` |
| | `config/backends.yaml`, `deploy/`, `Dockerfile.*` |
| | `docs/HOWTO.md`, `imports/openwebui/**` |
| | `portal5_acceptance_comfyui.py` |
