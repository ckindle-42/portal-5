"""Open WebUI's embedding prefixes are the EG2 contract's, byte for byte (TASK_EG2_CUTOVER_V1 C3).

Open WebUI prepends RAG_EMBEDDING_{QUERY,CONTENT}_PREFIX verbatim, so a dropped trailing space or
a retyped separator silently moves every stored chunk or query out of the measured space."""

from __future__ import annotations

from pathlib import Path

import yaml

from portal.platform.embedding.contract import Role, Task, format_text

COMPOSE = Path(__file__).resolve().parents[2] / "deploy" / "portal-5" / "docker-compose.yml"


def _owui_env() -> dict[str, str]:
    svc = yaml.safe_load(COMPOSE.read_text())["services"]["open-webui"]
    return dict(item.split("=", 1) for item in svc["environment"])


def test_owui_prefixes_equal_contract() -> None:
    env = _owui_env()
    assert env["RAG_EMBEDDING_QUERY_PREFIX"] == format_text("", Task.SEARCH, Role.QUERY)
    assert env["RAG_EMBEDDING_CONTENT_PREFIX"] == format_text("", Task.SEARCH, Role.DOCUMENT)
    assert "RAG_EMBEDDING_PREFIX_FIELD_NAME" not in env  # unset = OWUI concatenates the prefix


def test_owui_embeds_with_eg2() -> None:
    env = _owui_env()
    assert env["RAG_OPENAI_API_BASE_URL"].endswith(":8946/v1")
    assert env["RAG_EMBEDDING_MODEL"] == "google/embeddinggemma-2"
