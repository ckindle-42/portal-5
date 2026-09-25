"""Portal 5 — Security MCP Tool Server.

Provides vulnerability severity classification using CIRCL's VLAI RoBERTa model.
Port: 8919 (configurable via SECURITY_MCP_PORT or MCP_PORT env var)
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any, cast

import torch
from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from portal.modules.security.core.perception import (
    LabPerception,
    OutOfScopeError,
    default_lab_prober,
)

logger = logging.getLogger(__name__)

# ── Model Configuration ──────────────────────────────────────────────────────
_MODEL_NAME = "CIRCL/vulnerability-severity-classification-roberta-base"
_LABELS = ["low", "medium", "high", "critical"]

# Lazy-loaded globals (loaded on first tool call, not import time)
_tokenizer: Any = None
_model: Any = None

_VULNLLM_MODEL = os.environ.get(
    "VULNLLM_MODEL", "hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k"
)
_VULNLLM_SAMPLING = {
    "temperature": 0.7,
    "top_p": 0.8,
    "top_k": 20,
    "repeat_penalty": 1.05,
}
_VULNLLM_SYSTEM_PROMPT = "You are a helpful assistant. You should think step-by-step."
_VULNLLM_REASONING = """Please think step by step and follow the following procedure.
Step 1: understand the code and identify key instructions and program states;
Step 2: come up with the constraints on the identified instructions or states to decide if the code is vulnerable;
Step 3: Predict the actual program states and decide if it follows the constraints;
Step 4: Tell whether the code is vulnerable based on the analysis above
\n
"""
_VULNLLM_CWES = {
    "CWE-134": "Ensure that format strings are fixed and not influenced by external input.",
    "CWE-191": "Look for arithmetic operations, especially decrement operations that are performed on variables that can potentially hold minimum integer values.",
    "CWE-22": "Confirm that the code includes checks for absolute paths, using security flags, and verify that the code correctly identifies and handles absolute paths by setting errors and returning failure codes when such paths are detected.",
    "CWE-327": "Identify the use of strong, well-regarded cryptographic algorithms, and understand that the use of such algorithms mitigates vulnerabilities like CWE-327 by providing adequate cryptographic strength.",
    "CWE-367": "Identify that the benign code does not perform a separate check before using the resource, and understand that by directly attempting to use the resource, the code avoids the window of opportunity for a race condition.",
    "CWE-526": "Note the absence of conditional logic that prevents the exposure of environment variables. If the code always executes the output of an environment variable without any checks, it is likely vulnerable.",
    "CWE-121": "Ensure that both lower and upper bounds are checked before using an index to access an array, and recognize the addition of a condition of data size as a fix.",
    "CWE-23": "Recognize code that uses static, predefined strings for file paths, ensuring that no external input can influence the path construction.",
    "CWE-369": "Verify that the code includes checks to validate inputs before they are used in division operations. This includes ensuring the divisor is not zero or close to zero.",
    "CWE-400": "Ensure that input values are validated and constrained within safe limits before being used to control resource consumption.",
    "CWE-416": "Ensure that memory allocation and deallocation are handled correctly, with no operations on pointers after deallocation, and verify that any deallocated pointers are not used in subsequent operations.",
    "CWE-457": "Ensure that all elements of an array or structure are initialized before any use. This can be achieved by initializing the entire array in a loop before any other operations.",
    "CWE-476": "Ensure that pointers are validated before they are dereferenced. This includes checking if a pointer is `NULL` and handling such cases appropriately, often using conditional statements or error-handling constructs.",
    "CWE-758": "Identify code patterns where objects are used without proper initialization. Specifically, look for instances where a pointer is dereferenced to access or copy data from an uninitialized object.",
    "CWE-761": "Prefer index-based traversal over pointer arithmetic when iterating through a buffer. This ensures that the original pointer remains unchanged and can be safely freed.",
    "CWE-843": "Ensure that the type of data being accessed is consistent with the type of the variable it is pointing to.",
    "CWE-125": "Ensure that any operation involving buffers or arrays checks the boundaries before accessing elements. Look for conditions where the code might access elements beyond the allocated memory.",
    "CWE-190": "Ensure that input is validated before being used in arithmetic operations. This includes checking that the input is within a safe range to prevent overflow.",
    "CWE-787": "Identify code sections where data is written to buffers. Pay attention to calculations involving buffer sizes and offsets. Look for operations that modify buffer pointers or indices, especially in loops or conditional statements.",
}
_VULNLLM_CALLER_CWES = {
    "CWE-601": "Ensure redirects cannot be controlled by untrusted external input or point to untrusted destinations.",
    "CWE-89": "Ensure SQL queries do not use untrusted input without parameterization.",
    "CWE-798": "Ensure credentials are not hard-coded in source code.",
    "CWE-502": "Ensure untrusted data is not deserialized by unsafe object loaders.",
}
_VULNLLM_CWE_RE = re.compile(r"\bCWE-\d+\b", re.IGNORECASE)


class _TypedMCPServer(MCPServer):
    def custom_route(
        self,
        path: str,
        methods: list[str],
        name: str | None = None,
        include_in_schema: bool = True,
    ) -> Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]]:
        return cast(
            Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]],
            super().custom_route(path, methods, name=name, include_in_schema=include_in_schema),
        )


def _ensure_model() -> None:
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

mcp = _TypedMCPServer(
    "Portal Security Tools",
    instructions="Vulnerability severity classification and security analysis tools",
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
        "name": "scan_code",
        "description": (
            "Run the trained VulnLLM-R vulnerability detector against a code snippet. "
            "Returns a structured yes/no judgment and at most one CWE, preserving the "
            "raw detector answer for review."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The source-code snippet to inspect.",
                },
                "cwe_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional CWE shortlist; defaults to the trained 19-CWE policy list.",
                },
            },
            "required": ["code"],
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
async def ready(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "model_loaded": _model is not None,
            "port": _port,
            "prewarm_enabled": os.environ.get("SECURITY_MCP_PREWARM", "1") == "1",
        }
    )


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "security-mcp", "port": _port})


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request: Request) -> JSONResponse:
    return JSONResponse({"tools": TOOLS_MANIFEST})


@mcp.custom_route("/tools/{tool_name}", methods=["POST"])
async def invoke_tool(request: Request) -> JSONResponse:
    """REST dispatch endpoint used by portal-pipeline tool_registry."""
    tool_name = request.path_params.get("tool_name", "")
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        body = {}
    arguments: Any = body.get("arguments", body)
    if tool_name == "classify_vulnerability":
        try:
            result = classify_vulnerability(**arguments)
            return JSONResponse(result)
        except TypeError as e:
            return JSONResponse({"error": f"Invalid arguments: {e}"}, status_code=400)
        except Exception as e:
            logger.error("classify_vulnerability failed: %s", e, exc_info=True)
            return JSONResponse({"error": str(e)}, status_code=500)
    if tool_name == "scan_code":
        try:
            result = scan_code(**arguments)
            return JSONResponse(result)
        except TypeError as e:
            return JSONResponse({"error": f"Invalid arguments: {e}"}, status_code=400)
        except Exception as e:
            logger.error("scan_code failed: %s", e, exc_info=True)
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
def classify_vulnerability(description: str) -> dict[str, Any]:
    """Classify a vulnerability description into severity level (low/medium/high/critical).

    Uses CIRCL's VLAI model (RoBERTa-base, 82% accuracy, trained on 600K+ CVEs).
    Input: CVE or vulnerability description text.
    Returns: severity label, confidence score, and all class probabilities.

    Args:
        description: The vulnerability description text to classify.
                     Works best with CVE-style descriptions (1-3 sentences).
    """
    _ensure_model()
    tokenizer = _tokenizer
    model = _model

    inputs = tokenizer(
        description, return_tensors="pt", truncation=True, padding=True, max_length=512
    )

    with torch.no_grad():
        outputs = model(**inputs)
        probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)

    predicted_idx = int(torch.argmax(probabilities, dim=-1).item())
    confidence = float(probabilities[0][predicted_idx].item())

    return {
        "severity": _LABELS[predicted_idx],
        "confidence": round(confidence, 4),
        "probabilities": {
            label: round(float(prob.item()), 4)
            for label, prob in zip(_LABELS, probabilities[0], strict=True)
        },
        "model": _MODEL_NAME,
    }


def _vulnllm_prompt(code: str, cwe_ids: list[str] | None = None) -> str:
    """Build VulnLLM-R's trained reasoning prompt, including its CWE policy."""
    selected = cwe_ids or list(_VULNLLM_CWES)
    descriptions = {**_VULNLLM_CWES, **_VULNLLM_CALLER_CWES}
    cwe_info = "\n".join(
        f"- {cwe.upper()}: {descriptions.get(cwe.upper(), 'Assess whether the code exhibits this caller-supplied weakness.')}"
        for cwe in selected
    )
    if not cwe_info:
        cwe_info = "- No shortlist supplied; identify the most relevant CWE if one exists."
    return f"""You are an advanced vulnerability detection model. Your task is to check if a specific vulnerability exists in a given piece of code. You need to output whether the code is vulnerable and the type of vulnerability present with cwe id (CWE-xx).

## You are given the following code snippet:
```
{code}
```

You should only focus on checking and reasoning if the code contains one of the following CWEs, or other cwe if you think it is more relevant:
{cwe_info}

{_VULNLLM_REASONING}

## Final Answer
#judge: <yes/no>
#type: <vulnerability type>

## Additional Constraint:
- If `#judge: yes`, then `#type:` **must contain exactly one CWE**.
- If `#judge: yes`, the model must output **only the most probable CWE** related to the given code snippet.

## Example
- If the target function is vulnerable to a CWE-79, you should finally output:
## Final Answer
#judge: yes
#type: CWE-79

- If the target function does not contain vulnerabilities related to the given CWE, you should finally output:
## Final Answer
#judge: no
#type: N/A
"""


def _parse_vulnllm_output(raw: str) -> dict[str, Any]:
    """Parse the detector's rigid final-answer contract without losing raw text."""
    judge_match = re.search(r"#judge\s*:\s*(yes|no)\b", raw, re.IGNORECASE)
    judge = judge_match.group(1).lower() if judge_match else None
    type_match = re.search(r"#type\s*:\s*(.+)", raw, re.IGNORECASE)
    type_text = type_match.group(1).strip() if type_match else ""
    cwes = [c.upper() for c in _VULNLLM_CWE_RE.findall(type_text)]
    errors: list[str] = []
    if judge is None:
        errors.append("missing #judge yes/no")
    if judge == "yes" and len(cwes) != 1:
        errors.append("#judge yes requires exactly one CWE in #type")
    return {
        "judge": judge,
        "vulnerable": judge == "yes" if judge is not None else None,
        "cwe": cwes[0] if len(cwes) == 1 else None,
        "cwes": cwes,
        "type_text": type_text,
        "parse_errors": errors,
        "raw": raw,
    }


def _vulnllm_chat(prompt: str) -> str:
    """Call the local Ollama VulnLLM tag with the card's sampling contract."""
    base = (os.environ.get("OLLAMA_URL") or "http://localhost:11434").rstrip("/")
    payload = {
        "model": _VULNLLM_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": _VULNLLM_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "options": {**_VULNLLM_SAMPLING, "num_predict": 3072},
    }
    request = urllib.request.Request(
        f"{base}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        body = json.load(response)
    return str((body.get("message") or {}).get("content") or "")


@mcp.tool()
def scan_code(code: str, cwe_ids: list[str] | None = None) -> dict[str, Any]:
    """Detect a vulnerability in source code using VulnLLM-R's trained contract."""
    prompt = _vulnllm_prompt(code, cwe_ids)
    parsed = _parse_vulnllm_output(_vulnllm_chat(prompt))
    return {
        **parsed,
        "model": _VULNLLM_MODEL,
        "sampling": {**_VULNLLM_SAMPLING, "max_tokens": 3072},
        "prompt_contract": "VulnLLM-R reasoning_user_prompt + new_policy + our_cot",
    }


@mcp.tool()
def lab_perception(hosts: list[str]) -> dict[str, Any]:
    """Bounded live-state enumerator for the RBP lab (DESIGN_EMERGENT_LAB_AGENT_V2 Δ1).

    Returns a live observation delta (services, reachability, changed hosts)
    for the given hosts. Any host outside 10.10.11.0/24 is rejected before any
    probe leaves the box (invariant I1) — the guard runs first, always.
    """
    delta = LabPerception(prober=default_lab_prober).enumerate(hosts)
    return delta.to_observation()


# ── Serve ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=_port)
