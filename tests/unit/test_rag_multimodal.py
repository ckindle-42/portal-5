"""Unit tests for portal.modules.research.tools.rag_multimodal client seam
(TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 A1).

No network, no LanceDB, no VL server — httpx.AsyncClient is faked.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

rm = pytest.importorskip(
    "portal.modules.research.tools.rag_multimodal",
    reason="lancedb/pyarrow/httpx not importable",
)

_embedding = pytest.importorskip("portal.platform.retrieval.embedding")

_store = pytest.importorskip("portal.platform.retrieval.store")

_fusion = pytest.importorskip("portal.platform.retrieval.fusion")


class _HealthClient:
    payload = {"embed_model": "model-X", "embedding_dim": 2048}

    async def get(self, url):
        return _FakeHealthResp(_HealthClient.payload)


class _FakeHealthResp:
    def __init__(self, p):
        self._p = p

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class _FakeTable:
    def __init__(self, rows):
        self._rows = rows

    def search(self, _qvec):
        return self

    def limit(self, _n):
        return self

    def to_list(self):
        return self._rows


def _wire_search(monkeypatch, *, text_distance, rerank_scores):
    """Patch _search's dependencies so only the fusion is exercised."""

    async def _emb(text=None, image_path=None, is_query=False):
        return [0.1] * _embedding.VL_DIM

    async def _model_id():
        return ("m", _embedding.VL_DIM)

    async def _rerank(q, cands, n):
        return [{"index": i, "score": s} for i, s in enumerate(rerank_scores)]

    monkeypatch.setattr(_embedding, "vl_embed", _emb)
    monkeypatch.setattr(_embedding, "vl_model_id", _model_id)
    monkeypatch.setattr(_store, "assert_embedding_space", lambda *a: None)
    monkeypatch.setattr(_embedding, "vl_rerank", _rerank)
    monkeypatch.setattr(
        _store,
        "text_table",
        lambda kb, create=False: _FakeTable(
            [
                {
                    "chunk_id": "t1",
                    "source_file": "prose.pdf",
                    "chunk_index": 0,
                    "text": "x",
                    "_distance": text_distance,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        _store,
        "visual_table",
        lambda kb, create=False: _FakeTable(
            [{"chunk_id": "v1", "source_file": "figure.pdf", "page": 1, "image_path": "/x.png"}]
        ),
    )


async def _run_search(kb="k", query="q"):
    class _R:
        async def json(self):
            return {"arguments": {"kb_id": kb, "query": query, "top_k": 3}}

    import json as _j

    return _j.loads((await rm._search(_R())).body)["results"]


async def test_unified_is_immune_to_text_arm_richness(monkeypatch):
    """`unified` keys off no absolute cosine, so the same visual candidate wins at
    BOTH text distances — the property that motivated it. It is NOT the default:
    measured on the eval corpus it scores diagram r@1 0.619 against text_gate's
    0.952, because the shared reranker space is text-biased. Retained as an A/B
    switch, and this test pins the property it does have."""
    monkeypatch.setattr(_fusion, "FUSION", "unified")
    for text_distance in (1.2, 0.3):  # weak text arm, then rich text arm
        _wire_search(monkeypatch, text_distance=text_distance, rerank_scores=[0.30, 0.88])
        res = await _run_search(query="which valve is fail-closed")
        assert res[0]["kind"] == "visual", f"regressed at text_distance={text_distance}"


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
