"""Entity-level (BOTS-style) key scoring: scenario -> step -> artefact, no raw log tree."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from portal.modules.security.core.hunt.notables import scoreboard as board
from portal.modules.security.core.hunt.notables.scoreboard import ScoreboardError, main, score

FIRST = 1502400000.0


def _notable(
    generator: str,
    text: str,
    *,
    terms: tuple[str, ...] = (),
    p_yes: float | None = None,
    content_key: str = "",
) -> dict[str, Any]:
    query = 'search index="botsv2" ' + " ".join(f'TERM("{term}")' for term in terms)
    row: dict[str, Any] = {
        "notable_id": content_key or generator,
        "generator": generator,
        "source_id": "botsv2:stream:dns",
        "content_key": content_key or f"{generator}-{text[:20]}",
        "what": text,
        "entities": [],
        "evidence": [{"line": text, "query": query, "earliest": FIRST, "latest": FIRST + 3600.0}],
    }
    if p_yes is not None:
        row["p_yes"] = p_yes
    return row


def _key(
    scenario: str,
    step: str,
    value: str,
    *,
    role: str = "artefact",
    entity: str = "domain",
    admitted: bool | None = True,
    count: int | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "dataset": "botsv2",
        "scenario": scenario,
        "step": step,
        "value": value,
        "entity": entity,
        "role": role,
        "citations": ["https://example.invalid/writeup §Q1"],
        "locator": f'| tstats count where index=botsv2 TERM("{value}")',
        "admitted": admitted,
        "audit": None if count is None else {"count": count},
    }
    return row


def _run(
    tmp_path: Path,
    *,
    notables: list[dict[str, Any]],
    keys: list[dict[str, Any]],
    index: str = "botsv2",
    relate: dict[str, Any] | None = None,
    run_name: str = "bots",
) -> Path:
    run = tmp_path / run_name
    run.mkdir(parents=True, exist_ok=True)
    (run / "notables.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in notables), encoding="utf-8"
    )
    (run / "progress.json").write_text(
        json.dumps(
            {
                "stages": {
                    "cards": {"seconds": 1.0, "model_requests": 1, "peak_memory_mb": 10.0},
                    "notables": {"seconds": {"total": 2.0}, "peak_memory_mb": 20.0},
                    "judge": {"seconds": 3.0, "requests": 2, "peak_memory_mb": 30.0},
                },
                "peak_memory_mb": 30.0,
            }
        ),
        encoding="utf-8",
    )
    (run / "sources.json").write_text(
        json.dumps({"index": index, "cards": [{"facts": {"sources": ["stream:dns"]}}]}),
        encoding="utf-8",
    )
    (run / "keys.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in keys), encoding="utf-8"
    )
    if relate is not None:
        (run / "relate.json").write_text(json.dumps(relate), encoding="utf-8")
    return run


def _family(tmp_path: Path, **kwargs: Any) -> dict[str, Any]:
    run = _run(tmp_path, **kwargs)
    return score(run, [str(run / "keys.jsonl")])["families"][0]


def test_artefact_in_evidence_covers_its_step_and_scenario_with_cuts(tmp_path: Path) -> None:
    keys = [
        _key("fruitfly", "c2_beacon", "eidk.duckdns.org", count=12),
        _key("fruitfly", "c2_beacon", "eidk.hopto.org", count=8),
        _key("fruitfly", "usb_delivery", "Important_HR_INFO_for_mkraeusen", entity="file"),
    ]
    fillers = [_notable("deviation", f"noise {index}") for index in range(60)]
    hit = _notable(
        "peer_rare", "dns query eidk.duckdns.org", terms=("eidk.duckdns.org",), p_yes=0.9
    )
    family = _family(tmp_path, notables=[*fillers, hit], keys=keys)
    assert family["mode"] == "entity"
    artefacts = {row["value"]: row for row in family["artefacts"]}
    assert artefacts["eidk.duckdns.org"]["first_rank"] == 60
    assert artefacts["eidk.duckdns.org"]["events"] == 12
    assert artefacts["eidk.duckdns.org"]["covered"] == {"50": False, "100": True, "None": True}
    assert artefacts["eidk.hopto.org"]["first_rank"] is None
    steps = {step["step"]: step for step in family["steps"]}
    assert steps["fruitfly/c2_beacon"]["first_rank"] == 60
    assert steps["fruitfly/c2_beacon"]["lines"] == 20
    assert steps["fruitfly/usb_delivery"]["first_rank"] is None
    scenarios = {step["step"]: step for step in family["scenarios"]}
    assert scenarios["fruitfly"]["first_rank"] == 60
    assert family["recall"]["overall"] == {"50": 0, "100": 1, "None": 1}
    assert family["scenario_recall"]["overall"] == {"50": 0, "100": 1, "None": 1}
    assert family["notables"]["covering"] == 1
    assert family["judge"] is not None and family["judge"]["bad"] == 1


def test_asset_match_never_finds_a_scenario_but_is_reported(tmp_path: Path) -> None:
    keys = [
        _key("fruitfly", "c2_beacon", "eidk.duckdns.org"),
        _key("fruitfly", "usb_delivery", "kutekitten", role="asset", entity="host", count=6088),
    ]
    family = _family(
        tmp_path,
        notables=[_notable("alerts", "osquery event on kutekitten")],
        keys=keys,
    )
    assert family["notables"]["covering"] == 0
    assert family["scenarios"][0]["first_rank"] is None
    assert family["recall"]["overall"]["None"] == 0
    assets = {row["value"]: row for row in family["assets"]}
    assert assets["kutekitten"]["first_rank"] == 0


def test_entity_values_match_on_word_boundaries(tmp_path: Path) -> None:
    keys = [_key("brewertalk_web", "xss_cookie_theft", "1502408189", entity="cookie")]
    embedded = _notable("deviation", "epoch 15024081891234 seen", content_key="embedded")
    exact = _notable("peer_rare", "cookie=1502408189; path=/", content_key="exact")
    family = _family(tmp_path, notables=[embedded, exact], keys=keys)
    assert family["artefacts"][0]["first_rank"] == 1


def test_admitted_false_is_excluded_and_pending_is_scored_and_flagged(tmp_path: Path) -> None:
    keys = [
        _key("taedonggang_phish", "empire", "invoice.doc", entity="file", admitted=False),
        _key("taedonggang_phish", "spearphish", "invoice.zip", entity="file", admitted=None),
    ]
    family = _family(
        tmp_path,
        notables=[_notable("alerts", "smtp attachment invoice.zip and invoice.doc")],
        keys=keys,
    )
    values = [row["value"] for row in family["artefacts"]]
    assert values == ["invoice.zip"]
    assert family["keys"]["not_admitted"] == 1
    assert family["keys"]["pending_audit"] == 1
    assert "pending" in board.render(family).lower()


def test_proof_index_keys_are_rejected(tmp_path: Path) -> None:
    keys = [_key("phish", "spearphish", "invoice.zip")]
    for row in keys:
        row["dataset"] = "botsv1"
    run = _run(tmp_path, notables=[_notable("alerts", "x")], keys=keys, index="botsv1")
    with pytest.raises(ScoreboardError, match="proof"):
        score(run, [str(run / "keys.jsonl")])


def test_keys_from_another_index_are_rejected(tmp_path: Path) -> None:
    keys = [_key("fruitfly", "c2_beacon", "eidk.duckdns.org")]
    run = _run(tmp_path, notables=[_notable("alerts", "x")], keys=keys, index="botsv3")
    with pytest.raises(ScoreboardError, match="another"):
        score(run, [str(run / "keys.jsonl")])


def test_relate_cases_report_scenario_rank_and_false_cases_above(tmp_path: Path) -> None:
    keys = [_key("fruitfly", "c2_beacon", "eidk.duckdns.org")]
    relate = {
        "receipt": {"cases": 2},
        "notables": [
            {
                "notable_id": "relate-1",
                "generator": "relate",
                "anchor_rank": 0,
                "relation_score": 1.0,
                "source_id": "botsv2:stream:dns",
                "evidence": [
                    {
                        "line": "query[A] eidk.duckdns.org",
                        "query": 'search index="botsv2" TERM("eidk.duckdns.org")',
                        "earliest": FIRST,
                        "latest": FIRST + 60.0,
                    }
                ],
            }
        ],
        "cases": [
            {
                "case_id": "case-false",
                "evidence": [{"host": "web", "source": "/x.log", "time": FIRST, "line": "benign"}],
            },
            {
                "case_id": "case-true",
                "evidence": [
                    {
                        "host": "kutekitten",
                        "source": "/dns.log",
                        "time": FIRST,
                        "line": "query[A] eidk.duckdns.org",
                    }
                ],
            },
        ],
    }
    family = _family(tmp_path, notables=[_notable("deviation", "noise")], keys=keys, relate=relate)
    relation = family["relate"]
    assert relation["before"]["overall"]["None"] == 0
    assert relation["after"]["overall"]["None"] == 1
    assert relation["after"]["by_generator"]["relate"] == {"50": 1, "100": 1, "None": 1}
    assert relation["first_true_case_rank"] == 1
    assert relation["false_cases_above_first_true"] == 1
    assert relation["case_rows"][1]["scenarios"] == ["fruitfly"]


def test_artefact_located_through_the_index_normalization_form(tmp_path: Path) -> None:
    value = "나는_데이비드를_사랑한다.hwp"  # NFC key value, 17 code points
    nfd = unicodedata.normalize("NFD", value)  # the index's spelling, 32 code points
    assert unicodedata.normalize("NFC", nfd) == value
    keys = [_key("taedonggang_phish", "ftp_download", value, entity="file")]
    indexed = _notable("peer_rare", f"ftp download {nfd}", terms=(nfd,), content_key="nfd")
    composed = _notable("peer_rare", f"ftp download {value}", terms=(value,), content_key="nfc")
    family = _family(tmp_path, notables=[indexed, composed], keys=keys)
    artefact = family["artefacts"][0]
    assert artefact["first_rank"] == 0  # the NFD evidence line locates the NFC key value
    assert artefact["covered"] == {"50": True, "100": True, "None": True}
    assert family["notables"]["covering"] == 2
    steps = {step["step"]: step for step in family["steps"]}
    assert steps["taedonggang_phish/ftp_download"]["first_rank"] == 0


def test_render_and_main_print_the_entity_report(tmp_path: Path, capsys: Any) -> None:
    keys = [
        _key("fruitfly", "c2_beacon", "eidk.duckdns.org", count=12),
        _key("fruitfly", "usb_delivery", "kutekitten", role="asset", entity="host"),
    ]
    run = _run(
        tmp_path,
        notables=[_notable("peer_rare", "dns eidk.duckdns.org", p_yes=0.8)],
        keys=keys,
    )
    assert main(["--out", str(run), "--keys", f"bots={run / 'keys.jsonl'}"]) == 0
    printed = capsys.readouterr().out
    assert "mode entity" in printed
    assert "fruitfly/c2_beacon" in printed
    assert "eidk.duckdns.org" in printed
    assert "scenarios  top50 1/1" in printed
