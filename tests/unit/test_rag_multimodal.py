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


class _FakeResp:
    def __init__(self, n):
        self._n = n

    def raise_for_status(self):
        pass

    def json(self):
        return {"embeddings": [[0.1] * rm.VL_DIM for _ in range(self._n)]}


class _FakeClient:
    posted: list[int] = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def post(self, url, json):
        n = len(json["items"])
        _FakeClient.posted.append(n)
        return _FakeResp(n)


async def test_vl_embed_batch_caps_request_size(monkeypatch):
    monkeypatch.setattr(rm, "VL_EMBED_MAX_ITEMS", 4)
    monkeypatch.setattr(rm.httpx, "AsyncClient", _FakeClient)
    _FakeClient.posted = []
    vecs = await rm._vl_embed_batch([{"text": f"t{i}"} for i in range(10)])
    assert len(vecs) == 10
    assert _FakeClient.posted == [4, 4, 2]  # 3 requests, none over the cap, order kept


async def test_vl_embed_batch_empty_is_noop(monkeypatch):
    monkeypatch.setattr(rm.httpx, "AsyncClient", _FakeClient)
    _FakeClient.posted = []
    assert await rm._vl_embed_batch([]) == []
    assert _FakeClient.posted == []


# ── A3: embedding-model identity stamp ──────────────────────────────────────


def test_write_then_read_stamp_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "RAG_DIR", str(tmp_path))
    rm._write_stamp("kb1", "mlx-community/Qwen3-VL-Embedding-2B-mxfp8", 2048)
    got = rm._read_stamp("kb1")
    assert got["embed_model"] == "mlx-community/Qwen3-VL-Embedding-2B-mxfp8"
    assert got["vl_dim"] == 2048
    assert rm._read_stamp("absent") is None


def test_assert_embedding_space_rejects_same_dim_different_model(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "RAG_DIR", str(tmp_path))
    rm._write_stamp("kb1", "model-A-2048", 2048)
    rm._assert_embedding_space("kb1", "model-A-2048")  # match: fine
    with pytest.raises(rm._VLUnavailableError, match="different spaces"):
        rm._assert_embedding_space("kb1", "model-B-2048")
    # an unstamped KB (legacy) is not blocked
    rm._assert_embedding_space("kb-legacy", "model-B-2048")


class _HealthClient:
    payload = {"embed_model": "model-X", "embedding_dim": 2048}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, url):
        return _FakeHealthResp(_HealthClient.payload)


class _FakeHealthResp:
    def __init__(self, p):
        self._p = p

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


async def test_vl_model_id_reads_health_and_caches(monkeypatch):
    monkeypatch.setattr(rm.httpx, "AsyncClient", _HealthClient)
    rm._MODEL_ID_CACHE.update(value=None, at=0.0)
    calls = []
    orig_get = _HealthClient.get

    async def counting_get(self, url):
        calls.append(url)
        return await orig_get(self, url)

    monkeypatch.setattr(_HealthClient, "get", counting_get)
    assert await rm._vl_model_id() == ("model-X", 2048)
    assert await rm._vl_model_id() == ("model-X", 2048)  # served from cache
    assert len(calls) == 1  # /health hit once, not per call


# ── C1: text-gated visual boost (B1 fusion fix) ────────────────────────────


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
        return [0.1] * rm.VL_DIM

    async def _model_id():
        return ("m", rm.VL_DIM)

    async def _rerank(q, cands, n):
        return [{"index": i, "score": s} for i, s in enumerate(rerank_scores)]

    monkeypatch.setattr(rm, "_vl_embed", _emb)
    monkeypatch.setattr(rm, "_vl_model_id", _model_id)
    monkeypatch.setattr(rm, "_assert_embedding_space", lambda *a: None)
    monkeypatch.setattr(rm, "_vl_rerank", _rerank)
    monkeypatch.setattr(
        rm,
        "_text_table",
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
        rm,
        "_visual_table",
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


async def test_c1_weak_text_promotes_the_figure(monkeypatch):
    # top text cosine ~0.40 (< VL_TEXT_GATE 0.72) -> visual boost ON.
    # Pinned explicitly: `unified` and `rrf` are selectable and neither uses the
    # gate, so the strategy under test must be named rather than inherited.
    monkeypatch.setattr(rm, "FUSION", "text_gate")
    _wire_search(monkeypatch, text_distance=1.2, rerank_scores=[0.7])
    res = await _run_search(query="which valve is fail-closed")
    assert res[0]["kind"] == "visual" and res[0]["reranker_prob"] == 0.7


async def test_c1_strong_text_keeps_text_first(monkeypatch):
    # top text cosine ~0.85 (>= gate) -> visual boost OFF, RRF tie -> text wins
    monkeypatch.setattr(rm, "FUSION", "text_gate")
    _wire_search(monkeypatch, text_distance=0.3, rerank_scores=[0.7])
    res = await _run_search(query="how often must an ESP be reviewed")
    assert res[0]["kind"] == "text"


async def test_unified_ranks_purely_on_the_shared_reranker_score(monkeypatch):
    """The structural fix for B1: with one comparable scoring pass there is no
    tie to break, so the winner is whichever candidate the cross-encoder scored
    highest — regardless of which arm it came from or how rich the text arm is."""
    monkeypatch.setattr(rm, "FUSION", "unified")
    # text candidate is index 0, visual is index 1; give the VISUAL the higher score
    _wire_search(monkeypatch, text_distance=0.3, rerank_scores=[0.30, 0.88])
    res = await _run_search(query="which valve is fail-closed")
    assert res[0]["kind"] == "visual"
    assert res[0]["fused_score"] == 0.88


async def test_unified_is_immune_to_text_arm_richness(monkeypatch):
    """`unified` keys off no absolute cosine, so the same visual candidate wins at
    BOTH text distances — the property that motivated it. It is NOT the default:
    measured on the eval corpus it scores diagram r@1 0.619 against text_gate's
    0.952, because the shared reranker space is text-biased. Retained as an A/B
    switch, and this test pins the property it does have."""
    monkeypatch.setattr(rm, "FUSION", "unified")
    for text_distance in (1.2, 0.3):  # weak text arm, then rich text arm
        _wire_search(monkeypatch, text_distance=text_distance, rerank_scores=[0.30, 0.88])
        res = await _run_search(query="which valve is fail-closed")
        assert res[0]["kind"] == "visual", f"regressed at text_distance={text_distance}"


# ── the retrieval eval's staleness guard ─────────────────────────────────────
# WHAT THE FAILURE ACTUALLY LOOKS LIKE, because the first version of these tests
# got it wrong. Diagram recall@1 fell 1.000 -> 0.714 when docling replaced the
# PyMuPDF fallback, and tau DID NOT CHANGE — it sat at 0.67 the whole time. The
# data moved underneath a constant that was still correct-looking.
#
# So a test that only reads module constants (`assert VL_TEXT_GATE < 0.75`,
# `assert _text_arm_is_unconfident(0.6732, ...)`) is structurally incapable of
# catching this: it is a comparison between two hardcoded numbers, invariant to
# the corpus, the extractor and the embedding model. It fails only when someone
# edits tau — the one thing that did not happen. Those checks are kept below,
# but demoted to what they are: assertions that tau matches the recorded sweep,
# not regression detection.
#
# The only thing that can actually detect the failure is the retrieval eval, and
# it cannot run here (MLX VL server, ~21 min ingest, the operator's private
# PDFs). What IS testable is whether that eval's result is still VALID — i.e.
# whether any of its inputs moved since it was run. That is the guard: pin the
# fingerprint, so an extraction/model/strategy change fails loudly and says
# "re-run the eval" instead of quietly invalidating tau.

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


def test_retrieval_eval_baseline_still_matches_the_declared_dependency_pins():
    """The change that silently halved diagram recall was a DEPENDENCY change:
    docling arriving and displacing the PyMuPDF fallback. A later `pip install
    docling` downgraded transformers 5.16.1 -> 5.8.1 under the VL server and
    invalidated the sweep a second time. Both are edits to a manifest, so both
    are catchable here — unlike the recall number itself."""
    root = pathlib.Path(__file__).resolve().parents[2]
    pyproject = (root / "pyproject.toml").read_text()
    dockerfile = (root / "Dockerfile.mcp").read_text()
    fp = _BASELINE["fingerprint"]

    for pkg, expected in fp["pyproject_pins"].items():
        assert _declared_pin(pyproject, pkg) == expected, (
            f"pyproject now pins {pkg}{_declared_pin(pyproject, pkg)}, but the "
            f"retrieval eval in {_BASELINE['report']} was run against "
            f"{pkg}{expected}. Extraction and embedding output are version-coupled "
            f"and VL_TEXT_GATE is fitted to them — re-run the eval, re-derive tau, "
            f"then update {_BASELINE_PATH.name}."
        )
    for pkg, expected in fp["dockerfile_mcp_pins"].items():
        assert _declared_pin(dockerfile, pkg) == expected, (
            f"Dockerfile.mcp now pins {pkg}{_declared_pin(dockerfile, pkg)} but the "
            f"eval used {pkg}{expected}. Container and host must extract identically."
        )


def test_retrieval_eval_baseline_still_matches_the_configured_pipeline():
    """The other way to invalidate the eval without touching tau: change the
    embedding model, the chunker, or the fusion strategy. Each silently rebases
    the cosine distribution tau is compared against."""
    fp = _BASELINE["fingerprint"]
    server = (
        pathlib.Path(__file__).resolve().parents[2] / "scripts" / "vl-retrieval-server.py"
    ).read_text()

    for name, live, recorded in (
        ("RAG_CHUNK_STRATEGY", rm.CHUNK_STRATEGY, fp["chunk_strategy"]),
        ("VL_FUSION", rm.FUSION, fp["fusion"]),
        ("VL_TEXT_GATE_MODE", rm.VL_TEXT_GATE_MODE, fp["gate_mode"]),
        ("VL_EMBEDDING_DIM", rm.VL_DIM, fp["embedding_dim"]),
    ):
        assert live == recorded, (
            f"{name} is {live!r}; the retrieval eval that fitted tau ran with "
            f"{recorded!r}. Re-run the eval before shipping this."
        )
    for key, model in (
        ("VL_EMBED_MODEL", fp["embed_model"]),
        ("VL_RERANK_MODEL", fp["rerank_model"]),
    ):
        assert f'"{key}", "{model}"' in server, (
            f"{key} default no longer {model}; the eval's cosine distribution — and "
            f"therefore tau — was measured on that model. Re-run the eval."
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
    shipped_tau = rm.VL_TEXT_GATE
    assert shipped_tau == pytest.approx(knee["tau"]), (
        f"VL_TEXT_GATE={shipped_tau} but the recorded sweep's knee is "
        f"{knee['tau']} (diagram r@1 {knee['diagram_r1']}, prose r@1 "
        f"{knee['prose_r1']}). Changing tau without re-running the eval is how "
        f"this went wrong before."
    )


def test_gate_endpoints_prove_both_halves_are_load_bearing():
    """Guards the DESIGN, not the constant: tau=0.00 (never fires) must reproduce
    B1, and tau=1.01 (always fires) must cost prose. If a future sweep ever shows
    otherwise, text_gate is the wrong shape and re-tuning it is not the answer."""
    ep = _BASELINE["endpoint_tests"]
    shipped = next(r for r in _BASELINE["tau_sweep"] if r["tau"] == _BASELINE["chosen_tau"])
    assert ep["never_fires_tau_0.00"]["diagram_r1"] < shipped["diagram_r1"], (
        "gate never firing does not hurt diagram recall — the boost is not load-bearing"
    )
    assert ep["always_fires_tau_1.01"]["prose_r1"] < shipped["prose_r1"], (
        "gate always firing costs nothing — the CONDITIONALITY is not load-bearing"
    )


def test_relative_gate_mode_is_not_the_default():
    """`relative` is measurably dominated (the margin is anti-correlated with
    need: diagram queries carry the LARGER margin, 0.117 vs prose 0.055). It
    stays selectable for A/B; it must not become the shipped behaviour."""
    assert rm.VL_TEXT_GATE_MODE == "absolute"
    assert rm.FUSION == "text_gate"
