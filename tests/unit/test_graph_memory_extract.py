"""Graph memory extraction failures stay observable without failing the write."""

import asyncio

import httpx

from portal.platform.memory import graph_memory


def test_extract_logs_and_counts_http_status_failure(monkeypatch, caplog):
    client_cls = httpx.AsyncClient

    def client_factory(*, timeout):
        def handler(request):
            return httpx.Response(404, json={"error": "model missing"}, request=request)

        return client_cls(transport=httpx.MockTransport(handler), timeout=timeout)

    before = graph_memory._EXTRACT_FAILURES.labels(reason="http_404")._value.get()
    monkeypatch.setattr(graph_memory.httpx, "AsyncClient", client_factory)

    result = asyncio.run(graph_memory._extract("Portal5 and NERC CIP."))

    assert result == {"entities": [], "relations": []}
    assert "status=404" in caplog.text
    assert graph_memory._EXTRACT_FAILURES.labels(reason="http_404")._value.get() == before + 1
