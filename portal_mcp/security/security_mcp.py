"""Portal 5 — Security MCP Tool Server.

Provides vulnerability severity classification using CIRCL's VLAI RoBERTa model.
Port: 8919 (configurable via SECURITY_MCP_PORT or MCP_PORT env var)
"""

from __future__ import annotations

import logging
import os

import torch
from starlette.responses import JSONResponse
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Vendored FastMCP
from portal_mcp.mcp_server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ── Model Configuration ──────────────────────────────────────────────────────
_MODEL_NAME = "CIRCL/vulnerability-severity-classification-roberta-base"
_LABELS = ["low", "medium", "high", "critical"]

# Lazy-loaded globals (loaded on first tool call, not import time)
_tokenizer = None
_model = None


def _ensure_model():
    """Load the VLAI model on first use. Downloads from HuggingFace if not cached."""
    global _tokenizer, _model
    if _model is not None:
        return
    logger.info("Loading VLAI severity classifier: %s", _MODEL_NAME)
    _tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME)
    _model = AutoModelForSequenceClassification.from_pretrained(_MODEL_NAME)
    _model.eval()
    logger.info("VLAI model loaded successfully (%d labels)", len(_LABELS))


# ── MCP Server Setup ─────────────────────────────────────────────────────────
_port = int(os.environ.get("SECURITY_MCP_PORT") or os.environ.get("MCP_PORT", "8919"))

mcp = FastMCP(
    "Portal Security Tools",
    instructions="Vulnerability severity classification and security analysis tools",
    port=_port,
)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "security-mcp", "port": _port})


@mcp.tool()
def classify_vulnerability(description: str) -> dict:
    """Classify a vulnerability description into severity level (low/medium/high/critical).

    Uses CIRCL's VLAI model (RoBERTa-base, 82% accuracy, trained on 600K+ CVEs).
    Input: CVE or vulnerability description text.
    Returns: severity label, confidence score, and all class probabilities.

    Args:
        description: The vulnerability description text to classify.
                     Works best with CVE-style descriptions (1-3 sentences).
    """
    _ensure_model()

    inputs = _tokenizer(description, return_tensors="pt", truncation=True, padding=True, max_length=512)

    with torch.no_grad():
        outputs = _model(**inputs)
        probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)

    predicted_idx = torch.argmax(probabilities, dim=-1).item()
    confidence = probabilities[0][predicted_idx].item()

    return {
        "severity": _LABELS[predicted_idx],
        "confidence": round(confidence, 4),
        "probabilities": {
            label: round(prob.item(), 4)
            for label, prob in zip(_LABELS, probabilities[0], strict=True)
        },
        "model": _MODEL_NAME,
    }


# ── Serve ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
