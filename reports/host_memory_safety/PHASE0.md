# Host Memory Safety V1 — Phase 0 live truth

Captured 2026-10-07 on the live production Mac, arm64, macOS 27.0.0. HEAD was `eed5b451b9fc88f4ff9145a3efe71edef8ceb271`.

## Engines and host memory

`ollama ps`:

```text
NAME                                                               ID              SIZE      PROCESSOR    CONTEXT    RUNNER      UNTIL
hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M-ctx2k    160bbe54d5aa    5.4 GB    100% GPU     2048       llamacpp    Forever
```

oMLX `GET http://127.0.0.1:8085/v1/models/status` (Bearer key supplied; key omitted) at 11:34:48 UTC:

```json
{"final_ceiling":44564870782,"current_model_memory":0,"model_count":44,"loaded_count":0,"models":[]}
```

At 11:35:07 UTC, a second read returned `final_ceiling=44513293950`, `current_model_memory=0`, `loaded_count=0`, and no loaded or loading models.

`sysctl vm.swapusage`:

```text
vm.swapusage: total = 10240.00M  used = 9460.62M  free = 779.38M  (encrypted)
```

`memory_pressure -Q`:

```text
The system has 68719476736 (4194304 pages with a page size of 16384).
System-wide memory free percentage: 93%
```

Free swap is below the required watchdog floor of 1024 MiB despite `memory_pressure` reporting 93% free. This is a live safety finding and must be resolved or explicitly accounted for before multi-model live tests.

## Log sizes

`stat -f '%N|%z bytes|%b blocks' /opt/homebrew/var/log/ollama.log /opt/homebrew/var/log/omlx.log ~/.portal5/logs/*.log`:

```text
/opt/homebrew/var/log/ollama.log|3341656322 bytes|6549400 blocks
/opt/homebrew/var/log/omlx.log|30847866 bytes|61496 blocks
/Users/chris/.portal5/logs/acceptance-overnight-20260617T232114.log|0 bytes|0 blocks
/Users/chris/.portal5/logs/auk.log|47192 bytes|96 blocks
/Users/chris/.portal5/logs/compliance-mcp.log|8306271 bytes|17800 blocks
/Users/chris/.portal5/logs/data-mcp.log|170931 bytes|368 blocks
/Users/chris/.portal5/logs/detection-mcp.log|168762 bytes|360 blocks
/Users/chris/.portal5/logs/detections-mcp.log|786718 bytes|1648 blocks
/Users/chris/.portal5/logs/embedding-server-err.log|2179491 bytes|6168 blocks
/Users/chris/.portal5/logs/embedding-server.log|12630 bytes|32 blocks
/Users/chris/.portal5/logs/engine-update.launchd.log|1512 bytes|8 blocks
/Users/chris/.portal5/logs/icsot-mcp.log|168990 bytes|360 blocks
/Users/chris/.portal5/logs/lab-callback-relay-err.log|144 bytes|8 blocks
/Users/chris/.portal5/logs/lab-callback-relay.log|0 bytes|0 blocks
/Users/chris/.portal5/logs/laguna-pull.log|733 bytes|8 blocks
/Users/chris/.portal5/logs/mflux.log|343368 bytes|792 blocks
/Users/chris/.portal5/logs/mitre-mcp.log|789618 bytes|1648 blocks
/Users/chris/.portal5/logs/mlx-speech.log|6611772 bytes|14256 blocks
/Users/chris/.portal5/logs/mlx-transcribe.log|1275169 bytes|4368 blocks
/Users/chris/.portal5/logs/music-minimax.log|431571 bytes|952 blocks
/Users/chris/.portal5/logs/netforensics-mcp.log|168592 bytes|360 blocks
/Users/chris/.portal5/logs/obscura-update-check.launchd.log|122 bytes|8 blocks
/Users/chris/.portal5/logs/omlx-watchdog.launchd.log|0 bytes|0 blocks
/Users/chris/.portal5/logs/omlx-watchdog.log|6059 bytes|16 blocks
/Users/chris/.portal5/logs/pipeline-mcp.log|1026515 bytes|2112 blocks
/Users/chris/.portal5/logs/splash-forwarder.log|70297 bytes|144 blocks
/Users/chris/.portal5/logs/splash-serve-closeout.log|6508 bytes|16 blocks
/Users/chris/.portal5/logs/splash-serve-q38.log|4251 bytes|16 blocks
/Users/chris/.portal5/logs/splash-serve.log|137443 bytes|272 blocks
/Users/chris/.portal5/logs/uat-overnight.log|86610 bytes|176 blocks
/Users/chris/.portal5/logs/update-check.launchd.log|4823 bytes|16 blocks
/Users/chris/.portal5/logs/video-mlx.log|297716 bytes|696 blocks
/Users/chris/.portal5/logs/vl-retrieval.log|3343706 bytes|6952 blocks
/Users/chris/.portal5/logs/vulnintel-mcp.log|171574 bytes|368 blocks
/Users/chris/.portal5/logs/whisper-pull.log|386 bytes|8 blocks
/Users/chris/.portal5/logs/wiki-mcp.log|791671 bytes|1656 blocks
```

## Extraction model

`ollama list | rg 'gemma4:e4b'`:

```text
gemma4:e4b-it-qat-ctx8k                                                                                      06c1d2c9c195    6.1 GB    12 days ago
gemma4:e4b-it-qat                                                                                            ee6656371218    6.1 GB    5 weeks ago
```

`docker exec portal5-mcp-memory printenv MEMORY_EXTRACT_MODEL`:

```text
gemma4:e4b-it-q4_K_M
```

One raw extraction request to the MCP's configured Ollama endpoint returned:

```text
status= 404 body= {"error":"model 'gemma4:e4b-it-q4_K_M' not found"}
```

No memory was written for this extraction-only probe.

## Pipeline memory reading

`docker exec portal5-pipeline python -c "from portal.platform.inference.router.monitor import memory_pct; print(memory_pct())"`:

```text
0.0
```

## Direct native Ollama endpoint inventory

Command: `rg -n --glob '*.py' '/api/(chat|generate|embed)' portal`. The raw inventory is appended below; comments/docstrings as well as runtime callers are included for review.

```text
portal/platform/inference/router/validation.py:256:    toggle as ``think`` (Ollama-native, /api/chat only) plus, for ``think:
portal/platform/inference/router/validation.py:300:    # reach the model because Ollama backends are served from native /api/chat
portal/platform/inference/router/validation.py:318:    # CURRENT (2026-09-25): Ollama backends are served from native /api/chat by
portal/platform/inference/router/validation.py:324:    # `think` is Ollama's NATIVE knob and works only on /api/chat. We dispatch
portal/platform/inference/router/lifespan.py:159:            # oMLX has no /api/generate nor keep_alive — its EnginePool owns
portal/platform/inference/router/lifespan.py:170:            warmup_url = f"{backend.url.rstrip('/')}/api/generate"
portal/platform/inference/router/lifespan.py:303:    # Ollama backends are served from native /api/chat behind the unchanged
portal/platform/memory/graph_memory.py:31:OLLAMA_CHAT = os.environ.get("OLLAMA_CHAT_URL", "http://localhost:11434/api/chat")
portal/platform/inference/streaming_client.py:22:* native Ollama (``/api/chat``): JSON lines with a FULL ``tool_calls`` array
portal/platform/inference/streaming_client.py:125:    """Parse one Ollama /api/chat JSON line into ``turn``. True when done."""
portal/modules/eval/persona_matrix/ollama_client.py:229:            f"{OLLAMA_URL}/api/generate",
portal/platform/inference/router/backend_introspect.py:129:                    await client.post(f"{url}/api/generate", json={"model": name, "keep_alive": 0})
portal/platform/inference/router/routing.py:528:        Multi-line prompt string, ready to send to ``/api/generate``.
portal/platform/inference/router/routing.py:634:            f"{_LLM_ROUTER_OLLAMA_URL}/api/generate",
portal/platform/inference/router/routing.py:669:    ``/api/generate`` with ``format: _ROUTER_JSON_SCHEMA``, parses the
portal/platform/inference/router/routing.py:740:                f"{_LLM_ROUTER_OLLAMA_URL}/api/generate",
portal/platform/inference/router/council.py:52:    native ``/api/chat`` but oMLX ignores it silently: no error, no
portal/modules/research/tools/rag_multimodal.py:90:                f"{OLLAMA_URL}/api/generate",
portal/modules/compliance/core/council.py:43:# disabling thought; /api/chat separates the channels).
portal/modules/compliance/core/council.py:269:    native ``/api/chat`` the trace comes back as ``message.thinking``, a
portal/platform/inference/ollama_native.py:1:"""Serve OpenAI-shaped chat requests to Ollama from its NATIVE /api/chat.
portal/platform/inference/ollama_native.py:8:``think: true`` is dropped. /api/chat honours every one of them. Every
portal/platform/inference/ollama_native.py:15:from ``/api/chat`` and translates the response back to the exact shape /v1
portal/platform/inference/ollama_native.py:46:#: Per-request sampling options /api/chat honours. Load-time options are left
portal/platform/inference/ollama_native.py:138:    """Translate OpenAI chat messages to /api/chat messages. Tool results carry
portal/platform/inference/ollama_native.py:181:    """Apply ``tool_choice`` the one way /api/chat allows — by what is offered.
portal/platform/inference/ollama_native.py:198:    """Build the /api/chat body for an OpenAI chat body."""
portal/platform/inference/ollama_native.py:203:    # OpenAI allows a bare string; /api/chat 500s on anything but an array.
portal/platform/inference/ollama_native.py:289:    """A non-streamed /api/chat response as a /v1 chat.completion."""
portal/platform/inference/ollama_native.py:317:    """Translate /api/chat NDJSON lines into /v1 SSE bytes."""
portal/platform/inference/ollama_native.py:399:    """/api/chat errors are {"error": "..."}; /v1's are {"error": {...}}."""
portal/platform/inference/ollama_native.py:463:    """Answers /v1/chat/completions for Ollama backends from /api/chat.
portal/platform/inference/ollama_native.py:527:            "POST", f"{base}/api/chat", json=native, extensions=request.extensions
portal/modules/compliance/core/reading_transport.py:3:Native ``/api/chat`` returns ``message.thinking`` separately from
portal/modules/compliance/core/reading_transport.py:83:_ENDPOINT = "http://localhost:11434/api/chat"
portal/modules/compliance/core/reading_transport.py:182:#: * A baked ``num_ctx`` is a DEFAULT, not a ceiling. ``/api/chat`` honours a
portal/modules/compliance/core/obligation_alignment.py:780:    ``/api/chat`` a reasoning trace arrives in ``message.thinking`` and cannot
portal/modules/compliance/core/transport_dialects.py:4:Ollama's native ``/api/chat`` — at a module-level constant. That is the
portal/modules/compliance/core/transport_dialects.py:85:    """Ollama's native ``/api/chat`` — the module's original and default path.
portal/modules/compliance/core/transport_dialects.py:97:        self.endpoint = f"{self.base}/api/chat"
portal/modules/compliance/core/sweep.py:464:      module's own transport fields (gemma4, real fixed body, ``/api/chat``,
portal/platform/inference/tool_preselect/preselector.py:129:            _client().post(f"{ollama_url}/api/generate", json=payload),
portal/platform/inference/tool_preselect/cli_probe.py:85:        resp = await client.post(f"{args.ollama_url}/api/generate", json=payload)
portal/modules/security/core/__init__.py:170:            f"{ollama_url}/api/chat",
portal/modules/security/core/blue.py:1139:                    f"{OLLAMA_URL}/api/chat",
portal/modules/security/core/_config.py:37:    # Explicit num_ctx for chain /api/chat calls. Ollama 0.31+ defaults num_ctx to a
portal/modules/security/core/exec_chain.py:3678:                        f"{cfg.ollama_url}/api/chat",
portal/modules/security/core/exec_chain.py:4040:                        f"{cfg.ollama_url}/api/chat",
portal/modules/security/core/agentic_blue_eval.py:312:            f"{_OLLAMA_URL}/api/chat", {}, body, is_pipeline_mode=False, idle_timeout_s=300.0
portal/platform/wiki/adapters/portal_inference.py:25:    Uses /api/generate for single-turn generation (wiki seeding).
portal/platform/wiki/adapters/portal_inference.py:44:        """Generate text via Ollama /api/generate."""
portal/platform/wiki/adapters/portal_inference.py:48:                f"{self.ollama_url}/api/generate",
portal/modules/security/core/commands/run.py:433:                        f"{ollama_url}/api/generate",
portal/modules/security/core/drift_gate.py:264:                f"{ollama_url}/api/chat",
portal/modules/security/core/intake.py:73:    instead of Ollama's native /api/generate — oMLX never reports an
portal/modules/security/core/intake.py:117:                    f"{ollama_url}/api/generate",
portal/modules/security/core/refusal.py:37:            f"{ollama_url}/api/chat",
portal/modules/security/core/refusal.py:159:    of Ollama's native /api/chat — same AUDIT_TOOL, same pass/fail criteria."""
portal/modules/security/core/refusal.py:181:                f"{OLLAMA_URL}/api/chat",
```
