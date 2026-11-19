"""Unit tests for portal.modules.research.tools.rag_multimodal client seam
(TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 A1).

No network, no LanceDB, no VL server. Retrieval against a loaded knowledge base is
proved live by ``portal trace --section rag``; what stays here is the fitted
constant and the pins that must move with it.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

_fusion = pytest.importorskip("portal.platform.retrieval.fusion")


_BASELINE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "fixtures"
    / "rag_eval_corpus"
    / "retrieval_eval_baseline.json"
)

_BASELINE = json.loads(_BASELINE_PATH.read_text())


def _declared_pin(text: str, package: str) -> str | None:
    """The version specifier a manifest declares for `package`, e.g. '>=2.99.0'."""
    m = re.search(rf'"{re.escape(package)}([^"]*)"', text)
    return m.group(1) if m else None


def test_uv_lock_docling_matches_the_dockerfile_mcp_pin():
    """The invariant the first test enforces (pyproject ≈ Dockerfile) is
    necessary but not sufficient: on 2026-10-10 the lock drifted to 2.137.0
    while the container stayed on 2.99.0 and no test noticed because neither
    comparison spans hosts versus containers. The container and host must
    extract identically — otherwise the container silently runs a tau that
    was never measured against what it produces (Dockerfile.mcp comment)."""
    tomllib = pytest.importorskip("tomllib")  # stdlib from 3.11; the project allows 3.10
    root = pathlib.Path(__file__).resolve().parents[2]
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    dockerfile = (root / "Dockerfile.mcp").read_text()

    resolved = next(
        (pkg["version"] for pkg in lock["package"] if pkg.get("name") == "docling"), None
    )

    declared = (_declared_pin(dockerfile, "docling") or "").removeprefix("==")
    assert resolved == declared, (
        f"uv.lock resolves docling {resolved} but Dockerfile.mcp pins "
        f"=={declared}. Container and host must extract identically — "
        f"re-run the retrieval eval (scripts/rag_retrieval_eval.py), "
        f"re-derive tau, then update both the lock and the Dockerfile pin "
        f"together."
    )


def test_shipped_tau_is_the_knee_of_the_recorded_sweep():
    """Derive the choice from the data rather than restating it: the knee is the
    smallest tau reaching max diagram recall, and it must cost nothing in prose.
    If someone edits tau alone, this fails; if someone edits the sweep, the
    fingerprint tests above already demanded the eval be re-run."""
    sweep = _BASELINE["tau_sweep"]
    best_dia = max(r["diagram_r1"] for r in sweep)
    best_prose = max(r["prose_r1"] for r in sweep)
    knee = min(
        (r for r in sweep if r["diagram_r1"] == best_dia and r["prose_r1"] == best_prose),
        key=lambda r: r["tau"],
    )
    assert knee["tau"] == _BASELINE["chosen_tau"], "recorded chosen_tau is not the sweep's knee"
    shipped_tau = _fusion.VL_TEXT_GATE
    assert shipped_tau == pytest.approx(knee["tau"]), (
        f"VL_TEXT_GATE={shipped_tau} but the recorded sweep's knee is "
        f"{knee['tau']} (diagram r@1 {knee['diagram_r1']}, prose r@1 "
        f"{knee['prose_r1']}). Changing tau without re-running the eval is how "
        f"this went wrong before."
    )


def test_gate_endpoints_prove_both_halves_are_load_bearing():
    """Guards the DESIGN, not the constant: tau=0.00 (never fires) must reproduce
    B1, and tau=1.01 (always fires) must not beat the shipped gate.

    Under Qwen3-VL always-fires cost prose (0.688 vs 0.812), so the conditionality was
    load-bearing. Under EmbeddingGemma 2 (2026-10-08) always-fires TIES the knee at the
    ceiling (1.000/1.000 on 42 queries): the boost is load-bearing, the conditionality is
    not shown to be. Whether to simplify fusion to always-blend is TASK_EG2_CUTOVER_V1 C7's
    separate decision; this asserts only that the shipped gate is never the worse choice."""
    ep = _BASELINE["endpoint_tests"]
    shipped = next(r for r in _BASELINE["tau_sweep"] if r["tau"] == _BASELINE["chosen_tau"])
    assert ep["never_fires_tau_0.00"]["diagram_r1"] < shipped["diagram_r1"], (
        "gate never firing does not hurt diagram recall — the boost is not load-bearing"
    )
    assert ep["always_fires_tau_1.01"]["prose_r1"] <= shipped["prose_r1"], (
        "gate always firing beats the shipped gate on prose — text_gate is the wrong shape"
    )


def test_relative_gate_mode_is_not_the_default():
    """`relative` is measurably dominated (the margin is anti-correlated with
    need: diagram queries carry the LARGER margin, 0.117 vs prose 0.055). It
    stays selectable for A/B; it must not become the shipped behaviour."""
    assert _fusion.VL_TEXT_GATE_MODE == "absolute"
    assert _fusion.FUSION == "text_gate"
