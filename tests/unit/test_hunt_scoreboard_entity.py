"""Entity-level (BOTS-style) key scoring: scenario -> step -> artefact, no raw log tree."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

import duckdb
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
    klass: str | None = None,
    credit: bool | None = None,
    requires: list[str] | None = None,
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
    if klass is not None:
        row["class"] = klass
    if credit is not None:
        row["credit"] = credit
    if requires is not None:
        row["requires"] = requires
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


def _family(
    tmp_path: Path, *, causes: dict[str, str] | None = None, **kwargs: Any
) -> dict[str, Any]:
    run = _run(tmp_path, **kwargs)
    extra = []
    if causes is not None:
        path = run / "causes.json"
        path.write_text(json.dumps(causes), encoding="utf-8")
        extra.append(f"{run.name}={path}")
    return score(run, [str(run / "keys.jsonl")], causes=extra)["families"][0]


def _store(
    run: Path,
    *,
    events: tuple[str, ...] = (),
    misfits: tuple[str, ...] = (),
) -> None:
    con = duckdb.connect(str(run / "behaviours.duckdb"))
    con.execute(
        "CREATE TABLE events (source_id VARCHAR, host VARCHAR, ts DOUBLE, actor VARCHAR,"
        " action VARCHAR, object VARCHAR, raw VARCHAR, query VARCHAR)"
    )
    for raw in events:
        con.execute("INSERT INTO events VALUES ('botsv2:st', 'h', 0, '', '', '', ?, '')", [raw])
    con.execute("CREATE TABLE misfits (source_id VARCHAR, shape VARCHAR, examples VARCHAR)")
    for shape in misfits:
        con.execute("INSERT INTO misfits VALUES ('botsv2:st', ?, '')", [shape])
    con.close()


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


def test_promoted_raw_relate_rows_do_not_improve_strict_or_case_recall(tmp_path: Path) -> None:
    key = _key("fruitfly", "c2_beacon", "eidk.duckdns.org")
    seed = _notable("peer_rare", "ordinary dns activity", content_key="seed")
    promoted = _notable(
        "relate", "raw event eidk.duckdns.org", terms=("eidk.duckdns.org",), content_key="raw"
    )
    case = {
        "case_id": "case-raw",
        "seed_notables": ["seed"],
        "related_notables": ["raw"],
        "evidence": [{"line": "raw event eidk.duckdns.org"}],
    }
    family = _family(
        tmp_path,
        notables=[seed, promoted],
        keys=[key],
        relate={
            "receipt": {"promotion": {"ids": [{"notable_id": "raw", "after_rank": 0}]}},
            "notables": [promoted],
            "cases": [case],
        },
    )

    assert family["strict_recall"]["overall"]["None"] == 0
    assert family["case_recall"]["overall"]["None"] == 0
    assert family["promotion_effect"]["with"]["strict_recall"]["overall"]["None"] == 0
    assert family["promotion_effect"]["without"]["case_recall"]["overall"]["None"] == 0


def test_ledger_separates_never_read_from_read_and_censored(tmp_path: Path) -> None:
    censored = _key("fruitfly", "c2_beacon", "eidk.duckdns.org")
    censored["locator"] = 'search index=botsv2 sourcetype="stream:dns" TERM("eidk.duckdns.org")'
    unread = _key("fruitfly", "usb_delivery", "Important_HR_INFO")
    unread["locator"] = 'search index=botsv2 sourcetype="syslog" TERM("Important_HR_INFO")'
    run = _run(
        tmp_path,
        notables=[_notable("peer_rare", "no key")],
        keys=[censored, unread],
    )
    (run / "ledger.jsonl").write_text(
        json.dumps(
            {
                "stage": "behaviours",
                "source_id": "botsv2:stream:dns",
                "part": None,
                "query": 'search index=botsv2 sourcetype="stream:dns"',
                "window_start": FIRST,
                "window_end": FIRST + 1,
                "rows": 1,
                "capped": True,
                "reason": "row_cap",
                "values_extracted": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    family = score(run, [str(run / "keys.jsonl")])["families"][0]
    causes = {row["step"].split("/")[-1]: row["cause"] for row in family["ceiling"]["per_step"]}

    assert causes == {"c2_beacon": "censored", "usb_delivery": "unreached"}


def test_generator_marginal_counts_top50_and_top100_loss(tmp_path: Path) -> None:
    key = _key("fruitfly", "c2_beacon", "eidk.duckdns.org")
    at_50 = [
        _notable("peer_rare", f"noise {index}", content_key=f"noise-{index}") for index in range(49)
    ]
    at_50.append(_notable("deviation", "eidk.duckdns.org", content_key="hit-50"))
    family_50 = _run(tmp_path, notables=at_50, keys=[key], run_name="at-50")
    progress = json.loads((family_50 / "progress.json").read_text())
    progress["stages"]["notables"].update(
        peer_rare={"existed": 49, "kept": 49},
        deviation={"existed": 1, "kept": 1},
        merge={"weights": {"peer_rare": 1, "deviation": 0}, "priority": ["peer_rare", "deviation"]},
    )
    (family_50 / "progress.json").write_text(json.dumps(progress))

    scored_50 = score(family_50, [str(family_50 / "keys.jsonl")])["families"][0]
    assert scored_50["generators"]["deviation"]["marginal@50"] == 1
    assert scored_50["generators"]["deviation"]["head@50"] == 1
    assert scored_50["generators"]["peer_rare"]["head@50"] == 49
    assert scored_50["generators"]["deviation"]["used_weight"] == 0

    at_51 = [
        _notable("peer_rare", f"noise {index}", content_key=f"late-noise-{index}")
        for index in range(50)
    ]
    at_51.append(_notable("alerts", "eidk.duckdns.org", content_key="hit-51"))
    family_51 = _run(tmp_path, notables=at_51, keys=[key], run_name="at-51")
    progress = json.loads((family_51 / "progress.json").read_text())
    progress["stages"]["notables"].update(
        peer_rare={"existed": 50, "kept": 50},
        alerts={"existed": 1, "kept": 1},
        merge={"weights": {"peer_rare": 1, "alerts": 0}, "priority": ["peer_rare", "alerts"]},
    )
    (family_51 / "progress.json").write_text(json.dumps(progress))

    scored_51 = score(family_51, [str(family_51 / "keys.jsonl")])["families"][0]
    assert scored_51["generators"]["alerts"]["marginal@50"] == 0
    assert scored_51["generators"]["alerts"]["marginal@100"] == 1


def test_marginal_weight_folds_average_remerge_losses_and_floor_unmeasured() -> None:
    weights = board._weights_block(
        [
            {
                "family": "a",
                "marginal_generators": {"deviation": {"candidates": 1, "marginal@50": 2}},
            },
            {
                "family": "b",
                "marginal_generators": {"deviation": {"candidates": 1, "marginal@50": 4}},
            },
        ]
    )

    assert weights["folds"][0]["weights"]["deviation"] == 3
    assert weights["folds"][1]["weights"]["deviation"] == 4
    assert weights["folds"][0]["weights"]["peer_rare"] == board.UNMEASURED_WEIGHT


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


def _sqli_notable() -> dict[str, Any]:
    """Row-34 shape from the stored botsv2 run: the query terms select mysql keyed events;
    the artefact values (/member.php, updatexml) appear nowhere in the notable text."""
    line = (
        '2017-08-08 17:58:59 hostname="gacrux", port="3306", database_name="mysql", '
        'EVENT_ID="11", Duration="0.000167", '
        "SQL_TEXT=\"SELECT * FROM mybb_users WHERE uid = '31'\""
    )
    return {
        "generator": "similar_to_known",
        "source_id": "botsv2:mysql:transaction:details",
        "content_key": "similar_to_known|botsv2:mysql:transaction:details|sqli",
        "what": "did SELECT * FROM mybb_users WHERE uid = '31' to mysql",
        "entities": [
            {"role": "action", "value": "SELECT * FROM mybb_users WHERE uid = '31'"},
            {"role": "object", "value": "mysql"},
        ],
        "evidence": [
            {
                "line": line,
                "query": 'search index="botsv2" sourcetype="mysql:transaction:details" '
                '(source="gacrux") "mybb_users" "SELECT" "mysql" | head 5',
                "earliest": 1502215139.569,
                "latest": 1504220160.271,
            }
        ],
    }


def _keyed_event(value: str, raw: str, source: str = "gacrux") -> str:
    return json.dumps(
        {
            "dataset": "botsv2",
            "scenario": "brewertalk_web",
            "step": "sql_injection",
            "value": value,
            "time": 1502215139.569,
            "source": source,
            "raw": raw,
        }
    )


def test_line_mode_scores_keyed_events_beside_entity_mode(tmp_path: Path) -> None:
    keys = [_key("brewertalk_web", "sql_injection", "updatexml", entity="payload", klass="B")]
    events = tmp_path / "keyed_events.jsonl"
    events.write_text(
        _keyed_event(
            "updatexml",
            "mysql> SELECT * FROM mybb_users WHERE uid = '31' and updatexml(1,1,1) -- gacrux",
        )
        + "\n",
        encoding="utf-8",
    )
    run = _run(tmp_path, notables=[_sqli_notable()], keys=keys)
    family = score(run, [str(run / "keys.jsonl")], keyed_events=[f"bots={events}"])["families"][0]
    assert family["recall"]["overall"]["None"] == 0  # entity mode: the value is never named
    line = family["line_mode"]
    assert line is not None and line["events"] == 1
    assert line["recall"]["overall"] == {"50": 1, "100": 1, "None": 1}
    steps = {step["step"]: step for step in line["steps"]}
    assert steps["brewertalk_web/sql_injection"]["first_rank"] == 0
    assert steps["brewertalk_web/sql_injection"]["by_generator"] == {"similar_to_known": 0}
    assert line["class_recall"]["B"]["covered"]["50"] == 1
    printed = board.render(family)
    assert "line mode" in printed and "strict" in printed


def test_line_mode_without_keyed_events_is_omitted(tmp_path: Path) -> None:
    keys = [_key("brewertalk_web", "sql_injection", "updatexml", entity="payload")]
    family = _family(tmp_path, notables=[_sqli_notable()], keys=keys)
    assert family["line_mode"] is None


def test_keyed_events_from_another_dataset_are_rejected(tmp_path: Path) -> None:
    keys = [_key("brewertalk_web", "sql_injection", "updatexml", entity="payload")]
    events = tmp_path / "keyed_events.jsonl"
    events.write_text(_keyed_event("updatexml", "raw") + "\n", encoding="utf-8")
    run = _run(tmp_path, notables=[_sqli_notable()], keys=keys, index="botsv3")
    (run / "sources.json").write_text(
        json.dumps({"index": "botsv2", "cards": [{"facts": {"sources": ["stream:dns"]}}]}),
        encoding="utf-8",
    )
    payload = events.read_text(encoding="utf-8").replace('"botsv2"', '"botsv1"')
    events.write_text(payload, encoding="utf-8")
    with pytest.raises(ScoreboardError, match="another dataset"):
        score(run, [str(run / "keys.jsonl")], keyed_events=[f"bots={events}"])


def test_strict_matches_only_what_basis_why_and_entities(tmp_path: Path) -> None:
    # real shape, botsv2 #30: the scanner IP sits only inside evidence lines
    evidence_line = (
        "[Fri Aug 11 12:02:10 2017] [error] [client 45.77.65.211] "
        "File does not exist: /var/www/html/1101"
    )
    loose_only = _notable("deviation", "error log burst")
    loose_only["evidence"][0]["line"] = evidence_line
    # real shape, botsv2 #18: the .hwp file name is an entity value and sits in `what`
    strict_hit = _notable("deviation", "first dns.py, last 나는_데이비드를_사랑한다.hwp")
    strict_hit["entities"] = [
        {"role": "actor", "value": "10.0.2.107"},
        {"role": "object", "value": "나는_데이비드를_사랑한다.hwp"},
    ]
    keys = [
        _key("brewertalk_web", "web_scan", "45.77.65.211", entity="ip", klass="B"),
        _key(
            "taedonggang_phish",
            "ftp_download",
            "나는_데이비드를_사랑한다.hwp",
            entity="file",
            klass="P",
        ),
    ]
    family = _family(tmp_path, notables=[loose_only, strict_hit], keys=keys)
    artefacts = {row["value"]: row for row in family["artefacts"]}
    assert artefacts["45.77.65.211"]["first_rank"] == 0
    assert artefacts["45.77.65.211"]["first_rank_strict"] is None
    assert artefacts["나는_데이비드를_사랑한다.hwp"]["first_rank"] == 1
    assert artefacts["나는_데이비드를_사랑한다.hwp"]["first_rank_strict"] == 1
    assert family["recall"]["overall"] == {"50": 2, "100": 2, "None": 2}
    assert family["strict_recall"]["overall"] == {"50": 1, "100": 1, "None": 1}
    assert "strict" in board.render(family)


def test_shared_key_credits_its_first_step_only(tmp_path: Path) -> None:
    keys = [
        _key("brewertalk_web", "web_scan", "45.77.65.211", entity="ip", klass="B", count=168004),
        _key("taedonggang_phish", "c2_ssl", "45.77.65.211", entity="ip", klass="B", count=168004),
    ]
    hit = _notable("deviation", "[client 45.77.65.211] File does not exist")
    family = _family(tmp_path, notables=[hit], keys=keys)
    steps = {step["step"]: step for step in family["steps"]}
    assert steps["brewertalk_web/web_scan"]["first_rank"] == 0
    assert "taedonggang_phish/c2_ssl" not in steps
    assert family["keys"]["shared_keys"] == 1
    shared = {row["value"]: row for row in family["artefacts"]}
    assert shared["45.77.65.211"]["first_rank"] == 0  # located, reported
    assert shared["45.77.65.211"]["shared_step"] == "brewertalk_web/web_scan"
    assert family["recall"]["overall"] == {"50": 1, "100": 1, "None": 1}
    assert family["scenario_recall"]["overall"]["None"] == 1  # taedonggang has nothing left
    assert "shared" in board.render(family)


def test_shared_key_events_land_on_the_owning_step_in_line_mode(tmp_path: Path) -> None:
    keys = [
        _key("brewertalk_web", "web_scan", "45.77.65.211", entity="ip", klass="B"),
        _key("taedonggang_phish", "c2_ssl", "45.77.65.211", entity="ip", klass="B"),
    ]
    events = tmp_path / "keyed_events.jsonl"
    events.write_text(
        json.dumps(
            {
                "dataset": "botsv2",
                "scenario": "brewertalk_web",
                "step": "web_scan",
                "value": "45.77.65.211",
                "time": 1502452930.0,
                "source": "/var/log/httpd/error_log",
                "raw": "[client 45.77.65.211] File does not exist: /var/www/html/1101",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    hit = {
        "generator": "deviation",
        "source_id": "botsv2:apache_error",
        "content_key": "burst",
        "what": "error log burst",
        "entities": [],
        "evidence": [
            {
                "line": "burst",
                "query": 'search index="botsv2" (source="/var/log/httpd/error_log") | head 109',
                "earliest": 1502452800.0,
                "latest": 1502467200.0,
            }
        ],
    }
    run = _run(tmp_path, notables=[hit], keys=keys)
    family = score(run, [str(run / "keys.jsonl")], keyed_events=[f"bots={events}"])["families"][0]
    line = family["line_mode"]
    steps = {step["step"]: step for step in line["steps"]}
    assert steps["brewertalk_web/web_scan"]["first_rank"] == 0
    assert "taedonggang_phish/c2_ssl" not in steps
    assert line["recall"]["overall"]["None"] == 1


def test_no_credit_key_is_reported_but_never_covers(tmp_path: Path) -> None:
    keys = [
        _key(
            "brewertalk_web",
            "xss_cookie_theft",
            "1502408189",
            entity="cookie",
            klass="T",
            credit=False,
        ),
        _key("fruitfly", "c2_beacon", "eidk.hopto.org", entity="domain", klass="B"),
    ]
    cookie = _notable("deviation", "cookie=1502408189; path=/")
    family = _family(tmp_path, notables=[cookie], keys=keys)
    artefacts = {row["value"]: row for row in family["artefacts"]}
    assert artefacts["1502408189"]["first_rank"] == 0  # seen and reported
    assert artefacts["1502408189"]["covered"] == {"50": False, "100": False, "None": False}
    assert family["recall"]["overall"]["None"] == 0
    assert family["recall"]["steps"] == 2  # the no-credit step stays, uncoverable
    steps = {step["step"]: step for step in family["steps"]}
    assert steps["brewertalk_web/xss_cookie_theft"]["lines"] == 0
    assert steps["brewertalk_web/xss_cookie_theft"]["class"] == "T"
    assert family["class_recall"]["T"]["steps"] == 1
    assert family["class_recall"]["T"]["covered"]["None"] == 0
    assert family["keys"]["no_credit_keys"] == 1
    assert "no credit" in board.render(family)


def test_requires_demands_the_payload_before_the_uri_credits(tmp_path: Path) -> None:
    keys = [
        _key(
            "brewertalk_web",
            "sql_injection",
            "/member.php",
            entity="uri",
            klass="B",
            requires=["updatexml"],
        ),
        _key("brewertalk_web", "sql_injection", "updatexml", entity="payload", klass="B"),
    ]
    uri_only = _notable("alerts", "GET /member.php from one host")
    family = _family(tmp_path, notables=[uri_only], keys=keys)
    assert family["recall"]["overall"]["None"] == 0  # no payload located yet
    payload = _notable("deviation", "updatexml extract in the query string")
    family = _family(tmp_path, notables=[uri_only, payload], keys=keys)
    steps = {step["step"]: step for step in family["steps"]}
    assert steps["brewertalk_web/sql_injection"]["first_rank"] == 0
    assert family["recall"]["overall"]["None"] == 1


def test_class_recall_splits_behavioural_from_trivia(tmp_path: Path) -> None:
    keys = [
        _key("brewertalk_web", "web_scan", "45.77.65.211", entity="ip", klass="B"),
        _key("insider_leak", "executive_contact", "mberk@berkbeer.com", entity="email", klass="T"),
    ]
    hit = _notable("deviation", "smtp to mberk@berkbeer.com")
    family = _family(tmp_path, notables=[hit], keys=keys)
    classes = family["class_recall"]
    assert classes["T"]["covered"]["None"] == 1
    assert classes["T"]["steps"] == 1
    assert classes["B"]["covered"]["None"] == 0
    assert classes["B+P"]["steps"] == 1
    assert classes["B+P"]["covered"]["None"] == 0


def test_untagged_keys_leave_class_recall_empty(tmp_path: Path) -> None:
    keys = [_key("fruitfly", "c2_beacon", "eidk.hopto.org", entity="domain")]
    family = _family(tmp_path, notables=[_notable("alerts", "quiet day")], keys=keys)
    assert family["class_recall"] == {}


def test_ceiling_marks_a_read_artefact_reachable_and_charges_not_surfaced(tmp_path: Path) -> None:
    keys = [_key("fruitfly", "c2_beacon", "eidk.duckdns.org", count=12, klass="B")]
    run = _run(tmp_path, notables=[_notable("deviation", "quiet day")], keys=keys)
    _store(run, events=("query eidk.duckdns.org from 10.0.0.9",))
    family = score(run, [str(run / "keys.jsonl")])["families"][0]
    ceiling = family["ceiling"]
    assert ceiling["keys_reachable"] == 1
    assert ceiling["loose"]["reachable"] == 1
    assert ceiling["loose"]["covered"]["50"] == 0
    assert ceiling["loose"]["recall"]["50"] == 0.0
    assert ceiling["per_step"][0]["reachable"] is True
    assert ceiling["per_step"][0]["stores"] == ["events"]
    assert ceiling["per_step"][0]["cause"] == "not_surfaced"


def test_a_key_in_no_read_store_is_unreached(tmp_path: Path) -> None:
    keys = [_key("fruitfly", "c2_beacon", "eidk.hopto.org", count=8, klass="B")]
    run = _run(tmp_path, notables=[_notable("deviation", "quiet day")], keys=keys)
    _store(run)
    family = score(run, [str(run / "keys.jsonl")])["families"][0]
    assert family["ceiling"]["keys_reachable"] == 0
    assert family["ceiling"]["per_step"][0]["cause"] == "unreached"


def test_the_inventory_value_list_is_a_reachable_store(tmp_path: Path) -> None:
    keys = [_key("taedonggang_phish", "spearphish_attachment", "invoice.zip", klass="P")]
    run = _run(tmp_path, notables=[_notable("alerts", "quiet day")], keys=keys)
    (run / "inventory.json").write_text(
        json.dumps(
            {
                "fields": [
                    {
                        "field": "attach_filename",
                        "status": "complete",
                        "values": [{"value": "invoice.zip", "events": 9}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    family = score(run, [str(run / "keys.jsonl")])["families"][0]
    assert family["ceiling"]["per_step"][0]["reachable"] is True
    assert family["ceiling"]["per_step"][0]["stores"] == ["inventory"]


def test_audit_cause_overrides_the_derived_one(tmp_path: Path) -> None:
    keys = [_key("fruitfly", "c2_beacon", "eidk.hopto.org", count=8, klass="B")]
    family = _family(
        tmp_path,
        notables=[_notable("deviation", "quiet day")],
        keys=keys,
        causes={"fruitfly/c2_beacon": "design_limit"},
    )
    row = family["ceiling"]["per_step"][0]
    assert row["cause"] == "design_limit"
    assert row["cause_source"] == "audit"


def test_an_artefact_only_in_an_evidence_line_is_an_instrument_cause(tmp_path: Path) -> None:
    keys = [_key("fruitfly", "c2_beacon", "eidk.duckdns.org", count=12, klass="B")]
    hit = _notable("deviation", "quiet")
    hit["what"] = "dns beacon on one host"
    hit["evidence"][0]["line"] = "query eidk.duckdns.org from 10.0.0.9"
    run = _run(tmp_path, notables=[hit], keys=keys)
    _store(run, events=("query eidk.duckdns.org",))
    family = score(run, [str(run / "keys.jsonl")])["families"][0]
    assert family["strict_recall"]["overall"]["50"] == 0
    assert family["recall"]["overall"]["50"] == 1
    assert family["ceiling"]["per_step"][0]["cause"] == "instrument"
