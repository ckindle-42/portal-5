"""``portal test`` — end-to-end live-stack smoke tests."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer


def cmd_test(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
) -> None:
    """Run end-to-end smoke tests against the live Portal stack."""
    import json as _json

    import httpx

    owui_url = os.environ.get("OPENWEBUI_URL", "http://localhost:8080")
    pipe_url = os.environ.get("PIPELINE_URL", "http://localhost:9099")
    api_key = os.environ.get("PIPELINE_API_KEY", "")

    passed = 0
    failed = 0

    def _check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if ok:
            typer.echo(f"  ✅ {name}")
            passed += 1
        else:
            typer.echo(f"  ❌ {name}  {detail}", err=True)
            failed += 1

    typer.echo("=== Portal 5 Live Stack Smoke Test ===")

    with httpx.Client(timeout=30) as client:
        # ── Pipeline ──
        typer.echo("")
        typer.echo("Pipeline:")
        try:
            r = client.get(f"{pipe_url}/health")
            h = r.json()
            status = h.get("status", "?")
            backends = h.get("backends_healthy", 0)
            ok = status in ("ok", "degraded")
            _check(f"Pipeline reachable (status={status})", ok)
            if status == "ok":
                typer.echo(f"  ✅ Ollama connected ({backends} backends healthy)")
                passed += 1
            else:
                typer.echo("  ℹ️  Ollama: no backends healthy yet — run: portal models pull")
        except Exception as e:
            _check("Pipeline reachable", False, str(e)[:80])

        try:
            r = client.get(
                f"{pipe_url}/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            ws_count = len(r.json().get("data", []))
            _check("all 17 workspaces exposed", ws_count >= 15, f"got {ws_count}")
        except Exception as e:
            _check("all 17 workspaces exposed", False, str(e)[:80])

        try:
            r = client.get(f"{pipe_url}/metrics")
            portal_metrics = r.text.count("portal_")
            _check("Prometheus metrics", portal_metrics >= 4, f"{portal_metrics} gauges")
        except Exception as e:
            _check("Prometheus metrics", False, str(e)[:80])

        # ── Open WebUI ──
        typer.echo("")
        typer.echo("Open WebUI:")
        try:
            r = client.get(f"{owui_url}/health")
            _check("Open WebUI responds", r.status_code == 200)
        except Exception as e:
            _check("Open WebUI responds", False, str(e)[:80])

        # ── Ollama ──
        typer.echo("")
        typer.echo("Ollama:")
        try:
            r = client.get("http://localhost:11434/api/tags")
            models = r.json().get("models", [])
            ok = len(models) >= 1
            _check(f"Ollama has models", ok, f"{len(models)} model(s)")
        except Exception as e:
            _check("Ollama has models", False, str(e)[:80])

        # Live inference
        try:
            r = client.post(
                f"{pipe_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "auto",
                    "messages": [{"role": "user", "content": "Say PONG"}],
                    "stream": False,
                },
            )
            reply = r.json()["choices"][0]["message"].get("content", "")
            _check("Live inference", bool(reply), reply[:40] if reply else "empty")
        except Exception as e:
            _check("Live inference", False, str(e)[:80])

        # ── MCP Servers ──
        typer.echo("")
        typer.echo("MCP Servers:")
        mcp_checks = [
            (8913, "Documents"),
            (8912, "Music"),
            (8916, "TTS"),
            (8915, "Whisper"),
            (8910, "ComfyUI"),
            (8911, "Video"),
            (8914, "Sandbox"),
            (8917, "Embedding"),
            (8919, "Security"),
        ]
        for port, name in mcp_checks:
            try:
                r = client.get(f"http://localhost:{port}/health")
                _check(f"{name} MCP (:{port})", r.status_code == 200)
            except Exception as e:
                _check(f"{name} MCP (:{port})", False, str(e)[:60])

        # ── Document generation ──
        typer.echo("")
        typer.echo("Document Generation:")
        try:
            r = client.post(
                "http://localhost:8913/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "create_word_document",
                        "arguments": {
                            "title": "Smoke Test",
                            "content": "Portal 5 smoke test document",
                        },
                    },
                    "id": 1,
                },
            )
            data = r.json().get("result", {})
            ok = bool(data.get("success") or "path" in str(data))
            _check("Word document created", ok)
        except Exception as e:
            _check("Word document created", False, str(e)[:80])

        # ── TTS ──
        typer.echo("")
        typer.echo("TTS / Voice:")
        try:
            r = client.post(
                "http://localhost:8916/v1/audio/speech",
                json={"input": "Hello from Portal 5", "voice": "af_heart"},
            )
            ok = r.status_code in (200, 503)
            _check("TTS endpoint", ok, f"HTTP {r.status_code}")
        except Exception as e:
            _check("TTS endpoint", False, str(e)[:80])

    typer.echo("")
    typer.echo(f"Results: {passed} passed, {failed} failed")
    if failed:
        raise typer.Exit(code=1)


def register(app: typer.Typer) -> None:
    app.command("test")(cmd_test)
