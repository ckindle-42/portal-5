"""P6R amendment 1: near-verbatim split, copy-probe scoring, graded-fixture collection."""

from __future__ import annotations

from types import SimpleNamespace

from portal.modules.compliance.core.citation_by_quote import _fold
from scripts.compliance.truth import copy_probe as cp
from scripts.compliance.truth.citation_integrity import _quote_record
from scripts.compliance.truth.quote_fidelity import edit_kind

SOURCE = "The vendor portal does not directly access any BES Cyber System"
VOCAB = frozenset(_fold(SOURCE).split()) | {"car"}


def test_edit_inside_a_word_is_garbled():
    assert edit_kind("the vendor portal does not directly acess any", SOURCE, VOCAB) == "garbled"


def test_non_word_token_is_garbled():
    assert edit_kind("the vendor portal does nxt directly access", SOURCE, VOCAB) == "garbled"


def test_whole_word_substitution_is_altered():
    assert edit_kind("the vendor portal does car directly access", SOURCE, VOCAB) == "altered"


def _store(*texts):
    return SimpleNamespace(
        _citation_by_quote_index={f"s{i}": (_fold(t), "doc") for i, t in enumerate(texts)}
    )


def test_integrity_record_carries_kind_from_store_vocabulary():
    store = _store(SOURCE, "a car was parked")
    altered = _quote_record(store, SOURCE.replace("does not", "does car"), 2)
    garbled = _quote_record(store, SOURCE.replace("access", "acess"), 2)
    assert (altered["status"], altered["near_kind"]) == ("near_verbatim", "altered")
    assert (garbled["status"], garbled["near_kind"]) == ("near_verbatim", "garbled")
    assert altered["near_matches"][0]["kind"] == "altered"


def test_copy_probe_scores_meaning_change_separately_from_garbling():
    src = "The entity shall not grant access within 30 days"
    assert cp.score_copy(src, src)["exact"] is True
    typo = cp.score_copy(src, "The entity shall not grant acess within 30 days")
    assert typo["edits"] == 1 and typo["meaning_changed"] is False
    flipped = cp.score_copy(src, "The entity shall grant access within 30 days")
    assert flipped["meaning_changed"] is True
    number = cp.score_copy(src, "The entity shall not grant access within 90 days")
    assert number["meaning_changed"] is True
    modal = cp.score_copy(src, "The entity may not grant access within 30 days")
    assert modal["meaning_changed"] is True


def test_copy_probe_prompt_embeds_passage_and_summary_aggregates():
    prompt = cp.build_prompt("alpha beta gamma", "x" * 10)
    assert "<<<BEGIN PASSAGE>>>\nalpha beta gamma\n<<<END PASSAGE>>>" in prompt
    rows = [
        {"source": "abcd", **cp.score_copy("abcd", "abcd")},
        {"source": "abcd", **cp.score_copy("abcd", "abxd")},
        {"source": "abcd", "error": "boom"},
    ]
    summary = cp.summarise(rows)
    assert summary["n_scored"] == 2 and summary["exact"] == 1
    assert summary["errors_per_1000"] == 125.0


def test_whole_tree_collection_ignores_only_graded_wfe_fixtures():
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    addopts = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"][
        "addopts"
    ]
    assert "--ignore=tests/wfe/graded" in addopts
    # the WFE grader copies these into its own tmp dir, so the ignore cannot hide them from it
    assert "shutil.copy2(gf, tmp / gf.name)" in (root / "tests/wfe/checkers.py").read_text()


def test_copy_probe_builds_padding_off_the_worker_threads(monkeypatch):
    import threading

    main = threading.get_ident()
    monkeypatch.setattr(
        cp,
        "sample_passages",
        lambda store, n, seed: [
            {"section_id": f"s{i}", "side": "operator", "text": "a b"} for i in range(4)
        ],
    )

    def pad(store, need, sid, seed):
        assert threading.get_ident() == main  # the store connection is not thread-safe
        return "x"

    monkeypatch.setattr(cp, "padding", pad)
    monkeypatch.setattr(
        cp,
        "ask",
        lambda *a, **k: {
            "text": "<<<BEGIN PASSAGE>>>\na b\n<<<END PASSAGE>>>",
            "route": "r",
            "wall_s": 0,
        },
    )
    out = cp.run(
        None,
        None,
        router="",
        key="",
        workspace="w",
        build="b",
        mode="t0",
        pressure=0.01,
        window=1000,
        n=4,
        seed=0,
        concurrency=4,
    )
    assert out["summary"]["n_scored"] == 4
