"""Unit tests for portal.platform.embedding (TASK_EMBEDDINGGEMMA2_PLATFORM_V1).

No network: the client runs against httpx.MockTransport.
"""

from __future__ import annotations

import hashlib
import json
import math

import httpx
import pytest

from portal.platform.embedding import contract as ec
from portal.platform.embedding.classifier import (
    AnchorClassifier,
    AnchorSet,
    leakage,
    load_anchor_set,
)
from portal.platform.embedding.client import EmbeddingClient, EmbeddingUnavailableError


def _vec(text: str, dim: int = 768) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    raw = [((h[i % len(h)] + i * 31) % 97) - 48.0 for i in range(dim)]
    return ec.l2_normalize(raw)


# ── contract ────────────────────────────────────────────────────────────────
def test_prefixes_match_model_card() -> None:
    assert ec.format_text("x", ec.Task.SEARCH, ec.Role.QUERY) == "task: search result | query: x"
    assert ec.format_text("x", ec.Task.SEARCH, ec.Role.DOCUMENT) == "title: none | text: x"
    assert ec.format_text("x", ec.Task.SEARCH, ec.Role.DOCUMENT, "T") == "title: T | text: x"
    assert (
        ec.format_text("x", ec.Task.CODE_RETRIEVAL, ec.Role.QUERY)
        == "task: code retrieval | query: x"
    )
    # symmetric tasks ignore role
    for role in ec.Role:
        assert (
            ec.format_text("x", ec.Task.CLASSIFICATION, role) == "task: classification | query: x"
        )
        assert ec.format_text("x", ec.Task.CLUSTERING, role) == "task: clustering | query: x"


def test_parse_task_and_role() -> None:
    assert ec.parse_task("search result") is ec.Task.SEARCH
    assert ec.parse_task("SENTENCE_SIMILARITY") is ec.Task.SENTENCE_SIMILARITY
    assert ec.parse_role("document") is ec.Role.DOCUMENT
    with pytest.raises(ValueError):
        ec.parse_task("summarize")
    with pytest.raises(ValueError):
        ec.parse_role("passage")


def test_truncate_renormalizes_and_rejects_untrained_dims() -> None:
    v = _vec("a")
    t = ec.truncate(v, 256)
    assert len(t) == 256
    assert math.isclose(math.sqrt(sum(x * x for x in t)), 1.0, rel_tol=1e-9)
    with pytest.raises(ValueError):
        ec.truncate(v, 300)
    with pytest.raises(ValueError):
        ec.truncate(v[:100], 128)


def test_identity_version_tag_roundtrip() -> None:
    ident = ec.Identity(
        "google/embeddinggemma-2", "abcdef0123456789", 768, "bfloat16", "mps", "st", ("text",)
    )
    assert ident.version_tag(256) == "google/embeddinggemma-2@abcdef012345:256d"
    assert ec.Identity.from_dict(ident.to_dict()) == ident


def test_has_nan() -> None:
    assert ec.has_nan([0.1, float("nan")])
    assert not ec.has_nan([0.1, 0.2])


# ── client ──────────────────────────────────────────────────────────────────
def _service(
    model: str = "google/embeddinggemma-2", wrong_dim: bool = False
) -> httpx.MockTransport:
    ident = ec.Identity(model, "rev123", 768, "bfloat16", "mps", "fake", ("text",)).to_dict()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ready":
            return httpx.Response(200, json={"ready": True, "identity": ident})
        body = json.loads(request.content)
        if request.url.path == "/embed":
            dim = body["dim"]
            task, role = ec.parse_task(body["task"]), ec.parse_role(body["role"])
            vecs = [
                ec.truncate(_vec(ec.format_text(i["text"], task, role, i.get("title"))), dim)
                for i in body["inputs"]
            ]
            if wrong_dim:
                vecs = [v[:-1] for v in vecs]
            return httpx.Response(200, json={"embeddings": vecs, "dim": dim, "model": model})
        if request.url.path == "/embed_items":
            vecs = [
                ec.truncate(_vec(json.dumps(i, sort_keys=True)), body["dim"]) for i in body["items"]
            ]
            return httpx.Response(
                200, json={"embeddings": vecs, "dim": body["dim"], "model": model}
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_client_embeds_with_server_side_prefix() -> None:
    c = EmbeddingClient("http://svc", transport=_service())
    [q] = await c.embed_texts(["hello"], task=ec.Task.SEARCH, role=ec.Role.QUERY, dim=256)
    [d] = await c.embed_texts(["hello"], task=ec.Task.SEARCH, role=ec.Role.DOCUMENT, dim=256)
    assert len(q) == 256 and q != d
    assert await c.version_tag(256) == "google/embeddinggemma-2@rev123:256d"


async def test_client_rejects_wrong_model_and_wrong_dim() -> None:
    c = EmbeddingClient(
        "http://svc",
        transport=_service(model="other/model"),
        expected_model="google/embeddinggemma-2",
    )
    with pytest.raises(EmbeddingUnavailableError):
        await c.identity()
    with pytest.raises(EmbeddingUnavailableError):
        await c.embed_texts(["x"], task=ec.Task.SEARCH)
    c2 = EmbeddingClient("http://svc", transport=_service(wrong_dim=True))
    with pytest.raises(EmbeddingUnavailableError):
        await c2.embed_texts(["x"], task=ec.Task.SEARCH, dim=128)


async def test_client_rejects_untrained_dim_before_network() -> None:
    c = EmbeddingClient("http://svc", transport=_service())
    with pytest.raises(ValueError):
        await c.embed_texts(["x"], task=ec.Task.SEARCH, dim=300)


async def test_client_unreachable_maps_to_unavailable() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    c = EmbeddingClient("http://svc", transport=httpx.MockTransport(boom))
    with pytest.raises(EmbeddingUnavailableError):
        await c.embed_texts(["x"], task=ec.Task.SEARCH)


# ── classifier ──────────────────────────────────────────────────────────────
class _FakeClient:
    """Embeds by bag-of-letters so semantically 'close' toy strings are close."""

    async def embed_texts(self, texts, *, task, role, dim):  # type: ignore[no-untyped-def]
        out = []
        for t in texts:
            v = [0.0] * dim
            for ch in t.lower():
                if ch.isalpha():
                    v[(ord(ch) - 97) % dim] += 1.0
            out.append(ec.l2_normalize(v) if any(v) else [1.0] + [0.0] * (dim - 1))
        return out

    async def version_tag(self, dim: int) -> str:
        return f"fake:{dim}d"


async def test_anchor_classifier_picks_label_and_abstains() -> None:
    aset = AnchorSet(
        name="t",
        task=ec.Task.CLASSIFICATION,
        dim=128,
        labels={"aaa": ["aaaa", "aaab"], "zzz": ["zzzz", "zzzy"]},
        min_score=0.5,
        min_margin=0.05,
        top_k=2,
    )
    fc = _FakeClient()
    clf = await AnchorClassifier.build(aset, fc)
    assert clf.version == "fake:128d"
    d = await clf.classify_text("aaaaa", fc)
    assert d.label == "aaa" and not d.abstained and d.margin > 0
    d2 = await clf.classify_text("mmmm", fc)
    assert d2.abstained and d2.label is None


def test_load_anchor_set_validates(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "a.json"
    p.write_text(
        json.dumps({"name": "x", "task": "classification", "dim": 256, "labels": {"a": ["x"]}})
    )
    s = load_anchor_set(p)
    assert s.dim == 256 and s.task is ec.Task.CLASSIFICATION
    p.write_text(json.dumps({"labels": {"a": []}}))
    with pytest.raises(ValueError):
        load_anchor_set(p)
    p.write_text(json.dumps({"dim": 300, "labels": {"a": ["x"]}}))
    with pytest.raises(ValueError):
        load_anchor_set(p)


def test_leakage_detects_normalized_overlap() -> None:
    assert leakage(["Write  a Python script"], ["write a python script", "other"]) == [
        "write a python script"
    ]
    assert leakage(["a"], ["b"]) == []
