"""S2: Service health checks."""
import time

from tests.acceptance._common import (
    GRAFANA_URL,
    MCP,
    MLX_SPEECH_URL,
    OLLAMA_URL,
    OPENWEBUI_URL,
    PIPELINE_URL,
    PROMETHEUS_URL,
    SEARXNG_URL,
    _docker_alive,
    _get,
    _ollama_models,
    record,
)


async def run() -> None:
    """S2: Service health checks."""
    print("\n━━━ S2. SERVICE HEALTH ━━━")
    sec = "S2"

    # S2-01: Docker alive
    t0 = time.time()
    alive, detail = _docker_alive()
    record(sec, "S2-01", "Docker daemon", "PASS" if alive else "FAIL", detail, t0=t0)

    # S2-02: Pipeline health
    t0 = time.time()
    code, data = await _get(f"{PIPELINE_URL}/health")
    if code == 200 and isinstance(data, dict):
        backends_total = data.get("backends_total", 0)
        backends_healthy = data.get("backends_healthy", 0)
        workspaces = data.get("workspaces", 0)
        record(
            sec,
            "S2-02",
            "Pipeline /health",
            "PASS" if backends_healthy > 0 else "WARN",
            f"backends={backends_healthy}/{backends_total}, workspaces={workspaces}",
            t0=t0,
        )
    else:
        record(sec, "S2-02", "Pipeline /health", "FAIL", f"HTTP {code}", t0=t0)

    # S2-03: Ollama health
    t0 = time.time()
    code, _ = await _get(f"{OLLAMA_URL}/api/tags")
    models = _ollama_models()
    record(
        sec,
        "S2-03",
        "Ollama",
        "PASS" if code == 200 else "FAIL",
        f"{len(models)} models" if code == 200 else f"HTTP {code}",
        t0=t0,
    )

    # S2-04: Open WebUI health
    t0 = time.time()
    code, _ = await _get(f"{OPENWEBUI_URL}/health")
    record(sec, "S2-04", "Open WebUI", "PASS" if code == 200 else "FAIL", f"HTTP {code}", t0=t0)

    # S2-05: SearXNG health
    t0 = time.time()
    code, _ = await _get(f"{SEARXNG_URL}/healthz")
    record(sec, "S2-05", "SearXNG", "PASS" if code == 200 else "WARN", f"HTTP {code}", t0=t0)

    # S2-06: Prometheus health
    t0 = time.time()
    code, _ = await _get(f"{PROMETHEUS_URL}/-/healthy")
    record(sec, "S2-06", "Prometheus", "PASS" if code == 200 else "WARN", f"HTTP {code}", t0=t0)

    # S2-07: Grafana health
    t0 = time.time()
    code, _ = await _get(f"{GRAFANA_URL}/api/health")
    record(sec, "S2-07", "Grafana", "PASS" if code == 200 else "WARN", f"HTTP {code}", t0=t0)

    # S2-08 to S2-15: MCP services
    mcp_services = [
        ("S2-08", "documents", MCP["documents"]),
        # Music MCP is host-native (not a Docker service) — requires ./launch.sh install-music
        # WARN is expected if not installed; this is not a regression
        ("S2-09", "music", MCP["music"]),
        ("S2-10", "tts", MCP["tts"]),
        ("S2-11", "whisper", MCP["whisper"]),
        ("S2-12", "sandbox", MCP["sandbox"]),
        ("S2-13", "video", MCP["video"]),
        ("S2-14", "embedding", MCP["embedding"]),
        ("S2-15", "security", MCP["security"]),
    ]
    for tid, name, port in mcp_services:
        t0 = time.time()
        code, _ = await _get(f"http://localhost:{port}/health", timeout=5)
        record(
            sec,
            tid,
            f"MCP {name} (:{port})",
            "PASS" if code == 200 else "WARN",
            f"HTTP {code}",
            t0=t0,
        )

    # S2-17: MLX Speech health
    t0 = time.time()
    code, _ = await _get(f"{MLX_SPEECH_URL}/health", timeout=5)
    record(
        sec,
        "S2-17",
        "MLX Speech",
        "PASS" if code == 200 else "INFO",
        f"HTTP {code}" if code else "not running (optional)",
        t0=t0,
    )
