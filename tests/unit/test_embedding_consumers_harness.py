"""Harness tests (TASK_EMBEDDINGGEMMA2_PLATFORM_V1 Phase 3).

Offline: a bag-of-words fake stands in for the EG2 service, so these tests
prove the probes load the REAL repo fixtures and produce well-formed results —
not that EG2 is good (that is the live run's job).
"""

from __future__ import annotations

import hashlib
import math
import re

import pytest

from portal.platform.embedding import contract as ec
from tests.benchmarks.embedding_consumers import framework as fw
from tests.benchmarks.embedding_consumers import probes as _probes  # noqa: F401

_TOK = re.compile(r"[a-z0-9]+")


class BagOfWordsClient:
    async def embed_texts(self, texts, *, task, role, dim, titles=None):  # type: ignore[no-untyped-def]
        out = []
        for i, t in enumerate(texts):
            text = f"{titles[i]} {t}" if titles and titles[i] else t
            v = [0.0] * dim
            for tok in _TOK.findall(text.lower()):
                v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim] += 1.0
            out.append(ec.l2_normalize(v) if any(v) else [1.0] + [0.0] * (dim - 1))
        return out

    async def version_tag(self, dim: int) -> str:
        return f"bow:{dim}d"


def test_ledger_ids_unique_and_registry_subset() -> None:
    assert len(fw.CONSUMER_IDS) == len(set(fw.CONSUMER_IDS))
    assert set(fw.registry()) <= set(fw.CONSUMER_IDS)


def test_probe_decorator_rejects_unknown_and_duplicate() -> None:
    with pytest.raises(KeyError):
        fw.probe("not_in_ledger")
    with pytest.raises(KeyError):
        fw.probe("router")(lambda ctx: None)  # type: ignore[arg-type,return-value]


def test_metrics() -> None:
    assert fw.accuracy(["a", "b"], ["a", "c"]) == 0.5
    assert fw.recall_at_k([["x", "y"], ["z"]], [["y"], ["q"]], 2) == 0.5
    assert math.isclose(fw.mrr([["x", "y"]], [["y"]]), 0.5)
    assert fw.auc([0.9, 0.8], [0.1]) == 1.0
    assert fw.macro_f1(["a", "a"], ["a", "b"]) == pytest.approx((2 / 3 + 0) / 2)
    assert fw.compare(0.80, 0.81) == "PARITY" and fw.compare(0.8, 0.9) == "BETTER"
    assert fw.compare(0.9, 0.8) == "WORSE"


async def test_missing_probe_is_not_implemented_and_fails_gate() -> None:
    ctx = fw.ProbeContext(client=BagOfWordsClient())
    res = await fw.run(["generation_dedup"], ctx)
    assert res[0].status in (fw.NOT_IMPLEMENTED, fw.MEASURED, fw.BLOCKED)
    if res[0].status == fw.NOT_IMPLEMENTED:
        assert not fw.gate_ok(res)


@pytest.mark.parametrize("cid", ["tool_preselect", "attack_mapping", "wiki_search"])
async def test_reference_probes_run_offline_on_real_fixtures(
    cid: str, tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    if cid == "wiki_search":
        # Real canonical units, bounded to keep the unit suite fast.
        import portal_wiki.mcp as wiki_mcp
        from portal.platform.wiki import store

        subset = sorted(store.load_all(), key=lambda u: u.id)[:40]
        monkeypatch.setattr(store, "load_all", lambda: subset)
        monkeypatch.setattr(wiki_mcp, "load_all", lambda: subset)
    ctx = fw.ProbeContext(client=BagOfWordsClient(), options={"wiki_sample": "20"})
    [res] = await fw.run([cid], ctx)
    assert res.status == fw.MEASURED, res.notes
    assert res.candidate.get("primary") is not None
    out = fw.write([res], tmp_path)
    assert (out / "SCORECARD.md").read_text().count(cid) == 1


async def test_router_probe_runs_or_blocks_honestly() -> None:
    ctx = fw.ProbeContext(client=BagOfWordsClient())
    [res] = await fw.run(["router"], ctx)
    # Before Phase 1 canonicalises the golden set this must BLOCK with a reason;
    # after, it must MEASURE. Never ERROR, never silently pass.
    assert res.status in (fw.MEASURED, fw.BLOCKED), res.notes
    if res.status == fw.BLOCKED:
        assert "retired workspace ids" in res.blocked_reason or "leakage" in res.blocked_reason
