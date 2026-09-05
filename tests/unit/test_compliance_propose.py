"""Reliability regressions for real coverage retrieval (no live model/queue)."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from portal.modules.compliance.core import propose as p
from portal.modules.compliance.core.applicability import AssetScope
from portal.modules.compliance.core.cip_register import Register
from portal.modules.compliance.core.coverage import ProposalError, coverage_matrix
from portal.modules.compliance.core.mapping_store import MappingStore
from portal.platform.retrieval import embedding, pipeline

REAL_SEARCH = pipeline.search
TARGET = next(n for n in Register.load().nodes if n.id == "CIP-007-6 R5 Part 5.4")
OTHER = next(n for n in Register.load().nodes if n.id == "CIP-007-6 R1 Part 1.1")
SCOPE = AssetScope(impact_present={"high", "medium"}, declared_by="test")
TEXT = "Change known default passwords, per Cyber Asset capability."


def hit(doc, text=TEXT, **extra):
    return {"source_file": doc, "chunk_index": 43, "page": 11, "text": text, **extra}


@pytest.fixture
def wired(monkeypatch, tmp_path):
    search = AsyncMock(return_value={"results": [hit("policy.pdf"), hit("procedure.pdf")]})
    rerank = AsyncMock(return_value=[{"index": 1, "score": 0.9}, {"index": 0, "score": 0.95}])
    review = Mock(return_value=SimpleNamespace(id="review-id"))
    monkeypatch.setattr(pipeline, "search", search)
    monkeypatch.setattr(embedding, "vl_rerank", rerank)
    monkeypatch.setattr(p.rq, "propose", review)
    monkeypatch.setattr(
        p,
        "read_sidecar",
        lambda: {
            "policy.pdf": {"layer": "policy", "standard_hint": "CIP-003"},
            "procedure.pdf": {"layer": "procedure", "standard_hint": "CIP-007"},
        },
    )
    return SimpleNamespace(
        search=search, rerank=rerank, review=review, store=MappingStore(tmp_path / "mappings.json")
    )


def matrix(wired, nodes=None):
    return coverage_matrix(
        Register(nodes=nodes or [TARGET]), SCOPE, "2026-09-04", p.make_real_proposer(), wired.store
    )


def test_isolated_and_sweep_use_identical_query_candidates_and_scores(wired):
    isolated = matrix(wired).cells[0]
    sweep = matrix(wired, [OTHER, TARGET]).cells[1]
    assert isolated.to_dict() == sweep.to_dict()
    assert isolated.coverage == "FULL"
    assert isolated.policy_spans == sweep.policy_spans
    assert isolated.procedure_spans == sweep.procedure_spans
    assert [c.args[2] for c in wired.search.await_args_list] == [
        TARGET.verbatim_text,
        OTHER.verbatim_text,
        TARGET.verbatim_text,
    ]
    assert wired.search.await_count == wired.rerank.await_count == 3
    # The cloned coverage composition excludes image-only pointers, without
    # changing the general multimodal composition.
    assert wired.search.await_args.args[0].visual_table("operator_corpus") is None


def test_image_pointer_cannot_poison_the_text_rerank_batch(wired):
    wired.search.return_value["results"] += [
        hit("policy.pdf", None, kind="visual", content_available=False),
        hit("policy.pdf", "   "),
        hit("policy.pdf", "[page image]", content_available=False),
    ]
    cell = matrix(wired).cells[0]
    assert cell.coverage == "FULL"
    assert wired.rerank.await_args.args[1] == [{"text": TEXT}, {"text": TEXT}]
    assert len(cell.policy_spans) == 1


def test_compact_citation_keeps_the_matched_part_and_preserves_verbatim_text(wired):
    from portal.modules.compliance.tools.compliance_mcp import _compact_citation

    text = (
        "Previous unrelated Part. " * 30
        + TEXT.replace("default passwords", "default  passwords")
        + " (Part 5.4)"
    )
    wired.search.return_value = {"results": [hit("policy.pdf", text), hit("procedure.pdf", text)]}
    cell = matrix(wired).cells[0]
    citation = _compact_citation(cell.policy_spans)
    assert citation["span"].startswith("Change known default")
    assert "(Part 5.4)" in citation["span"]
    assert citation["span"] in text
    assert cell.coverage == "FULL"


def test_representative_citation_uses_the_highest_rerank_score(wired):
    from portal.modules.compliance.tools.compliance_mcp import _compact_citation

    wired.search.return_value["results"].append(
        {
            **hit("procedure.pdf", "Default accounts must have their passwords changed."),
            "chunk_index": 26,
        }
    )
    wired.rerank.return_value = [
        {"index": 2, "score": 0.95},
        {"index": 0, "score": 0.9},
        {"index": 1, "score": 0.6},
    ]
    cell = matrix(wired).cells[0]
    assert "#chunk26" in _compact_citation(cell.procedure_spans)["section"]


def test_visual_boost_cannot_evict_policy_from_coverage_pool(wired, monkeypatch):
    from portal.modules.compliance.tools import compliance_retrieval as cr
    from portal.platform.retrieval import store

    text_rows = [
        {
            **hit("policy.pdf" if i == 14 else "procedure.pdf"),
            "chunk_id": f"t{i}",
            "chunk_index": i,
            "_distance": 1.5,
        }
        for i in range(15)
    ]
    visual_rows = [
        {
            "chunk_id": f"v{i}",
            "source_file": "procedure.pdf",
            "page": i,
            "image_path": f"/fake/page-{i}.png",
        }
        for i in range(15)
    ]
    text_table, visual_table = Mock(), Mock()
    text_table.search.return_value.limit.return_value.to_list.return_value = text_rows
    visual_table.search.return_value.limit.return_value.to_list.return_value = visual_rows
    monkeypatch.setattr(pipeline, "search", REAL_SEARCH)
    monkeypatch.setattr(store, "text_table", lambda *a, **kw: text_table)
    monkeypatch.setattr(store, "visual_table", lambda *a, **kw: visual_table)
    monkeypatch.setattr(store, "assert_embedding_space", lambda *a, **kw: None)
    monkeypatch.setattr(embedding, "vl_model_id", AsyncMock(return_value=("fake", 8)))
    monkeypatch.setattr(embedding, "vl_embed", AsyncMock(return_value=[0.1] * 8))

    async def score(query, candidates, top_n):
        return [{"index": i, "score": 0.95} for i in range(len(candidates))]

    wired.rerank.side_effect = score
    general = asyncio.run(
        REAL_SEARCH(cr._composition(), "operator_corpus", TARGET.verbatim_text, 15)
    )
    assert all(h["kind"] == "visual" for h in general["results"])
    visual_table.reset_mock()
    cell = matrix(wired).cells[0]
    assert cell.coverage == "FULL"
    assert cell.policy_spans[0]["document_id"] == "policy.pdf"
    visual_table.search.assert_not_called()
    assert all("text" in c for c in wired.rerank.await_args.args[1])


def test_folder_filter_preserves_cross_cutting_policy(wired):
    wired.search.return_value["results"].append(hit("other.pdf"))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            p,
            "read_sidecar",
            lambda: {
                "policy.pdf": {"layer": "policy", "standard_hint": "CIP-003"},
                "procedure.pdf": {"layer": "procedure", "standard_hint": "CIP-007"},
                "other.pdf": {"layer": "procedure", "standard_hint": "CIP-014"},
            },
        )
        cell = matrix(wired).cells[0]
    assert cell.coverage == "FULL"
    assert [s["document_id"] for s in cell.procedure_spans] == ["procedure.pdf"]


@pytest.mark.parametrize("stage", ["search", "rerank"])
def test_failure_is_unresolved_and_sweep_continues(wired, stage):
    operation = getattr(wired, stage)
    good = operation.return_value
    operation.side_effect = [RuntimeError("service unavailable"), good]
    result = matrix(wired, [TARGET, OTHER])
    failed, good_cell = result.cells
    assert failed.coverage == "NEEDS_REVIEW"
    assert not failed.substantively_resolved
    assert failed.to_dict()["retrieval_errors"] == [
        {"stage": stage, "error": "RuntimeError: service unavailable"}
    ]
    assert good_cell.coverage == "FULL"
    assert result.summary()["full_gaps"] == []
    assert result.summary()["examined"] == 2
    assert result.summary()["substantively_resolved"] == 1


@pytest.mark.parametrize("stage", ["search", "rerank"])
def test_call_timeout_does_not_switch_to_keyword_coverage(wired, monkeypatch, stage):
    async def hang(*args):
        await asyncio.Event().wait()

    getattr(wired, stage).side_effect = hang
    monkeypatch.setattr(p, f"{stage.upper()}_CALL_TIMEOUT_S", 0.01)
    cell = matrix(wired).cells[0]
    assert cell.coverage == "NEEDS_REVIEW"
    assert "TimeoutError" in cell.retrieval_errors[0]["error"]
    assert not cell.substantively_resolved


@pytest.mark.parametrize(
    "ranked",
    [
        [],
        [{"index": 0, "score": 0.9}],
        [{"index": 0, "score": 0.9}, {"index": 0, "score": 0.9}],
        [{"index": -1, "score": 0.9}, {"index": 1, "score": 0.9}],
        [{"index": True, "score": 0.9}, {"index": 0, "score": 0.9}],
        [{"index": 0, "score": float("nan")}, {"index": 1, "score": 0.9}],
        [{"index": 0, "score": float("inf")}, {"index": 1, "score": 0.9}],
        [{"index": 0, "score": 1.1}, {"index": 1, "score": 0.9}],
    ],
)
def test_malformed_or_incomplete_rerank_is_not_a_gap(wired, ranked):
    wired.rerank.return_value = ranked
    cell = matrix(wired).cells[0]
    assert cell.coverage == "NEEDS_REVIEW"
    assert cell.retrieval_errors[0]["stage"] == "rerank"


def test_ambiguous_policy_is_reviewable_not_a_substantively_resolved_gap(wired):
    wired.rerank.return_value = [{"index": 0, "score": 0.4}, {"index": 1, "score": 0.9}]
    cell = matrix(wired).cells[0]
    assert cell.coverage == "NEEDS_REVIEW"
    assert not cell.substantively_resolved
    assert cell.policy_spans[0]["queue_item_id"] == "review-id"
    assert wired.review.call_args.kwargs["proposed_value"]["rerank_score"] == 0.4


def test_ambiguous_span_is_excluded_from_conflict_detection(wired):
    """A candidate that only scored into the ambiguous middle (queued, not
    locatable) must not be compared for COMPLIANCE_CONFLICT — live on the real
    corpus this produced false conflicts (a policy-review cadence flagged
    against an unrelated procedure's delegation-update deadline, purely
    because both spans happened to mention a duration)."""
    node = replace(
        TARGET,
        verbatim_text="Reinforce cyber security practices at least once every 15 calendar months.",
    )
    wired.search.return_value = {
        "results": [
            hit(
                "policy.pdf",
                "Reinforce cyber security practices at least once every 15 calendar months.",
            ),
            hit(
                "procedure.pdf", "Unrelated delegation updates occur within 30 days of any change."
            ),
        ]
    }
    wired.rerank.return_value = [{"index": 0, "score": 0.9}, {"index": 1, "score": 0.4}]
    cell = matrix(wired, [node]).cells[0]
    assert cell.procedure_spans[0]["locatable"] is False
    assert cell.conflicts == []


def test_locatable_but_topically_dissimilar_span_is_not_a_conflict(wired):
    """A candidate can score high enough to be locatable (real on the live
    corpus: rerank rewards broad semantic relevance) while its own quoted
    duration belongs to a different, topically distant obligation than the
    one just reused from a shared vocabulary word. Requiring topical overlap
    between the two spans catches this case; it does NOT catch the harder
    live pattern where the conflicting duration sits in a different bullet of
    the *same* broadly on-topic paragraph — see the reliability report for
    that open, unresolved residual."""
    node = replace(
        TARGET,
        verbatim_text=(
            "Enforce a password change at least once every 15 calendar months for "
            "interactive user access, where technically feasible."
        ),
    )
    wired.search.return_value = {
        "results": [
            hit(
                "policy.pdf",
                "Enforce a password change at least once every 15 calendar months for "
                "interactive user access, where technically feasible.",
            ),
            hit(
                "procedure.pdf",
                "A delegate may act on a Senior Manager's behalf; delegations are "
                "documented and updated within 30 calendar days of any change.",
            ),
        ]
    }
    wired.rerank.return_value = [{"index": 0, "score": 0.9}, {"index": 1, "score": 0.9}]
    cell = matrix(wired, [node]).cells[0]
    assert cell.procedure_spans[0]["locatable"] is True
    assert cell.conflicts == []


def test_successful_empty_search_is_a_gap(wired):
    wired.search.return_value = {"results": []}
    cell = matrix(wired).cells[0]
    assert cell.coverage == "NONE"
    assert cell.substantively_resolved
    wired.rerank.assert_not_awaited()


def test_direct_proposer_surfaces_errors_to_other_callers(wired):
    wired.search.side_effect = RuntimeError("unavailable")
    with pytest.raises(ProposalError, match="unavailable"):
        p.make_real_proposer()(TARGET, "policy")


@pytest.mark.parametrize("verbose", [False, True])
def test_tool_output_exposes_failed_retrieval(wired, monkeypatch, verbose):
    from portal.modules.compliance.core import mapping_store, scope_derive
    from portal.modules.compliance.tools.compliance_mcp import compliance_gaps

    monkeypatch.setattr(scope_derive, "derive_scope", lambda kb: (SCOPE, {}))
    monkeypatch.setattr(mapping_store, "MappingStore", lambda: wired.store)
    monkeypatch.setattr(p.rq, "sync_proposed_mappings", lambda store: 0)
    monkeypatch.setattr(p.rq, "open_items", lambda **kw: [])
    wired.rerank.side_effect = RuntimeError("unavailable")
    result = compliance_gaps(standard=TARGET.standard, requirement="R5 Part 5.4", verbose=verbose)
    assert "error" not in result
    row = result["rows"][0]
    assert row["coverage"] == "NEEDS_REVIEW"
    assert not row["substantively_resolved"]
    assert row["retrieval_errors"][0]["stage"] == "rerank"
    assert result["summary"]["substantively_resolved"] == 0
