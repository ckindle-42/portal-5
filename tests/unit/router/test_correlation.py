import logging

import httpx

from portal.platform.inference.router.correlation import (
    CorrelationIdLogFilter,
    get_correlation_id,
    new_correlation_id,
    set_correlation_id,
    workspace_request_kwargs,
)


def test_new_id_shape():
    cid = new_correlation_id()
    assert cid.startswith("p5-") and len(cid) == 15


def test_set_get_roundtrip():
    set_correlation_id("p5-abcdef012345")
    assert get_correlation_id() == "p5-abcdef012345"


def test_filter_stamps_record():
    set_correlation_id("p5-testcid00000")
    rec = logging.LogRecord("n", logging.INFO, __file__, 1, "m", None, None)
    assert CorrelationIdLogFilter().filter(rec) is True
    assert rec.correlation_id == "p5-testcid00000"


def test_filter_dash_when_unset():
    set_correlation_id("")
    rec = logging.LogRecord("n", logging.INFO, __file__, 1, "m", None, None)
    CorrelationIdLogFilter().filter(rec)
    assert rec.correlation_id == "-"


async def test_workspace_request_kwargs_tag_only_httpx_clients():
    async with httpx.AsyncClient() as client:
        assert workspace_request_kwargs(client, "hunt-reasoning") == {
            "extensions": {"portal_workspace_id": "hunt-reasoning"}
        }
        assert workspace_request_kwargs(client, "") == {}
    assert workspace_request_kwargs(object(), "hunt-reasoning") == {}
