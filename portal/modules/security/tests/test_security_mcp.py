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
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

sys.path.insert(0, ".")

# ── Mock torch + transformers before importing the security module ─────────
# The security MCP imports torch and transformers at module level.
# We inject lightweight mocks so the module loads without GPU/ML deps.


class _FakeScalar:
    """Wraps a float so .item() works — mimics torch scalar tensor."""

    def __init__(self, val: float) -> None:
        self._val: float = val

    def item(self) -> float:
        return self._val

    def __repr__(self) -> str:
        return f"_Scalar({self._val})"


class _FakeTensor:
    """Minimal tensor mock supporting indexing, item(), and iteration.

    Modeled as an Any-typed fake on purpose: torch is a heavy third-party dep
    that is deliberately not installed under the unit suite, so its shapes are
    not statically checkable here.
    """

    def __init__(self, data: Any) -> None:
        self._data: Any = data

    def item(self) -> float:
        """Return scalar value — works for 0-d and 1-element tensors."""
        if isinstance(self._data, (int, float)):
            return float(self._data)
        if isinstance(self._data, list) and len(self._data) == 1:
            val = self._data[0]
            if hasattr(val, "item"):
                return float(val.item())
            return float(val)
        return float(self._data)

    def __getitem__(self, idx: object) -> Any:
        if isinstance(idx, int):
            val = self._data[idx]
            if isinstance(val, list):
                return _FakeTensor(val)
            return _FakeScalar(val)  # Leaf value gets .item()
        return _FakeTensor(self._data[idx])

    def __iter__(self) -> Iterator[_FakeScalar | _FakeTensor]:
        if isinstance(self._data, list):
            for v in self._data:
                if isinstance(v, list):
                    yield _FakeTensor(v)
                else:
                    yield _FakeScalar(v)


class _FakeOutputs:
    def __init__(self) -> None:
        self.logits = _FakeTensor([[0.05, 0.10, 0.70, 0.15]])


class _NoGradContext:
    def __enter__(self) -> _NoGradContext:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        pass


def fake_tensor(data: Any, **kwargs: Any) -> _FakeTensor:
    return _FakeTensor(data)


def fake_argmax(tensor: Any, dim: int | None = None) -> Any:
    return types.SimpleNamespace(item=lambda: 2)


def fake_softmax(logits: Any, dim: int | None = None) -> _FakeTensor:
    return _FakeTensor([[0.05, 0.10, 0.70, 0.15]])


def _mock_torch() -> Any:
    """Create a minimal torch mock for testing.

    The mock is returned as Any: it is installed into ``sys.modules`` where it
    stands in for the real (heavy, optional) torch package, so mypy does not
    statically model its attributes.
    """
    torch_mock: Any = types.ModuleType("torch")

    # Mock nn.functional
    nn_module: Any = types.ModuleType("torch.nn")
    functional: Any = types.ModuleType("torch.nn.functional")

    functional.softmax = fake_softmax
    nn_module.functional = functional

    torch_mock.tensor = fake_tensor
    torch_mock.Tensor = _FakeTensor
    torch_mock.argmax = fake_argmax
    torch_mock.no_grad = lambda: _NoGradContext()
    torch_mock.nn = nn_module

    # Store FakeOutputs for transformers mock
    torch_mock._FakeOutputs = _FakeOutputs

    return torch_mock


def _make_transformers_mock(torch_mock: Any) -> Any:
    """Create a transformers mock that uses the torch mock."""

    class FakeTokenizer:
        def __call__(self, text: str, **kwargs: Any) -> dict[str, Any]:
            return {"input_ids": [[1, 2, 3]], "attention_mask": [[1, 1, 1]]}

    class FakeModel:
        def eval(self) -> FakeModel:
            return self

        def __call__(self, **kwargs: Any) -> Any:
            return torch_mock._FakeOutputs()

    transformers_mock: Any = types.ModuleType("transformers")

    class AutoTokenizer:
        @staticmethod
        def from_pretrained(name: str, **kwargs: Any) -> FakeTokenizer:
            return FakeTokenizer()

    class AutoModelForSequenceClassification:
        @staticmethod
        def from_pretrained(name: str, **kwargs: Any) -> FakeModel:
            return FakeModel()

    transformers_mock.AutoTokenizer = AutoTokenizer
    transformers_mock.AutoModelForSequenceClassification = AutoModelForSequenceClassification

    return transformers_mock


# Install mocks before import
if "torch" not in sys.modules:
    _torch: Any = _mock_torch()
    sys.modules["torch"] = _torch
    sys.modules["torch.nn"] = _torch.nn
    sys.modules["torch.nn.functional"] = _torch.nn.functional
if "transformers" not in sys.modules:
    sys.modules["transformers"] = _make_transformers_mock(sys.modules["torch"])

# Guard: skip if portal_mcp.security is not importable
pytest.importorskip(
    "portal.modules.security.tools.security_mcp",
    reason="portal_mcp.security not importable — run: pip install -e '.[dev,mcp]'",
)


def get_security_app() -> Any:
    """Get the security MCP server's Starlette ASGI app.

    streamable_http_app() can only be called once per mcp instance, so we
    create it once and reuse across all tests in this module.
    """
    from portal.modules.security.tools.security_mcp import mcp

    return mcp.streamable_http_app()


# Create the app once — StreamableHTTPSessionManager is single-use
_APP: Any = get_security_app()


class TestSecurityHealthEndpoint:
    """Test /health on the security MCP server."""

    @pytest.fixture(scope="class")
    def client(self) -> Iterator[TestClient]:
        from fastapi.testclient import TestClient

        with TestClient(_APP) as c:
            yield c

    def test_health_returns_200(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_correct_service(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert data["status"] == "ok"
        assert data["service"] == "security-mcp"

    def test_health_returns_port(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert "port" in data
        assert isinstance(data["port"], int)

    def test_lab_perception_dispatch_rejects_non_lab_target_with_400(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The /tools/lab_perception REST dispatch branch (Slice 1.4) maps a
        non-lab target to 400, not the generic 500 (OutOfScopeError is caught
        before the catch-all Exception branch). Lives on the same TestClient
        as the other health tests — StreamableHTTPSessionManager.run() can
        only be entered once per app instance, so a second TestClient(_APP)
        context in a separate class would hard-fail."""
        monkeypatch.setattr(
            "portal.modules.security.core.lab.lab_dispatch",
            lambda *a, **k: "unreachable",
        )
        resp = client.post("/tools/lab_perception", json={"arguments": {"hosts": ["8.8.8.8"]}})
        assert resp.status_code == 400


class TestClassifyVulnerability:
    """Test classify_vulnerability tool with mocked ML model."""

    def test_returns_severity_label(self) -> None:
        """classify_vulnerability must return a severity label."""
        from portal.modules.security.tools.security_mcp import classify_vulnerability

        result = classify_vulnerability(
            "Remote code execution via crafted HTTP request in Apache 2.4.x"
        )
        assert "severity" in result
        assert result["severity"] in ("low", "medium", "high", "critical")

    def test_returns_confidence_score(self) -> None:
        """classify_vulnerability must return a confidence score between 0 and 1."""
        from portal.modules.security.tools.security_mcp import classify_vulnerability

        result = classify_vulnerability(
            "Buffer overflow in OpenSSL allows remote attackers to execute arbitrary code"
        )
        assert "confidence" in result
        assert 0.0 <= result["confidence"] <= 1.0

    def test_returns_all_probabilities(self) -> None:
        """classify_vulnerability must return probabilities for all 4 severity levels."""
        from portal.modules.security.tools.security_mcp import classify_vulnerability

        result = classify_vulnerability("Cross-site scripting vulnerability in login form")
        assert "probabilities" in result
        probs = result["probabilities"]
        assert set(probs.keys()) == {"low", "medium", "high", "critical"}
        total = sum(probs.values())
        assert abs(total - 1.0) < 0.01, f"Probabilities should sum to ~1.0, got {total}"

    def test_returns_model_name(self) -> None:
        """classify_vulnerability must return the model name used."""
        from portal.modules.security.tools.security_mcp import classify_vulnerability

        result = classify_vulnerability("CVE-2024-1234: denial of service")
        assert "model" in result
        assert "roberta" in result["model"].lower() or "vulnerability" in result["model"].lower()

    def test_empty_description_handled(self) -> None:
        """Empty input should not crash — returns a result dict."""
        from portal.modules.security.tools.security_mcp import classify_vulnerability

        result = classify_vulnerability("")
        assert isinstance(result, dict)
        assert "severity" in result

    def test_long_description_truncated(self) -> None:
        """Descriptions exceeding 512 tokens should be truncated, not crash."""
        from portal.modules.security.tools.security_mcp import classify_vulnerability

        long_desc = "vulnerability " * 500  # Way over 512 tokens
        result = classify_vulnerability(long_desc)
        assert isinstance(result, dict)
        assert "severity" in result


class TestLabPerceptionTool:
    """Test the lab_perception MCP tool (Slice 1.4, invariant I1)."""

    def test_manifest_lists_lab_perception(self) -> None:
        from portal.modules.security.tools.security_mcp import TOOLS_MANIFEST

        names = {t["name"] for t in TOOLS_MANIFEST}
        assert "lab_perception" in names

    def test_lab_target_returns_observation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from portal.modules.security.tools import security_mcp

        monkeypatch.setattr(
            "portal.modules.security.core.lab.lab_dispatch",
            lambda fn_name, fn_args, dry_run=False: "OK: scan complete",
        )
        result = security_mcp.lab_perception(hosts=["10.10.11.5"])
        assert result["_source"] == "live_perception"
        assert result["services"] == [{"host": "10.10.11.5", "raw": "OK: scan complete"}]

    def test_non_lab_target_rejected_before_dispatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from portal.modules.security.core.perception import OutOfScopeError
        from portal.modules.security.tools import security_mcp

        calls: list[Any] = []

        def _record_call_and_return_unreachable(*a: object, **k: object) -> str:
            calls.append(a)
            return "unreachable"

        monkeypatch.setattr(
            "portal.modules.security.core.lab.lab_dispatch",
            _record_call_and_return_unreachable,
        )
        with pytest.raises(OutOfScopeError):
            security_mcp.lab_perception(hosts=["8.8.8.8"])
        assert calls == []  # guard fires before any dispatch leaves the box


class TestEnsureModel:
    """Test the lazy model loading behavior."""

    def test_ensure_model_is_callable(self) -> None:
        """_ensure_model should be a callable function."""
        from portal.modules.security.tools.security_mcp import _ensure_model

        assert callable(_ensure_model)

    def test_ensure_model_loads_only_once(self) -> None:
        """Calling _ensure_model twice should not reload the model."""
        from portal.modules.security.tools import security_mcp

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
