"""Unit tests for portal.platform.mcp_host.workspace (TASK-WORKSPACE-001)."""

from __future__ import annotations

import pytest

from portal.platform.mcp_host.workspace import (
    assert_public_http_url,
)


def test_assert_public_http_url_rejects_loopback_ip_literal() -> None:
    with pytest.raises(ValueError, match="non-public address"):
        assert_public_http_url("http://127.0.0.1:8080/secret")


def test_assert_public_http_url_rejects_link_local_metadata_ip_literal() -> None:
    with pytest.raises(ValueError, match="non-public address"):
        assert_public_http_url("http://169.254.169.254/latest/meta-data/")


def test_assert_public_http_url_rejects_private_range_ip_literal() -> None:
    with pytest.raises(ValueError, match="non-public address"):
        assert_public_http_url("http://10.0.0.5/internal")


def test_assert_public_http_url_rejects_non_http_scheme() -> None:
    with pytest.raises(ValueError, match="must be http"):
        assert_public_http_url("file:///etc/passwd")
