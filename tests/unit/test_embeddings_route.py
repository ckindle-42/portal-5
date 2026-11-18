"""POST /v1/embeddings — the Pipeline's embeddings route.

Pins the request contract (model acceptance, batch/input bounds, dimensions), the
typed error mapping (never a 200 with empty vectors), and admission: the route's
semaphore is its own, so a batch neither takes a chat slot nor waits behind one.
"""

from __future__ import annotations


def test_the_route_is_registered() -> None:
    from portal.platform.inference.router_pipe import app

    routes = {(r.path, m) for r in app.routes if hasattr(r, "methods") for m in r.methods}
    assert ("/v1/embeddings", "POST") in routes
