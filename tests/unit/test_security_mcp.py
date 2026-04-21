"""tests/unit/test_security_mcp.py

Unit tests for the Security MCP server (portal_mcp/security/security_mcp.py).
Tests the /health endpoint and classify_vulnerability tool logic.

Since torch + transformers are heavy deps that may not be installed in CI,
all tests mock these dependencies. The FastAPI app and tool logic are tested
without network or Docker.

Tests skip gracefully when portal_mcp.security is not importable.
"""

from __future__ import annotations

import sys
import types

import pytest

sys.path.insert(0, ".")

# ── Mock torch + transformers before importing the security module ─────────
# The security MCP imports torch and transformers at module level.
# We inject lightweight mocks so the module loads without GPU/ML deps.


def _mock_torch():
    """Create a minimal torch mock for testing."""
    torch_mock = types.ModuleType("torch")

    class _Scalar:
        """Wraps a float so .item() works — mimics torch scalar tensor."""

        def __init__(self, val):
            self._val = float(val)

        def item(self):
            return self._val

        def __repr__(self):
            return f"_Scalar({self._val})"

    class FakeTensor:
        """Minimal tensor mock supporting indexing, item(), and iteration."""

        def __init__(self, data):
            self._data = data

        def item(self):
            """Return scalar value — works for 0-d and 1-element tensors."""
            if isinstance(self._data, (int, float)):
                return float(self._data)
            if isinstance(self._data, list) and len(self._data) == 1:
                    val = self._data[0]
                    if hasattr(val, "item"):
                        return val.item()
                    return float(val)
            return float(self._data)

        def __getitem__(self, idx):
            if isinstance(idx, int):
                val = self._data[idx]
                if isinstance(val, list):
                    return FakeTensor(val)
                return _Scalar(val)  # Leaf value gets .item()
            return FakeTensor(self._data[idx])

        def __iter__(self):
            if isinstance(self._data, list):
                for v in self._data:
                    if isinstance(v, list):
                        yield FakeTensor(v)
                    else:
                        yield _Scalar(v)

    class FakeOutputs:
        def __init__(self):
            self.logits = FakeTensor([[0.05, 0.10, 0.70, 0.15]])

    def fake_tensor(data, **kwargs):
        return FakeTensor(data)

    def fake_argmax(tensor, dim=None):
        return types.SimpleNamespace(item=lambda: 2)

    # Mock nn.functional
    nn_module = types.ModuleType("torch.nn")
    functional = types.ModuleType("torch.nn.functional")

    def fake_softmax(logits, dim=None):
        return FakeTensor([[0.05, 0.10, 0.70, 0.15]])

    functional.softmax = fake_softmax
    nn_module.functional = functional

    torch_mock.tensor = fake_tensor
    torch_mock.argmax = fake_argmax
    torch_mock.no_grad = lambda: _NoGradContext()
    torch_mock.nn = nn_module

    # Store FakeOutputs for transformers mock
    torch_mock._FakeOutputs = FakeOutputs

    return torch_mock


class _NoGradContext:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _make_transformers_mock(torch_mock):
    """Create a transformers mock that uses the torch mock."""

    class FakeTokenizer:
        def __call__(self, text, **kwargs):
            return {"input_ids": [[1, 2, 3]], "attention_mask": [[1, 1, 1]]}

    class FakeModel:
        def eval(self):
            return self

        def __call__(self, **kwargs):
            return torch_mock._FakeOutputs()

    transformers_mock = types.ModuleType("transformers")

    class AutoTokenizer:
        @staticmethod
        def from_pretrained(name, **kwargs):
            return FakeTokenizer()

    class AutoModelForSequenceClassification:
        @staticmethod
        def from_pretrained(name, **kwargs):
            return FakeModel()

    transformers_mock.AutoTokenizer = AutoTokenizer
    transformers_mock.AutoModelForSequenceClassification = AutoModelForSequenceClassification

    return transformers_mock


# Install mocks before import
if "torch" not in sys.modules:
    _torch = _mock_torch()
    sys.modules["torch"] = _torch
    sys.modules["torch.nn"] = _torch.nn
    sys.modules["torch.nn.functional"] = _torch.nn.functional
if "transformers" not in sys.modules:
    sys.modules["transformers"] = _make_transformers_mock(sys.modules["torch"])

# Guard: skip if portal_mcp.security is not importable
pytest.importorskip(
    "portal_mcp.security.security_mcp",
    reason="portal_mcp.security not importable — run: pip install -e '.[dev,mcp]'",
)


def get_security_app():
    """Get the security MCP server's Starlette ASGI app.

    streamable_http_app() can only be called once per mcp instance, so we
    create it once and reuse across all tests in this module.
    """
    from portal_mcp.security.security_mcp import mcp

    return mcp.streamable_http_app()


# Create the app once — StreamableHTTPSessionManager is single-use
_APP = get_security_app()


class TestSecurityHealthEndpoint:
    """Test /health on the security MCP server."""

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        with TestClient(_APP) as c:
            yield c

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_correct_service(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"
        assert data["service"] == "security-mcp"

    def test_health_returns_port(self, client):
        data = client.get("/health").json()
        assert "port" in data
        assert isinstance(data["port"], int)


class TestClassifyVulnerability:
    """Test classify_vulnerability tool with mocked ML model."""

    def test_returns_severity_label(self):
        """classify_vulnerability must return a severity label."""
        from portal_mcp.security.security_mcp import classify_vulnerability

        result = classify_vulnerability(
            "Remote code execution via crafted HTTP request in Apache 2.4.x"
        )
        assert "severity" in result
        assert result["severity"] in ("low", "medium", "high", "critical")

    def test_returns_confidence_score(self):
        """classify_vulnerability must return a confidence score between 0 and 1."""
        from portal_mcp.security.security_mcp import classify_vulnerability

        result = classify_vulnerability(
            "Buffer overflow in OpenSSL allows remote attackers to execute arbitrary code"
        )
        assert "confidence" in result
        assert 0.0 <= result["confidence"] <= 1.0

    def test_returns_all_probabilities(self):
        """classify_vulnerability must return probabilities for all 4 severity levels."""
        from portal_mcp.security.security_mcp import classify_vulnerability

        result = classify_vulnerability(
            "Cross-site scripting vulnerability in login form"
        )
        assert "probabilities" in result
        probs = result["probabilities"]
        assert set(probs.keys()) == {"low", "medium", "high", "critical"}
        total = sum(probs.values())
        assert abs(total - 1.0) < 0.01, f"Probabilities should sum to ~1.0, got {total}"

    def test_returns_model_name(self):
        """classify_vulnerability must return the model name used."""
        from portal_mcp.security.security_mcp import classify_vulnerability

        result = classify_vulnerability("CVE-2024-1234: denial of service")
        assert "model" in result
        assert "roberta" in result["model"].lower() or "vulnerability" in result["model"].lower()

    def test_empty_description_handled(self):
        """Empty input should not crash — returns a result dict."""
        from portal_mcp.security.security_mcp import classify_vulnerability

        result = classify_vulnerability("")
        assert isinstance(result, dict)
        assert "severity" in result

    def test_long_description_truncated(self):
        """Descriptions exceeding 512 tokens should be truncated, not crash."""
        from portal_mcp.security.security_mcp import classify_vulnerability

        long_desc = "vulnerability " * 500  # Way over 512 tokens
        result = classify_vulnerability(long_desc)
        assert isinstance(result, dict)
        assert "severity" in result


class TestEnsureModel:
    """Test the lazy model loading behavior."""

    def test_ensure_model_is_callable(self):
        """_ensure_model should be a callable function."""
        from portal_mcp.security.security_mcp import _ensure_model

        assert callable(_ensure_model)

    def test_ensure_model_loads_only_once(self):
        """Calling _ensure_model twice should not reload the model."""
        from portal_mcp.security import security_mcp

        # Reset state
        security_mcp._model = None
        security_mcp._tokenizer = None

        security_mcp._ensure_model()
        model1 = security_mcp._model
        tokenizer1 = security_mcp._tokenizer

        security_mcp._ensure_model()
        model2 = security_mcp._model
        tokenizer2 = security_mcp._tokenizer

        assert model1 is model2, "Model should not be reloaded on second call"
        assert tokenizer1 is tokenizer2, "Tokenizer should not be reloaded on second call"
