"""Unit tests for the reranker MCP service."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_mlx_embeddings():
    with patch("portal_mcp.rag.reranker_mcp._ensure_loaded") as mock_load:
        mock_model = MagicMock()
        mock_processor = MagicMock()
        mock_load.return_value = (mock_model, mock_processor)

        with patch("portal_mcp.rag.reranker_mcp.generate") as mock_gen:
            mock_output = MagicMock()
            # Return scores attr so the primary path is exercised
            mock_output.scores = [0.9, 0.5, 0.1]
            mock_gen.return_value = mock_output

            with patch("portal_mcp.rag.reranker_mcp.mx") as mock_mx:
                mock_mx.array.return_value.tolist.return_value = [0.9, 0.5, 0.1]

                yield mock_load, mock_gen


def test_rerank_empty_documents_returns_empty():
    from portal_mcp.rag.reranker_mcp import rerank

    result = rerank("query", [], top_n=5)
    assert result == []


def test_rerank_returns_sorted_by_score(mock_mlx_embeddings):
    from portal_mcp.rag.reranker_mcp import rerank

    docs = ["doc1", "doc2", "doc3"]
    result = rerank("query", docs, top_n=2)
    assert len(result) == 2
    assert all("score" in r for r in result)
    assert all("original_index" in r for r in result)
    assert result[0]["score"] >= result[1]["score"]


def test_rerank_top_n_respected(mock_mlx_embeddings):
    from portal_mcp.rag.reranker_mcp import rerank

    docs = ["doc1", "doc2", "doc3"]
    result = rerank("query", docs, top_n=2)
    assert len(result) == 2


def test_rerank_top_n_none_returns_all(mock_mlx_embeddings):
    from portal_mcp.rag.reranker_mcp import rerank

    docs = ["doc1", "doc2", "doc3"]
    result = rerank("query", docs, top_n=None)
    assert len(result) == 3
