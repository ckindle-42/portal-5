"""Unit tests for portal.platform.embedding (TASK_EMBEDDINGGEMMA2_PLATFORM_V1).

No network: the client runs against httpx.MockTransport.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from portal.platform.embedding import contract as ec
from portal.platform.embedding.classifier import (
    AnchorClassifier,
    AnchorSet,
    leakage,
)


def _vec(text: str, dim: int = 768) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    raw = [((h[i % len(h)] + i * 31) % 97) - 48.0 for i in range(dim)]
    return ec.l2_normalize(raw)


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


def test_leakage_detects_normalized_overlap() -> None:
    assert leakage(["Write  a Python script"], ["write a python script", "other"]) == [
        "write a python script"
    ]
    assert leakage(["a"], ["b"]) == []
