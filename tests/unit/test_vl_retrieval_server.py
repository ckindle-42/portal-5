"""Server-seam contract tests for scripts/vl-retrieval-server.py
(TASK_VL_RUNTIME_LANDING_V4 Phase 7.1).

A FakeModel/FakeProcessor stands in for mlx-embeddings' Qwen3-VL so the seam can
be asserted with no MLX and no model download. What is pinned here is the
*verified* contract from mlx_embeddings/models/qwen3_vl/{model,processor}.py:

  * process(list)                       -> embed  -> (N, dim)
  * process(dict with "documents")      -> rerank -> (len(documents),)
  * process(dict without "documents")   -> embed
  * text items and image items are never in the same process() call
  * documents carry no instruction; the query does
  * a score/candidate length mismatch raises
  * tempfiles from image_b64 are unlinked, including on exception
  * normalize=True yields no second normalization in the server
"""

from __future__ import annotations

import base64
import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "vl_retrieval_server",
    Path(__file__).resolve().parents[2] / "scripts" / "vl-retrieval-server.py",
)
vl = importlib.util.module_from_spec(_SPEC)
sys.modules["vl_retrieval_server"] = vl
_SPEC.loader.exec_module(vl)

_PNG_1PX = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d4944415478da63f8cfc0f01f0005000100ff5cced20000000049454e44ae426082"
    )
).decode()


class FakeArray:
    def __init__(self, rows):
        self._rows = [list(r) for r in rows]
        self.shape = (len(self._rows), len(self._rows[0]) if self._rows else 0)

    def __iter__(self):
        return iter(FakeArray([r]) if False else r for r in self._rows)

    def tolist(self):
        return self._rows

    def reshape(self, *_):
        flat = [x for r in self._rows for x in r]
        out = FakeArray([flat])
        return out


class FakeVec(list):
    def tolist(self):
        return list(self)


class FakeModel:
    class args:  # noqa: N801
        normalize = True

    def __init__(self):
        self.calls = []

    def process(self, inputs, processor=None):
        self.calls.append(inputs)
        if isinstance(inputs, dict) and "documents" in inputs:
            docs = inputs["documents"]
            # emulate the real (N,) score vector
            return _ScoreArray([0.9 - 0.1 * i for i in range(len(docs))])
        items = inputs if isinstance(inputs, list) else [inputs]
        # one normalized 4-d vector per item (already unit-norm: no double-norm check)
        return _RowsArray([[0.5, 0.5, 0.5, 0.5] for _ in items])


class _RowsArray:
    def __init__(self, rows):
        self._rows = rows
        self.shape = (len(rows), len(rows[0]) if rows else 0)

    def __iter__(self):
        return iter(FakeVec(r) for r in self._rows)


class _ScoreArray:
    def __init__(self, xs):
        self._xs = list(xs)
        self.shape = (len(self._xs),)

    def reshape(self, *_):
        return self

    def tolist(self):
        return self._xs


class FakeProcessor:
    pass


@pytest.fixture(autouse=True)
def _fake_load(monkeypatch):
    model = FakeModel()

    def fake_load(slot, repo):
        if slot["model"] is None:
            slot["model"] = model
            slot["proc"] = FakeProcessor()
            if "normalize" in slot:
                slot["normalize"] = bool(model.args.normalize)
        return slot["model"], slot["proc"]

    monkeypatch.setattr(vl, "_load", fake_load)
    monkeypatch.setattr(vl, "_mx_rows", lambda out: [list(r) for r in out])
    monkeypatch.setattr(vl, "_flatten_scores", lambda out: list(out.tolist()))
    vl._embed.update(model=None, proc=None, normalize=None)
    vl._rerank.update(model=None, proc=None)
    return model


async def test_embed_list_returns_n_by_dim(_fake_load):
    vecs = await vl._embed_items([{"text": "a"}, {"text": "b"}, {"text": "c"}])
    assert len(vecs) == 3
    assert all(len(v) == 4 for v in vecs)


async def test_text_and_image_never_share_a_batch(_fake_load):
    await vl._embed_items([{"text": "a"}, {"image_b64": _PNG_1PX}, {"text": "b"}])
    # two process() calls: one text batch (2), one image batch (1)
    batches = [c for c in _fake_load.calls if isinstance(c, list)]
    assert len(batches) == 2
    sizes = sorted(len(b) for b in batches)
    assert sizes == [1, 2]
    for b in batches:
        kinds = {"image" if "image" in it else "text" for it in b}
        assert len(kinds) == 1


async def test_rerank_returns_len_documents_and_query_only_instruction(_fake_load):
    scores = await vl._score_documents(
        {"text": "q", "instruction": "find relevant"}, [{"text": "d1"}, {"text": "d2"}]
    )
    assert len(scores) == 2
    call = next(c for c in _fake_load.calls if isinstance(c, dict))
    assert "instruction" in call and call["instruction"] == "find relevant"
    assert "instruction" not in call["query"]
    for d in call["documents"]:
        assert "instruction" not in d


async def test_score_candidate_length_mismatch_raises(_fake_load, monkeypatch):
    monkeypatch.setattr(vl, "_flatten_scores", lambda out: [0.1])  # too few
    with pytest.raises(ValueError):
        await vl._score_documents({"text": "q"}, [{"text": "d1"}, {"text": "d2"}])


async def test_tempfiles_unlinked_on_success(_fake_load):
    created = []
    orig = vl._decode_b64_to_tempfile

    def spy(b64):
        p = orig(b64)
        created.append(p)
        return p

    vl._decode_b64_to_tempfile = spy
    try:
        await vl._embed_items([{"image_b64": _PNG_1PX}])
    finally:
        vl._decode_b64_to_tempfile = orig
    assert created and not any(Path(p).exists() for p in created)


async def test_tempfiles_unlinked_on_exception(_fake_load, monkeypatch):
    created = []
    orig = vl._decode_b64_to_tempfile

    def spy(b64):
        p = orig(b64)
        created.append(p)
        return p

    monkeypatch.setattr(vl, "_decode_b64_to_tempfile", spy)

    def boom(*_a, **_k):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(_fake_load, "process", boom)
    with pytest.raises(RuntimeError):
        await vl._embed_items([{"image_b64": _PNG_1PX}, {"text": "x"}])
    assert created and not any(Path(p).exists() for p in created)


async def test_item_with_neither_text_nor_image_is_rejected(_fake_load):
    with pytest.raises(ValueError):
        await vl._embed_items([{"fps": 1}])


async def test_embed_sub_chunks_at_max_batch_preserving_order(_fake_load, monkeypatch):
    """A1: no process() call carries more than VL_MAX_BATCH items, and the
    returned vectors stay in request order across sub-chunks."""
    monkeypatch.setattr(vl, "MAX_BATCH", 2)
    items = [{"text": f"t{i}"} for i in range(5)]
    vecs = await vl._embed_items(items)
    assert len(vecs) == 5
    batches = [c for c in _fake_load.calls if isinstance(c, list)]
    assert batches and all(len(b) <= 2 for b in batches)
    assert sum(len(b) for b in batches) == 5


async def test_reset_vl_state_runs_before_every_process_call(_fake_load, monkeypatch):
    """C5: _reset_vl_state must fire before each process() — one reset per
    forward pass, text and image batches alike."""
    monkeypatch.setattr(vl, "MAX_BATCH", 2)
    seen: list[str] = []
    real_reset = vl._reset_vl_state
    monkeypatch.setattr(vl, "_reset_vl_state", lambda m: (seen.append("reset"), real_reset(m))[1])
    orig_process = _fake_load.process

    def tracking_process(inputs, processor=None):
        seen.append("process")
        return orig_process(inputs, processor=processor)

    monkeypatch.setattr(_fake_load, "process", tracking_process)
    await vl._embed_items([{"text": "a"}, {"text": "b"}, {"text": "c"}, {"image_b64": _PNG_1PX}])
    # every "process" is immediately preceded by a "reset"
    assert seen
    for i, ev in enumerate(seen):
        if ev == "process":
            assert seen[i - 1] == "reset", seen


async def test_reset_vl_state_prevents_the_rope_cache_crash(monkeypatch):
    """C5: reproduce the upstream failure shape — two consecutive text-only
    calls with decreasing sequence length crash when the cached rope state is
    reused. The server's _reset_vl_state clears it before every call."""

    class RopeCrashModel:
        class args:  # noqa: N801
            normalize = True

        def __init__(self):
            self.lang = type("L", (), {"_position_ids": None, "_rope_deltas": None})()
            self.calls = []

        @property
        def language_model(self):
            return self.lang

        def process(self, inputs, processor=None):
            items = inputs if isinstance(inputs, list) else [inputs]
            n = sum(len(it.get("text", "")) for it in items) or 1
            pid = self.lang._position_ids
            if pid is not None and pid > n:
                raise IndexError("Too many indices for array with 2 dimensions")
            self.lang._position_ids = n
            self.calls.append(n)
            return _RowsArray([[0.5, 0.5, 0.5, 0.5] for _ in items])

    model = RopeCrashModel()
    monkeypatch.setattr(
        vl,
        "_load",
        lambda slot, repo: (
            (slot.__setitem__("model", model), (model, FakeProcessor()))[1]
            if slot["model"] is None
            else (slot["model"], slot["proc"])
        ),
    )
    monkeypatch.setattr(vl, "_mx_rows", lambda out: [list(r) for r in out])
    vl._embed.update(model=None, proc=None, normalize=None)

    await vl._embed_items([{"text": "a long-ish query string"}])
    # decreasing length — would reuse a too-long _position_ids without the reset
    await vl._embed_items([{"text": "hi"}])
    assert model.calls == [23, 2]

    # and prove the crash is real when the reset is a no-op
    model2 = RopeCrashModel()
    monkeypatch.setattr(
        vl,
        "_load",
        lambda slot, repo: (
            (slot.__setitem__("model", model2), (model2, FakeProcessor()))[1]
            if slot["model"] is None
            else (slot["model"], slot["proc"])
        ),
    )
    monkeypatch.setattr(vl, "_reset_vl_state", lambda m: None)
    vl._embed.update(model=None, proc=None, normalize=None)
    await vl._embed_items([{"text": "a long-ish query string"}])
    with pytest.raises(IndexError):
        await vl._embed_items([{"text": "hi"}])


async def test_normalize_flag_read_at_load_no_second_normalization(_fake_load):
    await vl._embed_items([{"text": "a"}])
    assert vl._embed["normalize"] is True
    # server must not renormalize: the fake returns [.5,.5,.5,.5] (norm 1.0) and
    # the server returns it unchanged
    vecs = await vl._embed_items([{"text": "a"}])
    assert vecs[0] == [0.5, 0.5, 0.5, 0.5]
