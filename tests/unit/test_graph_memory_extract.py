"""Graph memory extraction failures stay observable without failing the write."""

import asyncio

import httpx

from portal.platform.memory import graph_memory


def test_extract_logs_and_counts_http_status_failure(monkeypatch, caplog):
    client_cls = httpx.AsyncClient
    requests = []

    def client_factory(*, timeout):
        def handler(request):
            requests.append(request)
            return httpx.Response(404, json={"error": "model missing"}, request=request)

        return client_cls(transport=httpx.MockTransport(handler), timeout=timeout)

    before = graph_memory._EXTRACT_FAILURES.labels(reason="http_404")._value.get()
    monkeypatch.setattr(graph_memory, "OLLAMA_CHAT", "http://portal-pipeline.test/ollama/api/chat")
    monkeypatch.setenv("PIPELINE_API_KEY", "memory-test-key")
    monkeypatch.setattr(graph_memory.httpx, "AsyncClient", client_factory)

    result = asyncio.run(graph_memory._extract("Portal5 and NERC CIP."))

    assert result == {"entities": [], "relations": []}
    assert "status=404" in caplog.text
    assert requests[0].url.path == "/ollama/api/chat"
    assert requests[0].headers["authorization"] == "Bearer memory-test-key"
    assert graph_memory._EXTRACT_FAILURES.labels(reason="http_404")._value.get() == before + 1
