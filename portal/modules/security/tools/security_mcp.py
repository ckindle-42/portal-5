"""Portal 5 — Security MCP Tool Server.

Provides vulnerability severity classification using CIRCL's VLAI RoBERTa model.
Port: 8919 (configurable via SECURITY_MCP_PORT or MCP_PORT env var)
"""

from __future__ import annotations

import logging
import os

import torch

# Vendored FastMCP
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from portal.modules.security.core.perception import LabPerception, OutOfScopeError

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
    host="0.0.0.0",
    instructions="Vulnerability severity classification and security analysis tools",
    port=_port,
)

# Pre-warm the VLAI model at startup so the first tool call doesn't stall.
# Gate behind SECURITY_MCP_PREWARM (default "1" — production behavior unchanged).
# Set to "0" for faster dev startup; first call will load on demand.
if os.environ.get("SECURITY_MCP_PREWARM", "1") == "1":
    try:
        _ensure_model()
        logger.info("VLAI model pre-warm complete")
    except Exception as e:
        logger.warning("VLAI model pre-warm failed (will retry on first call): %s", e)


TOOLS_MANIFEST = [
    {
        "name": "classify_vulnerability",
        "description": (
            "Classify a vulnerability description into severity level "
            "(low/medium/high/critical) using CIRCL's VLAI RoBERTa model. "
            "Returns severity label, confidence score, and all class probabilities."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "CVE or vulnerability description text (1-3 sentences).",
                }
            },
            "required": ["description"],
        },
    },
    {
        "name": "lab_perception",
        "description": (
            "Bounded live-state enumerator for the RBP lab (10.10.11.0/24 only). "
            "Returns a live observation delta (services up, reachability, changed "
            "hosts) for the given hosts. Any host outside the lab CIDR is rejected "
            "before any probe leaves the box."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "hosts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lab host IPs to enumerate (must be inside 10.10.11.0/24).",
                }
            },
            "required": ["hosts"],
        },
    },
]


# ── Readiness endpoint ───────────────────────────────────────────────────────
@mcp.custom_route("/ready", methods=["GET"])
async def ready(request):
    return JSONResponse(
        {
            "model_loaded": _model is not None,
            "port": _port,
            "prewarm_enabled": os.environ.get("SECURITY_MCP_PREWARM", "1") == "1",
        }
    )


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "security-mcp", "port": _port})


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


@mcp.custom_route("/tools/{tool_name}", methods=["POST"])
async def invoke_tool(request):
    """REST dispatch endpoint used by portal-pipeline tool_registry."""
    tool_name = request.path_params.get("tool_name", "")
    try:
        body = await request.json()
    except Exception:
        body = {}
    arguments = body.get("arguments", body)
    if tool_name == "classify_vulnerability":
        try:
            result = classify_vulnerability(**arguments)
            return JSONResponse(result)
        except TypeError as e:
            return JSONResponse({"error": f"Invalid arguments: {e}"}, status_code=400)
        except Exception as e:
            logger.error("classify_vulnerability failed: %s", e, exc_info=True)
            return JSONResponse({"error": str(e)}, status_code=500)
    if tool_name == "lab_perception":
        try:
            result = lab_perception(**arguments)
            return JSONResponse(result)
        except OutOfScopeError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except TypeError as e:
            return JSONResponse({"error": f"Invalid arguments: {e}"}, status_code=400)
        except Exception as e:
            logger.error("lab_perception failed: %s", e, exc_info=True)
            return JSONResponse({"error": str(e)}, status_code=500)
    return JSONResponse({"error": f"Unknown tool: {tool_name}"}, status_code=404)


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

    inputs = _tokenizer(
        description, return_tensors="pt", truncation=True, padding=True, max_length=512
    )

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


def _lab_perception_prober(hosts: list[str]) -> dict:
    """Bind LabPerception to the existing curated real actuation path
    (`lab.lab_dispatch`) — no new offensive primitive (I2), just recon."""
    from portal.modules.security.core import lab

    state: dict[str, str] = {}
    services: list[dict] = []
    for host in hosts:
        raw = lab.lab_dispatch("run_nmap_scan", {"target": host}, dry_run=False)
        state[host] = raw
        services.append({"host": host, "raw": raw})
    return {"services": services, "reachable": [], "state": state}


@mcp.tool()
def lab_perception(hosts: list[str]) -> dict:
    """Bounded live-state enumerator for the RBP lab (DESIGN_EMERGENT_LAB_AGENT_V2 Δ1).

    Returns a live observation delta (services, reachability, changed hosts)
    for the given hosts. Any host outside 10.10.11.0/24 is rejected before any
    probe leaves the box (invariant I1) — the guard runs first, always.
    """
    delta = LabPerception(prober=_lab_perception_prober).enumerate(hosts)
    return delta.to_observation()


# ── Serve ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
