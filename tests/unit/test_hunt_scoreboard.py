from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from portal.modules.security.core.hunt.notables import scoreboard as board
from portal.modules.security.core.hunt.notables.scoreboard import (
    QUIET_MAX_LINES,
    event_time,
    main,
    score,
)

FIRST = 1616529600.0  # 2021-03-23T20:00:00Z


def _line(actor: str, path: str, moment: float = FIRST + 60.0) -> str:
    stamp = time_stamp(moment)
    return f'{actor} - - [{stamp} +0000] "GET {path} HTTP/1.1" 200 12 "-" "curl"'


def time_stamp(moment: float) -> str:
    return board.time.strftime("%d/%b/%Y:%H:%M:%S", board.time.gmtime(moment))


def _notable(
    generator: str,
    source: str,
    terms: list[str],
    *,
    window: tuple[float, float] | None = None,
    p_yes: float | None = None,
    content_key: str = "",
) -> dict[str, Any]:
    query = f'search index="idx" (source="{source}") ' + " ".join(
        f'TERM("{term}")' for term in terms
    )
    row: dict[str, Any] = {
        "notable_id": content_key or generator,
        "generator": generator,
        "source_id": f"idx:{source.rsplit('/', 1)[-1]}",
        "content_key": content_key or f"{generator}-{source}-{'|'.join(terms)}",
        "entities": [{"role": "actor", "value": term} for term in terms],
        "evidence": [
            {
                "line": "example",
                "query": query,
                "earliest": window[0] if window else FIRST,
                "latest": window[1] if window else FIRST + 3600.0,
            }
        ],
    }
    if p_yes is not None:
        row["p_yes"] = p_yes
    return row


def _run(
    tmp_path: Path,
    *,
    notables: list[dict[str, Any]],
    keys: list[dict[str, Any]],
    files: dict[tuple[str, str], list[str]],
    indexed: list[str] | None = None,
    stages: dict[str, Any] | None = None,
    peak: float | None = 512.5,
    judge: dict[str, Any] | None = None,
) -> Path:
    run = tmp_path / "fam"
    run.mkdir(parents=True, exist_ok=True)
    (run / "notables.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in notables), encoding="utf-8"
    )
    progress: dict[str, Any] = {
        "stages": stages
        if stages is not None
        else {
            "cards": {
                "start": FIRST,
                "seconds": 10.0,
                "model_requests": 4,
                "peak_memory_mb": 100.0,
            },
            "behaviours": {"seconds_total": 20.0, "peak_memory_mb": 200.0},
            "notables": {
                "seconds": {"total": 30.0},
                "peak_memory_mb": 300.0,
                "similar_to_known": {
                    "excluded_family": "fam",
                    "loaded_families": ["other"],
                    "knowledge_items": 7,
                    "embedding_model": "unit-embed",
                    "reliability": {"auc": 0.75},
                },
            },
            "judge": {"seconds": 40.0, "requests": 6, "peak_memory_mb": 320.0},
        },
    }
    if peak is not None:
        progress["peak_memory_mb"] = peak
    (run / "progress.json").write_text(json.dumps(progress), encoding="utf-8")
    listed = sorted(indexed if indexed is not None else {source for _h, source in files})
    (run / "sources.json").write_text(
        json.dumps(
            {
                "index": "idx",
                "cards": [{"facts": {"sources": listed, "source_count": len(listed)}}],
            }
        ),
        encoding="utf-8",
    )
    if indexed is not None:
        (run / "ledger.jsonl").write_text(
            json.dumps(
                {
                    "stage": "cards",
                    "source_id": "",
                    "part": None,
                    "capped": False,
                    "reason": None,
                    "query": '| tstats count where index="idx" by sourcetype source',
                    "rows": len(listed),
                    "values_extracted": listed,
                    "window_start": 0.0,
                    "window_end": 0.0,
                }
            )
            + "\n",
            encoding="utf-8",
        )
    (run / "keys.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in keys), encoding="utf-8"
    )
    logs = tmp_path / "corpus" / "fam" / "gather"
    for (host, source), lines in files.items():
        path = logs / host / "logs" / source.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    keys_dir = tmp_path / "corpus" / "fam_ingest"
    keys_dir.mkdir(parents=True, exist_ok=True)
    (run / "keys.jsonl").replace(keys_dir / "keys.jsonl")
    (run / "keys.jsonl").symlink_to(keys_dir / "keys.jsonl")
    if judge is not None:
        cache = run / "cache"
        cache.mkdir(exist_ok=True)
        (cache / "judge.json").write_text(json.dumps(judge), encoding="utf-8")
    return run


def _keys(source: str, host: str, lines: dict[int, list[str]]) -> list[dict[str, Any]]:
    return [
        {"digest": f"d{number}", "host": host, "source": source, "line": number, "labels": labels}
        for number, labels in lines.items()
    ]


def _family(tmp_path: Path, **kwargs: Any) -> dict[str, Any]:
    run = _run(tmp_path, **kwargs)
    report = score(run, [str(run / "keys.jsonl")], logs=tmp_path / "corpus" / "fam" / "gather")
    return report["families"][0]


def test_recall_counts_each_step_once_and_reports_cuts_and_generators(
    tmp_path: Path,
) -> None:
    source = "/apache2/access.log.4"
    lines = [_line("10.0.0.5", f"/scan{index}") for index in range(3)]
    lines.extend(_line("10.0.0.9", "/index.html") for _ in range(2))
    keys = _keys(source, "web", {1: ["scan"], 2: ["scan"], 3: ["scan"], 4: ["login"], 5: ["login"]})
    notables = [_notable("alerts", source, ["nobody"], content_key="miss")]
    notables.extend(
        _notable(f"filler{index}", "/elsewhere.log", ["x"], content_key=f"f{index}")
        for index in range(120)
    )
    notables.append(_notable("peer_rare", source, ["10.0.0.5"], content_key="hit"))
    family = _family(
        tmp_path,
        notables=notables,
        keys=keys,
        files={("web", source): lines},
    )
    steps = {step["step"]: step for step in family["steps"]}
    assert steps["scan"]["lines"] == 3
    assert steps["scan"]["first_rank"] == 121
    assert steps["scan"]["covered"] == {"50": False, "100": False, "None": True}
    assert steps["login"]["first_rank"] is None
    assert steps["scan"]["by_generator"] == {"peer_rare": 121}
    assert family["recall"]["overall"] == {"50": 0, "100": 0, "None": 1}
    assert family["recall"]["by_generator"]["peer_rare"] == {"50": 0, "100": 0, "None": 1}
    assert family["recall"]["by_generator"]["alerts"] == {"50": 0, "100": 0, "None": 0}
    assert family["notables"]["covering"] == 1
    assert family["notables"]["cost"] == {"50": 50, "100": 100, "None": 122}


def test_quiet_and_loud_steps_split_on_the_printed_threshold(tmp_path: Path) -> None:
    source = "/auth.log"
    total = 2 * QUIET_MAX_LINES + 1
    lines = [
        f"Mar 23 {20 + index // 3600:02d}:{index % 3600 // 60:02d}:{index % 60:02d} sshd[1] line {index}"
        for index in range(total)
    ]
    keys = _keys(source, "web", {index: ["escalate"] for index in range(1, QUIET_MAX_LINES + 1)})
    keys += _keys(
        source,
        "web",
        {index: ["dirb"] for index in range(QUIET_MAX_LINES + 1, total + 1)},
    )
    family = _family(
        tmp_path,
        notables=[_notable("deviation", source, ["nothing-here"], content_key="none")],
        keys=keys,
        files={("web", source): lines},
    )
    steps = {step["step"]: step for step in family["steps"]}
    assert steps["escalate"]["lines"] == QUIET_MAX_LINES
    assert steps["escalate"]["quiet"] is True
    assert steps["dirb"]["quiet"] is False
    assert steps["dirb"]["lines"] == QUIET_MAX_LINES + 1
    assert family["recall"]["quiet"]["steps"] == 1
    assert family["recall"]["loud"]["steps"] == 1
    printed = board.render(family)
    assert f"quiet = a step with <= {QUIET_MAX_LINES} labelled lines" in printed
    assert "QUIET steps" in printed and "LOUD steps" in printed


def test_window_only_notable_covers_lines_inside_its_evidence_window(tmp_path: Path) -> None:
    source = "/dnsmasq.log"
    inside = [
        f"Mar 23 20:0{minute}:00 dnsmasq[1]: query[A] host{minute}.example" for minute in range(5)
    ]
    outside = [
        f"Mar 24 03:00:0{minute} dnsmasq[1]: query[A] other{minute}.example" for minute in range(5)
    ]
    keys = _keys(source, "fw", {1: ["dnsteal"], 2: ["dnsteal"]})
    keys += _keys(source, "fw", {6: ["quiet_step"], 7: ["quiet_step"]})
    burst = _notable("deviation", source, [], window=(FIRST, FIRST + 3600.0), content_key="burst")
    burst["evidence"][0]["query"] = '| tstats count where index="idx" by sourcetype _time span=1h'
    family = _family(
        tmp_path,
        notables=[burst],
        keys=keys,
        files={("fw", source): inside + outside},
    )
    steps = {step["step"]: step for step in family["steps"]}
    assert steps["dnsteal"]["first_rank"] == 0
    assert steps["quiet_step"]["first_rank"] is None
    assert family["notables"]["covering"] == 1


def test_relate_reports_step_recall_and_case_purity_against_keys(tmp_path: Path) -> None:
    import hashlib

    source = "/auth.log"
    labelled = "Mar 23 20:01:00 alice reverse_shell"
    unlabelled = "Mar 23 20:02:00 alice status"
    run = _run(
        tmp_path,
        notables=[_notable("peer_rare", source, ["nobody"], content_key="seed")],
        keys=_keys(source, "web", {1: ["reverse_shell"]}),
        files={("web", source): [labelled, unlabelled]},
    )
    moment = FIRST + 60
    related = {
        "notable_id": "relate-1",
        "generator": "relate",
        "source_id": "idx:auth.log",
        "evidence": [
            {
                "line": labelled,
                "query": f'search index="idx" source="{source}" TERM("reverse_shell")',
                "earliest": moment,
                "latest": moment + 1,
            }
        ],
    }
    event_refs = [
        {
            "host": "web",
            "source": source,
            "time": moment,
            "raw_sha256": hashlib.sha256(labelled.encode()).hexdigest(),
        },
        {
            "host": "web",
            "source": source,
            "time": moment + 60,
            "raw_sha256": hashlib.sha256(unlabelled.encode()).hexdigest(),
        },
    ]
    (run / "relate.json").write_text(
        json.dumps(
            {"notables": [related], "cases": [{"case_id": "case-1", "evidence": event_refs}]}
        ),
        encoding="utf-8",
    )

    family = score(
        run,
        [str(run / "keys.jsonl")],
        logs=tmp_path / "corpus" / "fam" / "gather",
    )["families"][0]

    assert family["relate"]["before"]["overall"]["None"] == 0
    assert family["relate"]["after"]["overall"] == {"50": 1, "100": 1, "None": 1}
    assert family["relate"]["case_purity"]["cases"][0]["purity"] == 0.5
    assert "relate recall before top50" in board.render(family)
    assert "case 1: case-1" in board.render(family)


def test_relate_rows_never_displace_stage1_ranks() -> None:
    first = {"notable_id": "stage1-0"}
    second = {"notable_id": "stage1-1"}
    relation = {"notable_id": "relate-0", "anchor_rank": 0, "relation_score": 1.0}

    ordered = board._with_related([first, second], [relation])

    assert ordered[:2] == [first, second]
    assert ordered[2:] == [relation]


def test_a_notable_naming_another_source_never_covers_a_labelled_line(tmp_path: Path) -> None:
    source = "/apache2/access.log.4"
    keys = _keys(source, "web", {1: ["dirb"]})
    other = _notable("peer_rare", "/elsewhere/access.log.4", ["10.0.0.5"], content_key="other")
    family = _family(
        tmp_path,
        notables=[other],
        keys=keys,
        files={("web", source): [_line("10.0.0.5", "/x")]},
    )
    assert family["steps"][0]["first_rank"] is None
    assert family["notables"]["covering"] == 0


def test_every_term_must_appear_for_a_notable_to_cover(tmp_path: Path) -> None:
    source = "/apache2/access.log.4"
    keys = _keys(source, "web", {1: ["dirb"]})
    partial = _notable("peer_rare", source, ["10.0.0.5", "POST"], content_key="partial")
    family = _family(
        tmp_path,
        notables=[partial],
        keys=keys,
        files={("web", source): [_line("10.0.0.5", "/x")]},
    )
    assert family["steps"][0]["first_rank"] is None


def test_claim_reads_plain_quoted_terms_and_skips_field_values() -> None:
    row = {
        "source_id": "idx:auth.log",
        "generator": "similar_to_known",
        "evidence": [
            {
                "query": (
                    'search index="idx" (source="/auth.log") "systemd-logind" "root" | head 5'
                ),
            }
        ],
    }
    claim = board._claim(row)
    assert claim.terms == ("systemd-logind", "root")
    assert claim.sources == frozenset({"/auth.log"})


def test_a_plain_quoted_notable_covers_a_labelled_line(tmp_path: Path) -> None:
    source = "/auth.log"
    keys = _keys(source, "web", {1: ["change_user"]})
    notable = {
        "notable_id": "plain",
        "generator": "similar_to_known",
        "source_id": f"idx:{source.rsplit('/', 1)[-1]}",
        "content_key": "plain",
        "entities": [{"role": "actor", "value": "systemd-logind"}],
        "evidence": [
            {
                "line": "example",
                "query": f'search index="idx" (source="{source}") "systemd-logind" "root" | head 5',
                "earliest": FIRST,
                "latest": FIRST + 3600.0,
            }
        ],
    }
    family = _family(
        tmp_path,
        notables=[notable],
        keys=keys,
        files={
            ("web", source): [
                "Mar 23 21:12:56 host systemd-logind[1]: New session of user root",
            ]
        },
    )
    assert family["steps"][0]["first_rank"] == 0


def test_judge_separation_uses_covered_notables_as_labelled_bad(tmp_path: Path) -> None:
    source = "/apache2/access.log.4"
    keys = _keys(source, "web", {1: ["dirb"]})
    notables = [
        _notable("alerts", source, ["10.0.0.5"], p_yes=0.9, content_key="bad1"),
        _notable("alerts", source, ["10.0.0.5"], p_yes=0.8, content_key="bad2"),
        _notable("peer_rare", "/other/access.log", ["nomatch"], p_yes=0.1, content_key="good1"),
        _notable("peer_rare", "/other/access.log", ["nomatch"], p_yes=0.2, content_key="good2"),
    ]
    family = _family(
        tmp_path,
        notables=notables,
        keys=keys,
        files={("web", source): [_line("10.0.0.5", "/x")]},
    )
    judge = family["judge"]
    assert judge is not None
    assert judge["bad"] == 2 and judge["good"] == 2
    assert judge["auc_all"] == 1.0
    assert judge["auc_pooled"] == 1.0
    assert judge["yes_rate_bad"] == 1.0
    assert judge["yes_rate_good"] == 0.0


def test_judge_cache_supplies_p_yes_when_the_receipts_carry_none(tmp_path: Path) -> None:
    source = "/apache2/access.log.4"
    keys = _keys(source, "web", {1: ["dirb"]})
    family = _family(
        tmp_path,
        notables=[
            _notable("alerts", source, ["10.0.0.5"], content_key="bad1"),
            _notable("alerts", source, ["10.0.0.5"], content_key="bad2"),
            _notable("peer_rare", "/other/access.log", ["nomatch"], content_key="good1"),
            _notable("peer_rare", "/other/access.log", ["nomatch"], content_key="good2"),
            _notable("peer_rare", "/other/access.log", ["nomatch"], content_key="good3"),
        ],
        keys=keys,
        files={("web", source): [_line("10.0.0.5", "/x")]},
        judge={
            "bad1": {"p_yes": 0.7},
            "bad2": {"p_yes": 0.6},
            "good1": {"p_yes": 0.4},
            "good2": {"p_yes": 0.2},
        },
    )
    judge = family["judge"]
    assert judge is not None
    assert judge["judged"] == 4
    assert judge["auc_all"] == 1.0
    assert judge["auc_pooled"] == 1.0


def test_judge_block_is_omitted_without_any_judge_result(tmp_path: Path) -> None:
    source = "/apache2/access.log.4"
    family = _family(
        tmp_path,
        notables=[_notable("alerts", source, ["10.0.0.5"], content_key="one")],
        keys=_keys(source, "web", {1: ["dirb"]}),
        files={("web", source): [_line("10.0.0.5", "/x")]},
    )
    assert family["judge"] is None
    assert "judge: no judge result" in board.render(family)


def test_judge_separation_is_reported_per_generator(tmp_path: Path) -> None:
    source = "/apache2/access.log.4"
    keys = _keys(source, "web", {1: ["dirb"]})
    family = _family(
        tmp_path,
        notables=[
            _notable("alerts", source, ["10.0.0.5"], p_yes=0.9, content_key="bad1"),
            _notable("alerts", source, ["10.0.0.5"], p_yes=0.8, content_key="bad2"),
            _notable("peer_rare", "/other/access.log", ["nomatch"], p_yes=0.1, content_key="good1"),
            _notable("peer_rare", "/other/access.log", ["nomatch"], p_yes=0.2, content_key="good2"),
        ],
        keys=keys,
        files={("web", source): [_line("10.0.0.5", "/x")]},
    )
    by_generator = family["judge"]["auc_by_generator"]
    assert by_generator["alerts"] == {
        "judged": 2,
        "bad": 2,
        "good": 0,
        "auc": None,
        "yes_rate": 1.0,
    }
    assert by_generator["peer_rare"] == {
        "judged": 2,
        "bad": 0,
        "good": 2,
        "auc": None,
        "yes_rate": 0.0,
    }


def test_the_pooled_judge_auc_excludes_a_rank_list_generator(tmp_path: Path) -> None:
    source = "/apache2/access.log.4"
    keys = _keys(source, "web", {1: ["dirb"]})
    family = _family(
        tmp_path,
        notables=[
            _notable("alerts", source, ["10.0.0.5"], p_yes=0.9, content_key="bad1"),
            _notable("peer_rare", "/other/access.log", ["nomatch"], p_yes=0.1, content_key="good1"),
            _notable("similar_to_known", "/ranked/access.log", ["nomatch"], p_yes=0.99),
            _notable("similar_to_known", "/ranked/access.log", ["nomatch"], p_yes=0.98),
        ],
        keys=keys,
        files={("web", source): [_line("10.0.0.5", "/x")]},
    )
    judge = family["judge"]
    assert judge["auc_pooled"] == 1.0
    assert judge["auc_all"] < judge["auc_pooled"]
    assert "similar_to_known" not in judge["auc_pooled_generators"]
    assert judge["ranked_judged"] == 2
    assert judge["ranked_yes_rate"] == 1.0
    assert judge["auc_by_generator"]["similar_to_known"]["judged"] == 2


def test_cost_rolls_up_stages_requests_and_peak_memory(tmp_path: Path) -> None:
    source = "/apache2/access.log.4"
    family = _family(
        tmp_path,
        notables=[_notable("alerts", source, ["10.0.0.5"], content_key="one")],
        keys=_keys(source, "web", {1: ["dirb"]}),
        files={("web", source): [_line("10.0.0.5", "/x")]},
    )
    cost = family["cost"]
    assert cost["seconds"] == 100.0
    assert cost["model_requests"] == 10
    assert cost["peak_memory_mb"] == 512.5
    assert cost["stages"]["notables"]["seconds"] == 30.0
    assert "total=100.0s model-requests=10" in board.render(family)


def test_honesty_reports_loaded_families_and_the_exclusion(tmp_path: Path) -> None:
    source = "/apache2/access.log.4"
    family = _family(
        tmp_path,
        notables=[_notable("alerts", source, ["10.0.0.5"], content_key="one")],
        keys=_keys(source, "web", {1: ["dirb"]}),
        files={("web", source): [_line("10.0.0.5", "/x")]},
    )
    assert family["honesty"] == {
        "knowledge": "loaded",
        "families": ["other"],
        "excluded_family": "fam",
        "knowledge_items": 7,
        "embedding_model": "unit-embed",
        "reliability_auc": 0.75,
    }
    assert "excluded fam" in board.render(family)


@pytest.mark.parametrize(
    "stages",
    [
        {
            "cards": {"seconds": 1.0},
            "notables": {"seconds": {"total": 2.0}},
        },
        {
            "cards": {"seconds": 1.0},
            "notables": {
                "seconds": {"total": 2.0},
                "similar_to_known": {"excluded_family": "someone-else"},
            },
        },
    ],
)
def test_a_missing_knowledge_receipt_or_another_family_fails_loudly(
    tmp_path: Path, stages: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    source = "/apache2/access.log.4"
    run = _run(
        tmp_path,
        notables=[_notable("alerts", source, ["10.0.0.5"], content_key="one")],
        keys=_keys(source, "web", {1: ["dirb"]}),
        files={("web", source): [_line("10.0.0.5", "/x")]},
        stages=stages,
    )
    code = main(["--out", str(run), "--keys", str(run / "keys.jsonl")])
    if "similar_to_known" in stages["notables"]:
        assert code == 2
        assert "learned from its own family" in capsys.readouterr().err
    else:
        assert code == 0
        assert "none loaded" in capsys.readouterr().out


def test_empty_keys_fail_loudly(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = "/apache2/access.log.4"
    run = _run(
        tmp_path,
        notables=[_notable("alerts", source, ["10.0.0.5"], content_key="one")],
        keys=_keys(source, "web", {1: ["dirb"]}),
        files={("web", source): [_line("10.0.0.5", "/x")]},
    )
    (run / "keys.jsonl").write_text("", encoding="utf-8")
    code = main(["--out", str(run), "--keys", str(run / "keys.jsonl")])
    assert code == 2
    assert "no labelled line" in capsys.readouterr().err


def test_keys_from_another_family_fail_loudly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = "/apache2/access.log.4"
    run = _run(
        tmp_path,
        notables=[_notable("alerts", source, ["10.0.0.5"], content_key="one")],
        keys=_keys("/elsewhere/other.log", "web", {1: ["dirb"]}),
        files={("web", source): [_line("10.0.0.5", "/x")]},
    )
    code = main(["--out", str(run), "--keys", str(run / "keys.jsonl"), "--logs", str(tmp_path)])
    assert code == 2
    assert "another family" in capsys.readouterr().err


def test_proof_indexes_are_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = "/apache2/access.log.4"
    run = _run(
        tmp_path,
        notables=[_notable("alerts", source, ["10.0.0.5"], content_key="one")],
        keys=_keys(source, "web", {1: ["dirb"]}),
        files={("web", source): [_line("10.0.0.5", "/x")]},
    )
    (run / "sources.json").write_text(
        json.dumps({"index": "botsv1", "cards": []}), encoding="utf-8"
    )
    code = main(["--out", str(run), "--keys", str(run / "keys.jsonl")])
    assert code == 2
    assert "proof index" in capsys.readouterr().err


def test_missing_receipts_fail_loudly(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run = tmp_path / "fam"
    run.mkdir()
    (run / "progress.json").write_text(json.dumps({"stages": {}}), encoding="utf-8")
    (run / "keys.jsonl").write_text(
        json.dumps({"digest": "d", "host": "h", "source": "/s", "line": 1, "labels": ["x"]}),
        encoding="utf-8",
    )
    code = main(["--out", str(run), "--keys", str(run / "keys.jsonl")])
    assert code == 2
    assert "holds no <family>/notables.jsonl" in capsys.readouterr().err


def test_the_same_keys_file_needs_a_family_prefix_for_several_families(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("one", "two"):
        run = tmp_path / name
        run.mkdir()
        (run / "notables.jsonl").write_text("{}\n", encoding="utf-8")
    code = main(["--out", str(tmp_path), "--keys", "k.jsonl"])
    assert code == 2
    assert "one family=path" in capsys.readouterr().err


def test_json_output_carries_the_rule_and_every_section(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = "/apache2/access.log.4"
    run = _run(
        tmp_path,
        notables=[_notable("alerts", source, ["10.0.0.5"], p_yes=0.9, content_key="one")],
        keys=_keys(source, "web", {1: ["dirb"]}),
        files={("web", source): [_line("10.0.0.5", "/x")]},
    )
    code = main(["--out", str(run), "--keys", str(run / "keys.jsonl"), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    family = payload["families"][0]
    assert set(family) == {
        "family",
        "index",
        "card_contract",
        "rule",
        "keys",
        "notables",
        "steps",
        "recall",
        "generators",
        "ceiling",
        "judge",
        "cost",
        "honesty",
    }
    assert family["keys"]["labelled_lines"] == 1
    assert family["steps"][0]["step"] == "dirb"
    assert family["judge"]["auc_all"] is None  # one class only: no separation to report
    assert family["rule"].startswith("a notable covers a labelled line")


def test_scoreboard_reports_consumers_for_mixed_source_cards(tmp_path: Path) -> None:
    source = "/suricata/eve.json"
    run = _run(
        tmp_path,
        notables=[_notable("alerts", source, ["ET scan"], content_key="alert")],
        keys=_keys(source, "sensor", {1: ["scan"]}),
        files={("sensor", source): [_line("10.0.0.5", "/scan")]},
    )
    cards = [
        {
            "index": "idx",
            "sourcetype": "eve.json",
            "kind": "activity",
            "understood": True,
            "roles": {"actor": ["src"], "action": ["proto"]},
            "part": {"field": "event_type", "value": "flow"},
        },
        {
            "index": "idx",
            "sourcetype": "eve.json",
            "kind": "alert",
            "understood": True,
            "roles": {"actor": ["src"], "action": ["sig"]},
            "part": {"field": "event_type", "value": "alert"},
        },
        {
            "index": "idx",
            "sourcetype": "eve.json",
            "kind": "measurement",
            "understood": True,
            "roles": {},
            "part": {"field": "event_type", "value": "stats"},
        },
    ]
    (run / "sources.json").write_text(
        json.dumps({"index": "idx", "cards": cards}), encoding="utf-8"
    )

    family = score(
        run,
        [str(run / "keys.jsonl")],
        logs=tmp_path / "corpus" / "fam" / "gather",
    )["families"][0]

    assert family["card_contract"]["by_kind"] == {"activity": 1, "alert": 1, "measurement": 1}
    assert family["card_contract"]["consumers"]["alerts"] == ["idx:eve.json#event_type=alert"]
    assert family["card_contract"]["consumers"]["similar_to_known"] == [
        "idx:eve.json#event_type=flow"
    ]


def test_event_time_reads_the_shapes_the_ingest_writes() -> None:
    assert event_time('[23/Mar/2021:20:32:09 +0000] "GET / HTTP/1.1"', 1970) == FIRST + 1929.0
    assert event_time('{"timestamp":"2021-03-23T13:59:50.462715+0000"}', 1970) == 1616507990.0
    assert event_time("Mar 23 20:00:00 dnsmasq[1]: query[A] x", 2021) == FIRST
    assert event_time("msg=audit(1616529600.795:103): pid=1", 1970) == 1616529600.795
    assert event_time("[Tue Mar 23 20:32:09.254196 2021] [php7:error] boom", 1970) == FIRST + 1929.0
    assert event_time("no timestamp here", 1970) is None


def test_a_run_whose_notables_name_no_labelled_source_says_so(
    tmp_path: Path,
) -> None:
    source = "/apache2/access.log.4"
    family = _family(
        tmp_path,
        notables=[_notable("peer_rare", "/elsewhere/access.log", ["10.0.0.5"], content_key="x")],
        keys=_keys(source, "web", {1: ["dirb"]}),
        files={("web", source): [_line("10.0.0.5", "/x")]},
    )
    assert family["notables"]["on_labelled_sources"] == 0
    assert family["recall"]["overall"]["None"] == 0
    assert "WARNING no notable names a source the keys label" in board.render(family)


def test_a_run_root_scores_every_family_with_its_own_keys(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "run"
    specs = []
    for family, source in (("fam", "/apache2/access.log.4"), ("other", "/openvpn.log")):
        run = _run(
            tmp_path / family,
            notables=[_notable("alerts", source, ["10.0.0.5"], p_yes=0.9, content_key="a")],
            keys=_keys(source, "web", {1: ["dirb"]}),
            files={("web", source): [_line("10.0.0.5", "/x")]},
        )
        (run / "sources.json").write_text(
            json.dumps({"index": f"idx_{family}", "cards": [{"facts": {"sources": [source]}}]}),
            encoding="utf-8",
        )
        (run / "progress.json").write_text(
            json.dumps(
                {
                    "stages": {
                        "cards": {"seconds": 1.0, "model_requests": 1},
                        "notables": {
                            "seconds": {"total": 1.0},
                            "similar_to_known": {"excluded_family": family},
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        root.mkdir(exist_ok=True)
        run.rename(root / family)
        specs.append(f"{family}={root / family / 'keys.jsonl'}")
    args = ["--out", str(root), "--json"]
    for spec in specs:
        args += ["--keys", spec]
    code = main(args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [family["family"] for family in payload["families"]] == ["fam", "other"]
    assert all(
        family["honesty"]["excluded_family"] == family["family"] for family in payload["families"]
    )


def test_on_source_folds_the_case_of_splunk_source_matches(tmp_path: Path) -> None:
    # botsv2 notable #33 vs the keyed osquery events: the query names osqueryd.WARNING,
    # the index stores osqueryd.warning; Splunk source matching is case-insensitive.
    source = "/var/log/osquery/osqueryd.warning"
    keys = _keys(source, "mac", {1: ["macbook_file_encryption"]})
    query = (
        'search index="botsv2" (source="/var/log/osquery/osqueryd.WARNING" '
        'OR source="/var/log/osquery/osqueryd.WARNING.20170811-070436.221") '
        '"exceeds size limit" | head 5'
    )
    notable = {
        "notable_id": "misfit-crypt",
        "generator": "misfit",
        "source_id": "botsv2:osquery_warning",
        "content_key": "misfit-crypt",
        "entities": [],
        "evidence": [
            {
                "line": (
                    "W0811 14:50:40.060264 61181952 filesystem.cpp:114] Cannot read file "
                    "that exceeds size limit: Downloads/GoT.S07E02.mkv.crypt"
                ),
                "query": query,
                "earliest": FIRST,
                "latest": FIRST + 3600.0,
            }
        ],
    }
    family = _family(
        tmp_path,
        notables=[notable],
        keys=keys,
        files={("mac", source): ["W0811 14:50:40.060264 exceeds size limit: x.crypt"]},
    )
    assert family["steps"][0]["first_rank"] == 0
    assert family["recall"]["overall"]["None"] == 1


def test_honesty_accepts_an_index_unseen_by_the_store() -> None:
    # botsv2, 2026-11-18: the store holds no botsv2 rows, so nothing is excluded and the loader's
    # leak guard is the protection; the scoreboard must score it rather than refuse.
    progress = {
        "stages": {
            "notables": {
                "similar_to_known": {
                    "excluded_family": "",
                    "index_unseen": True,
                    "loaded_families": ["kyoushi", "russell", "santos"],
                }
            }
        }
    }
    assert board._honesty(progress, "botsv2")["knowledge"] == "loaded"
    leaked = {
        "stages": {
            "notables": {
                "similar_to_known": {
                    "excluded_family": "",
                    "index_unseen": True,
                    "loaded_families": ["botsv2", "santos"],
                }
            }
        }
    }
    with pytest.raises(board.ScoreboardError):
        board._honesty(leaked, "botsv2")


def test_honesty_scores_a_tuned_v2_index_under_its_corpus_family() -> None:
    # 2026-11-21: a santos `_v2` run scored from a `santos_v2` run dir. The store rightly excluded
    # santos, so the label alone must not read as the run learning from its own family.
    for label, index, excluded in (
        ("santos_v2", "hb_ait_santos_v2", "santos"),
        ("kyoushi_s1_v2", "hb_kyoushi_s1_v2", "kyoushi"),
        ("russellmitchell_v2", "hb_ait_russellmitchell_v2", "russell"),
    ):
        progress = {
            "stages": {
                "notables": {
                    "similar_to_known": {
                        "excluded_family": excluded,
                        "excluded_families": [excluded],
                        "index_unseen": True,
                        "loaded_families": ["kyoushi", "russell"],
                        "run_index": index,
                    }
                }
            }
        }
        assert board._honesty(progress, label)["excluded_family"] == excluded
        assert board._honesty(progress, excluded)["knowledge"] == "loaded"
        with pytest.raises(board.ScoreboardError):
            board._honesty(progress, "botsv2")


def test_line_ceiling_counts_only_labelled_lines_the_run_actually_read(tmp_path: Path) -> None:
    source = "/apache2/access.log.4"
    read = _line("10.0.0.5", "/scan")
    unread = _line("10.0.0.6", "/probe")
    run = _run(
        tmp_path,
        notables=[_notable("alerts", source, ["10.0.0.5"])],
        keys=_keys(source, "web", {1: ["dirb"], 2: ["nikto"]}),
        files={("web", source): [read, unread]},
    )
    con = duckdb.connect(str(run / "behaviours.duckdb"))
    con.execute("CREATE TABLE events (raw VARCHAR)")
    con.execute("INSERT INTO events VALUES (?)", [read])
    con.close()
    family = score(run, [str(run / "keys.jsonl")], logs=tmp_path / "corpus" / "fam" / "gather")[
        "families"
    ][0]
    ceiling = family["ceiling"]
    assert ceiling["lines_read"] == 1
    assert ceiling["labelled_lines"] == 2
    assert ceiling["reachable"] == 1
    assert ceiling["covered"]["50"] == 1
    assert ceiling["recall"]["50"] == 1.0
    per_step = {row["step"]: row for row in ceiling["per_step"]}
    assert per_step["dirb"]["reachable"] is True
    assert per_step["nikto"]["reachable"] is False


def test_a_step_whose_file_the_index_lacks_is_evidence_absent_not_unreachable(
    tmp_path: Path,
) -> None:
    present = "/apache2/access.log.4"
    dropped = "/logstash/intranet-server/2022-01-17-system.cpu.log"
    read = _line("10.0.0.5", "/scan")
    gone = [_line("10.0.0.7", "/guess"), _line("10.0.0.7", "/guess2")]
    run = _run(
        tmp_path,
        notables=[_notable("alerts", present, ["10.0.0.5"])],
        keys=_keys(present, "web", {1: ["dirb"]})
        + _keys(dropped, "mon", {1: ["crack"], 2: ["crack"]}),
        files={("web", present): [read], ("mon", dropped): gone},
        indexed=[present],
    )
    con = duckdb.connect(str(run / "behaviours.duckdb"))
    con.execute("CREATE TABLE events (raw VARCHAR)")
    con.execute("INSERT INTO events VALUES (?)", [read])
    con.close()
    base = tmp_path / "base"
    base.mkdir()
    (base / "notables.jsonl").write_text(
        json.dumps(_notable("alerts", dropped, ["10.0.0.7"])) + "\n", encoding="utf-8"
    )
    (base / "progress.json").write_text(json.dumps({"stages": {"cards": {"start": FIRST}}}))
    (base / "sources.json").write_text(json.dumps({"index": "idx", "cards": []}))
    family = score(
        run,
        [str(run / "keys.jsonl")],
        logs=tmp_path / "corpus" / "fam" / "gather",
        baseline=base,
    )["families"][0]
    ceiling = family["ceiling"]
    assert ceiling["keys_present"] == {"lines": 1, "of": 3}
    assert ceiling["evidence_absent"] == [{"step": "crack", "absent": 2, "lines": 2}]
    assert ceiling["steps"] == 1 and ceiling["steps_all"] == 2
    assert ceiling["recall"]["50"] == 1.0
    assert family["baseline"]["diff"] == {
        "lost": ["crack"],
        "gained": ["dirb"],
        "reachable_lost": [],
        "reachable_gained": ["dirb"],
    }
    printed = board.render(family)
    assert "C0 ceiling  steps 1/1 reachable" in printed
    assert "C0 evidence absent (excluded from the step denominator)  crack 2/2" in printed
    assert "  reachable   lost -  gained dirb" in printed


def test_a_line_family_names_a_cause_for_every_step(tmp_path: Path) -> None:
    source = "/apache2/access.log.4"
    cut = "/auth.log"
    absent = "/logstash/intranet-server/2022-01-17-system.cpu.log"
    read = _line("10.0.0.5", "/scan")
    uncovered = _line("10.0.0.7", "/probe")
    unread = _line("10.0.0.6", "/wp-login")
    run = _run(
        tmp_path,
        notables=[
            _notable("alerts", source, ["10.0.0.5"], content_key="read"),
            _notable("deviation", source, ["10.0.0.6"], content_key="unread"),
        ],
        keys=_keys(source, "web", {1: ["dirb"], 2: ["wpscan"], 3: ["nikto"]})
        + _keys(cut, "auth", {1: ["crack"]})
        + _keys(absent, "mon", {1: ["gone"], 2: ["gone"]}),
        files={
            ("web", source): [read, unread, uncovered],
            ("auth", cut): ["Mar 23 20:01:00 sshd[1] Failed password"],
            ("mon", absent): ["cpu 1 2 3", "cpu 4 5 6"],
        },
        indexed=[source, cut],
    )
    con = duckdb.connect(str(run / "behaviours.duckdb"))
    con.execute("CREATE TABLE events (raw VARCHAR)")
    con.executemany("INSERT INTO events VALUES (?)", [[read], [uncovered]])
    con.close()
    cut_read = {
        "stage": "behaviours",
        "source_id": "idx:auth.log",
        "part": None,
        "query": f'search index="idx" (source="{cut}") | head 5',
        "rows": 5,
        "capped": True,
        "reason": "row_cap",
        "values_extracted": [],
        "window_start": 0.0,
        "window_end": 0.0,
    }
    with (run / "ledger.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(cut_read) + "\n")
    family = score(run, [str(run / "keys.jsonl")], logs=tmp_path / "corpus" / "fam" / "gather")[
        "families"
    ][0]
    causes = {row["step"]: row["cause"] for row in family["ceiling"]["per_step"]}
    assert causes == {
        "dirb": "covered",
        "wpscan": "instrument",
        "nikto": "not_surfaced",
        "crack": "censored",
        "gone": "unreached",
    }
    printed = board.render(family)
    assert "C0 causes  censored 1, covered 1, instrument 1, not_surfaced 1, unreached 1" in printed
    assert "unreached: gone (2/2 absent)" in printed
