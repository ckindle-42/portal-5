"""Primary-model grader: serving-backend aliases, engine match, infra cause.

Trace shapes are the rows in results/qat/release_1_0_final_clean/results.jsonl
(s4-auto-daily-fast-continuity, s2-p2-auto-vision). The file stores the grader
evidence, not the pipeline record, so each trace is that evidence's workspace,
model, backend, and spans.
"""

from __future__ import annotations

import pytest

from portal.platform.inference.cluster_backends import BackendRegistry
from tests.qat import config as cq
from tests.qat import runner
from tests.qat.models import DefectClass, QATScenario, Status

# results.jsonl line for s4-auto-daily-fast-continuity (release_1_0_final_clean).
S4_SERVED = "unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit"
S4_EXPECTED = "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL-ctx96k"
S4_TRACE: dict[str, object] = {
    "workspace": "auto-daily::fast",
    "model": S4_SERVED,
    "backend": "omlx-general",
    "spans": [{"at_ms": 18347.1, "backend": "omlx-general", "name": "backend.failed"}],
}

# results.jsonl line for s2-p2-auto-vision. The seat's hint has since moved to
# ctx16k; the row graded ctx8k against ctx8k.
S2_MODEL = "qwen3-vl:32b-ctx8k"
S2_TRACE: dict[str, object] = {
    "workspace": "auto-vision",
    "model": S2_MODEL,
    "backend": "ollama-vision",
    "spans": [{"at_ms": 32329.6, "backend": "ollama-vision", "name": "backend.failed"}],
}


def _scenario(scenario_id: str, stage: int, workspace: str) -> QATScenario:
    return QATScenario(scenario_id, scenario_id, stage, "phase", 1, workspace)


def _s4() -> QATScenario:
    return _scenario("s4-auto-daily-fast-continuity", 4, "auto-daily::fast")


def _s2() -> QATScenario:
    return _scenario("s2-p2-auto-vision", 2, "auto-vision")


class TestServingBackendAlias:
    def test_s4_alias_on_omlx_general_is_the_primary(self) -> None:
        expected = cq.primary_model_for("auto-daily::fast")
        assert expected == S4_EXPECTED
        backend = runner._backend_named("omlx-general")
        assert backend is not None
        assert backend.resolve_model(expected) == S4_SERVED
        trace = {
            "workspace": "auto-daily::fast",
            "model": S4_SERVED,
            "backend": "omlx-general",
            "outcome": "complete",
            "spans": [
                {"name": "backend.selected", "backend": "omlx-general", "model": S4_SERVED},
            ],
        }
        assert runner._primary_model_failure(_s4(), trace, S4_SERVED) is None

    def test_hint_on_the_serving_backend_passes(self) -> None:
        expected = cq.primary_model_for("auto-daily::fast")
        trace = {
            "workspace": "auto-daily::fast",
            "model": expected,
            "backend": "ollama-general",
            "outcome": "complete",
            "spans": [{"name": "backend.selected", "backend": "ollama-general", "model": expected}],
        }
        assert runner._primary_model_failure(_s4(), trace, expected) is None

    def test_alias_from_another_backend_does_not_count(self) -> None:
        trace = {
            "workspace": "auto-daily::fast",
            "model": S4_SERVED,
            "backend": "ollama-general",
            "outcome": "complete",
            "spans": [
                {"name": "backend.selected", "backend": "ollama-general", "model": S4_SERVED}
            ],
        }
        result = runner._primary_model_failure(_s4(), trace, S4_SERVED)
        assert result is not None and result.status is Status.FAIL
        assert "served model differs from primary" in result.detail


class TestInfraCause:
    def test_s4_backend_failed_is_not_a_model_miss(self) -> None:
        result = runner._primary_model_failure(_s4(), S4_TRACE, S4_SERVED)
        assert result is not None and result.status is Status.FAIL
        assert result.defect_class is DefectClass.INFRA_ENV_GAP
        assert "backend.failed" in result.detail
        assert "primary model missed" not in result.detail
        assert "served model differs from primary" not in result.detail
        assert result.evidence["primary_mismatch"]["actual"] == S4_SERVED

    def test_s2_equal_models_report_backend_failed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(runner, "primary_model_for", lambda workspace: S2_MODEL)
        result = runner._primary_model_failure(_s2(), S2_TRACE, S2_MODEL)
        assert result is not None and result.status is Status.FAIL
        assert result.defect_class is DefectClass.INFRA_ENV_GAP
        assert "backend.failed on ollama-vision" in result.detail
        assert S2_MODEL in result.detail
        assert "primary model missed" not in result.detail

    def test_outcome_error_reports_the_error_not_a_model_miss(self) -> None:
        # Same selected-seat shape as the live auto-daily::fast HTTP 507 turn,
        # with the span's error text kept.
        trace = {
            "workspace": "auto-daily::fast",
            "model": S4_SERVED,
            "backend": "omlx-general",
            "outcome": "error",
            "spans": [
                {"name": "backend.selected", "backend": "omlx-general", "model": S4_SERVED},
                {
                    "name": "backend.failed",
                    "backend": "omlx-general",
                    "at_ms": 2575.2,
                    "error": "HTTP 507",
                },
            ],
        }
        result = runner._primary_model_failure(_s4(), trace, S4_SERVED)
        assert result is not None and result.status is Status.FAIL
        assert "backend.failed on omlx-general: HTTP 507" in result.detail
        assert "primary model missed" not in result.detail


class TestEngineInversion:
    def _hint(self) -> str:
        hint = cq.primary_model_for("auto-spl")
        natives = [
            backend.id
            for backend in BackendRegistry().list_backends()
            if backend.type == "omlx" and hint in backend.models
        ]
        assert natives, hint
        return hint

    def test_omlx_native_hint_served_by_ollama_names_both_engines(self) -> None:
        hint = self._hint()
        trace = {
            "workspace": "auto-spl",
            "model": hint,
            "backend": "ollama-general",
            "outcome": "complete",
            "spans": [{"name": "backend.selected", "backend": "ollama-general", "model": hint}],
        }
        result = runner._primary_model_failure(_scenario("s2-auto-spl", 2, "auto-spl"), trace, hint)
        assert result is not None and result.status is Status.FAIL
        assert "intended engine omlx (" in result.detail
        assert "served by ollama (ollama-general)" in result.detail
        assert "primary model missed" not in result.detail

    def test_ollama_serve_passes_after_omlx_attempt_failed(self) -> None:
        hint = self._hint()
        natives = [
            backend.id
            for backend in BackendRegistry().list_backends()
            if backend.type == "omlx" and hint in backend.models
        ]
        trace = {
            "workspace": "auto-spl",
            "model": hint,
            "backend": "ollama-general",
            "outcome": "complete",
            "spans": [
                *[
                    {"name": "backend.attempt", "backend": backend_id, "outcome": "failed"}
                    for backend_id in natives
                ],
                {"name": "backend.selected", "backend": "ollama-general", "model": hint},
            ],
        }
        assert (
            runner._primary_model_failure(_scenario("s2-auto-spl", 2, "auto-spl"), trace, hint)
            is None
        )


class TestRecoveredFallbackSpans:
    """A non-serving backend.attempt followed by the primary serving is a pass.
    A backend.failed span is not discovery: the row stays infra, not clean."""

    def _hint_and_natives(self) -> tuple[str, list[str]]:
        hint = TestEngineInversion()._hint()
        natives = [
            backend.id
            for backend in BackendRegistry().list_backends()
            if backend.type == "omlx" and hint in backend.models
        ]
        assert natives, hint
        return hint, natives

    def test_non_streaming_backend_failed_on_a_non_serving_backend_is_not_clean(self) -> None:
        hint, natives = self._hint_and_natives()
        trace = {
            "workspace": "auto-spl",
            "model": hint,
            "backend": "ollama-general",
            "outcome": "complete",
            "spans": [
                *[
                    {"name": "backend.failed", "backend": backend_id, "error": "connect timeout"}
                    for backend_id in natives
                ],
                *[
                    {"name": "backend.attempt", "backend": backend_id, "outcome": "failed"}
                    for backend_id in natives
                ],
                {"name": "backend.selected", "backend": "ollama-general", "model": hint},
            ],
        }
        result = runner._primary_model_failure(_scenario("s2-auto-spl", 2, "auto-spl"), trace, hint)
        assert result is not None and result.status is Status.FAIL
        assert result.defect_class is DefectClass.INFRA_ENV_GAP
        assert "not clean" in result.detail

    def test_streaming_backend_failed_on_a_non_serving_backend_is_not_clean(self) -> None:
        """backend.failed on the candidates that did not serve is still a failed
        attempt: the primary may have been served, and the row is infra."""
        hint, natives = self._hint_and_natives()
        serving = "ollama-general"
        trace = {
            "workspace": "auto-spl",
            "model": hint,
            "backend": serving,
            "outcome": "ok",
            "spans": [
                *[
                    {"name": "backend.failed", "backend": backend_id, "error": "HTTP 507"}
                    for backend_id in natives
                ],
                {"name": "backend.selected", "backend": serving, "model": hint, "fallback": True},
            ],
        }
        result = runner._primary_model_failure(_scenario("s2-auto-spl", 2, "auto-spl"), trace, hint)
        assert result is not None and result.status is Status.FAIL
        assert result.defect_class is DefectClass.INFRA_ENV_GAP
        assert "not clean" in result.detail

    def test_backend_failed_on_the_serving_backend_still_fails_infra(self) -> None:
        trace = {
            "workspace": "auto-daily::fast",
            "model": runner.primary_model_for("auto-daily::fast"),
            "backend": "omlx-general",
            "outcome": "error",
            "spans": [
                {"name": "backend.selected", "backend": "omlx-general", "model": "x"},
                {"name": "backend.failed", "backend": "omlx-general", "error": "HTTP 507"},
            ],
        }
        result = runner._primary_model_failure(_s4(), trace, str(trace["model"]))
        assert result is not None and result.defect_class is DefectClass.INFRA_ENV_GAP
        assert "backend.failed on omlx-general" in result.detail

    def test_exhausted_turn_without_serving_backend_keeps_the_cause(self) -> None:
        """All-candidates-failed traces carry no serving backend meta, so the
        backend.failed spans still name the cause (streaming.py exhaustion)."""
        trace = {
            "workspace": "auto-spl",
            "model": "",
            "outcome": "error",
            "spans": [
                {"name": "backend.failed", "backend": "omlx-general", "error": "HTTP 507"},
            ],
        }
        assert runner._infra_cause(trace) == "backend.failed on omlx-general: HTTP 507"
