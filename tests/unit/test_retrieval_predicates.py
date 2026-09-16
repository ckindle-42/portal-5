"""The one filter seam (SUBSTRATE_PROPERTIES_V1 P2).

Three things, each with its own failure mode:

* ``predicates.build`` — ONE clause builder for every consumer. Values are tool
  arguments an operator or a model supplies, so a raw string never reaches a
  clause: a quote is escaped, a clause fragment inside a value stays a value.
* the ``where`` seam — ``pipeline.search`` / ``fusion.fuse`` push a predicate
  into BOTH text arms and into the visual arm where its schema can express it,
  and REPORT it where it cannot. A half-filtered fused list looks filtered,
  which is worse than no filter.
* the no-filter path — byte-identical to before the seam existed. The exact
  result ordering, scores and payload keys of a no-filter search are pinned
  here; the seam changed nothing for a caller that passes no ``where``.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import sys
import types

import pytest

rm = importlib.import_module("portal.modules.research.tools.rag_multimodal")
predicates = importlib.import_module("portal.platform.retrieval.predicates")
fusion = importlib.import_module("portal.platform.retrieval.fusion")
pipeline = importlib.import_module("portal.platform.retrieval.pipeline")
_store = importlib.import_module("portal.platform.retrieval.store")
_embedding = importlib.import_module("portal.platform.retrieval.embedding")

DIM = 8


def _vec(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    return [((digest[i] / 255.0) - 0.5) for i in range(DIM)]


async def _emb(text=None, image_path=None, is_query=False):
    return _vec(text or image_path or "")


async def _emb_batch(items):
    return [_vec(i.get("text") or i.get("image_path") or "") for i in items]


async def _rr(_query, cands, _n):
    return [
        {
            "index": i,
            "score": round(
                int(
                    hashlib.sha256(
                        (c.get("text") or c.get("image_path") or "").encode()
                    ).hexdigest()[:8],
                    16,
                )
                % 1000
                / 1000,
                5,
            ),
        }
        for i, c in enumerate(cands)
    ]


async def _model_id():
    return ("fake-vl-model", DIM)


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    pytest.importorskip("lancedb")
    monkeypatch.setattr(_store, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(_store, "RAG_DIR", str(tmp_path / "lance" / "rag"))
    monkeypatch.setattr(_embedding, "VL_DIM", DIM)
    monkeypatch.setattr(_embedding, "vl_embed", _emb)
    monkeypatch.setattr(_embedding, "vl_embed_batch", _emb_batch)
    monkeypatch.setattr(_embedding, "vl_rerank", _rr)
    monkeypatch.setattr(_embedding, "vl_model_id", _model_id)
    monkeypatch.setattr(rm, "_PAGES_DIR", tmp_path / "kb_pages")
    _store._db = None
    fake = types.ModuleType("portal.modules.research.tools.rag_mcp")
    fake._read_file = lambda p: "body"
    monkeypatch.setitem(sys.modules, "portal.modules.research.tools.rag_mcp", fake)


# ── the clause builder ──────────────────────────────────────────────────────


class TestPredicatesBuild:
    def test_empty_spec_means_no_filter(self):
        assert predicates.build(None) == ""
        assert predicates.build({}) == ""
        assert predicates.build([]) == ""

    def test_dict_is_equality_conjunction(self):
        assert predicates.build({"family": "steal", "rank": 3}) == "family = 'steal' AND rank = 3"

    def test_comparisons_and_in_lists(self):
        clause = predicates.build(
            [("effective_from", "<=", "2026-09-16"), ("in", "unit_kind", ["prose", "table_row"])]
        )
        assert clause == "effective_from <= '2026-09-16' AND unit_kind IN ('prose', 'table_row')"

    def test_empty_in_list_can_never_match(self):
        assert predicates.build([("in", "col", [])]) == "0"

    def test_or_group_for_clock_bounds(self):
        clause = predicates.build(
            [[("effective_from", "=", ""), ("effective_from", "<=", "2026-09-16")]]
        )
        assert clause == "(effective_from = '' OR effective_from <= '2026-09-16')"

    def test_a_quote_in_a_value_is_escaped_not_interpreted(self):
        hostile = "CIP-007-6' OR 1=1 --"
        clause = predicates.build({"standard": hostile})
        assert clause == "standard = 'CIP-007-6'' OR 1=1 --'"
        # the fragment is INSIDE the literal: the clause names one column and
        # the value round-trips exactly
        assert clause.count("'") == 4

    def test_bool_is_a_number_not_python_text(self):
        assert predicates.build({"active": True}) == "active = 1"

    def test_unsupported_shapes_are_rejected_never_interpolated(self):
        with pytest.raises(ValueError):
            predicates.build({"col": {"nested": "dict"}})
        with pytest.raises(ValueError):
            predicates.build([("col", "~", "x")])
        with pytest.raises(ValueError):
            predicates.build([("col; DROP TABLE", "=", "x")])
        with pytest.raises(ValueError):
            predicates.build("effective_from = ''")  # a raw string is not a spec


# ── fake lancedb surfaces for the seam ──────────────────────────────────────


class _FakeQuery:
    def __init__(self, rows, state):
        self._rows = rows
        self._state = state

    def limit(self, n):
        self._state["limit"] = n
        return self

    def where(self, clause):
        self._state["where"] = clause
        return self

    def to_list(self):
        clause = self._state.get("where", "")
        # honour a marker column so tests can see the predicate ran
        rows = [r for r in self._rows if r.get("_marker")] if clause else self._rows
        return rows[: self._state.get("limit", len(rows))]


class _FakeTable:
    def __init__(self, rows, columns):
        self._rows = rows
        self._columns = columns
        self.states: list[dict] = []

    @property
    def schema(self):
        class _S:
            names = self._columns

        return _S()

    def search(self, *_a, **_k):
        state = {}
        self.states.append(state)
        return _FakeQuery(self._rows, state)


def _run(c):
    return asyncio.new_event_loop().run_until_complete(c)


class TestTheSeappliesToBothArmsOrReports:
    def test_a_filter_hits_dense_bm25_and_visual_when_expressible(self):
        rows = [
            {
                "chunk_id": "a",
                "text": "x",
                "_marker": True,
                "source_file": "f",
                "chunk_index": 0,
                "page": 1,
                "char_start": 0,
                "char_end": 1,
            }
        ]
        ttbl = _FakeTable(rows, {"chunk_id", "text", "marker_col"})
        vtbl = _FakeTable(
            [
                {
                    "chunk_id": "v",
                    "image_path": "p.png",
                    "source_file": "f",
                    "page": 1,
                    "_marker": True,
                }
            ],
            {"chunk_id", "image_path", "source_file", "page", "jurisdiction"},
        )
        out = _run(
            fusion.fuse("text_gate", ttbl, vtbl, "q", [0.1] * DIM, 3, _rr, "jurisdiction = 'US'")
        )
        assert isinstance(out, fusion.FusedWithFilter)
        assert isinstance(out, list)
        assert out.filter_report["text_dense"] == "applied"
        assert out.filter_report["visual"] == "applied"
        assert ttbl.states[0]["where"] == "jurisdiction = 'US'"
        assert vtbl.states[0]["where"] == "jurisdiction = 'US'"

    def test_an_inexpressible_visual_predicate_is_reported_not_silently_skipped(self):
        rows = [
            {
                "chunk_id": "a",
                "text": "x",
                "_marker": True,
                "source_file": "f",
                "chunk_index": 0,
                "page": 1,
                "char_start": 0,
                "char_end": 1,
            }
        ]
        ttbl = _FakeTable(rows, {"chunk_id", "text"})
        vtbl = _FakeTable(
            [{"chunk_id": "v", "image_path": "p.png", "source_file": "f", "page": 1}],
            {"chunk_id", "image_path", "source_file", "page"},  # no predicate columns
        )
        out = _run(
            fusion.fuse("text_gate", ttbl, vtbl, "q", [0.1] * DIM, 3, _rr, "jurisdiction = 'US'")
        )
        assert ttbl.states[0]["where"] == "jurisdiction = 'US'"  # text arm filtered
        assert "where" not in vtbl.states[0]  # visual arm could not
        assert out.filter_report["visual"].startswith("not applied")

    def test_no_filter_returns_a_plain_list_and_untouched_arms(self):
        rows = [
            {
                "chunk_id": "a",
                "text": "x",
                "_marker": False,
                "source_file": "f",
                "chunk_index": 0,
                "page": 1,
                "char_start": 0,
                "char_end": 1,
            }
        ]
        ttbl = _FakeTable(rows, {"chunk_id", "text"})
        out = _run(fusion.fuse("text_gate", ttbl, None, "q", [0.1] * DIM, 3, _rr))
        assert type(out) is list
        assert "where" not in ttbl.states[0]


# ── the no-filter path is byte-identical ────────────────────────────────────


class _Req:
    def __init__(self, a):
        self._a = {"arguments": a}

    async def json(self):
        return self._a


@pytest.fixture
def _baseline_kb(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "patching.txt").write_text(
        "Requirement R2.1 patch management for CIP-007-6. Evaluate security patches every 35 days."
    )
    (src / "esp.md").write_text(
        "The ESP review cadence is 15 calendar months for high impact systems."
    )
    (src / "evidence.txt").write_text("Evidence is retained in the change record for three years.")
    ingest = json.loads(
        (
            asyncio.new_event_loop().run_until_complete(
                rm._ingest(_Req({"kb_id": "kb", "source_dir": str(src)}))
            )
        ).body
    )
    assert ingest["chunks_added"] == 3

    import pyarrow as pa

    db = _store.get_db()
    vtbl = db.create_table(
        _store.vname("kb", prefix="kb_"),
        schema=pa.schema(
            [
                pa.field("chunk_id", pa.string()),
                pa.field("kb_id", pa.string()),
                pa.field("source_file", pa.string()),
                pa.field("page", pa.int64()),
                pa.field("image_path", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), DIM)),
                pa.field("ingested_at", pa.float64()),
            ]
        ),
    )
    vtbl.add(
        [
            {
                "chunk_id": "vis-1",
                "kb_id": "kb",
                "source_file": "patching.txt",
                "page": 1,
                "image_path": "/pages/patching_p1.png",
                "vector": _vec("/pages/patching_p1.png"),
                "ingested_at": 1.0,
            },
            {
                "chunk_id": "vis-2",
                "kb_id": "kb",
                "source_file": "esp.md",
                "page": 2,
                "image_path": "/pages/esp_p2.png",
                "vector": _vec("/pages/esp_p2.png"),
                "ingested_at": 1.0,
            },
        ]
    )
    return src


class TestNoFilterResultsAreUnchanged:
    def test_search_kb_order_scores_and_keys_are_pinned(self, _baseline_kb):
        src = _baseline_kb
        out = json.loads(
            (
                asyncio.new_event_loop().run_until_complete(
                    rm._search(
                        _Req(
                            {
                                "kb_id": "kb",
                                "query": "evaluate security patches 35 days",
                                "top_k": 5,
                            }
                        )
                    )
                )
            ).body
        )

        # pinned from the pre-seam run of this exact fixture: same ordering,
        # same kind, same fused scores, same payload keys. The ingest chunk id
        # is sha1(f"{kb_id}|{absolute file}|{idx}") — computed from the fixture.
        def cid(name, idx=0):
            return hashlib.sha1(f"kb|{src / name}|{idx}".encode()).hexdigest()

        assert sorted(out.keys()) == ["kb_id", "num_results", "query", "results"]
        assert [(r["chunk_id"], r["kind"], r["fused_score"]) for r in out["results"]] == [
            ("vis-2", "visual", 0.86267),
            ("vis-1", "visual", 0.08339),
            (cid("esp.md"), "text", 0.01667),
            (cid("patching.txt"), "text", 0.01639),
            (cid("evidence.txt"), "text", 0.01613),
        ]
        assert sorted(out["results"][0].keys()) == [
            "chunk_id",
            "chunk_index",
            "content_available",
            "fused_score",
            "kind",
            "locator",
            "page",
            "pointer_note",
            "reranker_prob",
            "source_file",
            "text",
        ]

    def test_pipeline_search_with_a_filter_reports_what_ran(self, _baseline_kb):
        # `headings` exists on the kb_ text table only, so the dense arm
        # applies the predicate and the visual arm must REPORT it did not.
        out = asyncio.new_event_loop().run_until_complete(
            pipeline.search(rm._composition(), "kb", "cadence months", 3, where="headings = ''")
        )
        assert out["filter_applied"] == "headings = ''"
        assert out["filter_report"]["text_dense"] == "applied"
        assert out["filter_report"]["visual"].startswith("not applied")
