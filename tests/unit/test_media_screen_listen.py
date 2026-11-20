"""Media screen listen step: pairing, blind order, answer parsing and unblinding (no network)."""

import importlib
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

listen = importlib.import_module("scripts.proofs.media_screen_listen")

CATALOG = listen.load_catalog()


def _receipt(row, role, index, output, rank=None):
    return {
        "medium": "music",
        "row": row,
        "role": role,
        "rank": rank,
        "prompt_index": index,
        "prompt": f"caption {index}",
        "outputs": [str(output)] if output else [],
    }


def _write_run(tmp_path, rows):
    run = tmp_path / "music-run"
    run.mkdir()
    (run / "rows.jsonl").write_text(
        "\n".join([json.dumps({"kind": "run", "medium": "music"})] + [json.dumps(r) for r in rows])
        + "\n"
    )
    return run


def test_draw_order_is_deterministic_and_depends_on_the_pair():
    for key in ("a-p1", "b-p1", "a-p2"):
        assert listen.draw_order(20261120, key) == listen.draw_order(20261120, key)
    orders = {listen.draw_order(20261120, f"row-{i}-p1") for i in range(40)}
    assert orders == {"AB", "BA"}


def test_pair_runs_pairs_each_candidate_with_the_incumbent_of_its_prompt(tmp_path):
    run = _write_run(
        tmp_path,
        [
            _receipt("inc", "incumbent", 1, tmp_path / "i1.wav"),
            _receipt("inc", "incumbent", 2, tmp_path / "i2.wav"),
            _receipt("cand", "candidate", 1, tmp_path / "c1.wav", rank=1),
            _receipt("cand", "candidate", 2, tmp_path / "c2.wav", rank=1),
            _receipt("lost", "candidate", 3, tmp_path / "c3.wav", rank=2),
        ],
    )
    pairs = listen.pair_runs(listen.load_receipts(run))
    assert [(p.candidate["row"], p.prompt_index, p.incumbent["row"]) for p in pairs] == [
        ("cand", 1, "inc"),
        ("cand", 2, "inc"),
    ]


def test_load_receipts_skips_the_run_header_and_rows_without_outputs(tmp_path):
    run = _write_run(tmp_path, [_receipt("inc", "incumbent", 1, tmp_path / "i1.wav")])
    with (run / "rows.jsonl").open("a") as stream:
        stream.write(json.dumps(_receipt("dead", "candidate", 1, None)) + "\n")
    rows = listen.load_receipts(run)
    assert [r["row"] for r in rows] == ["inc"]


def test_judge_question_carries_the_lyrics_and_the_instrumental_constraint():
    question = listen.judge_question(CATALOG, 2)
    assert "Hold the line" in question and "adherence" in question
    solo = listen.judge_question(CATALOG, 3)
    assert "no vocals" in solo and "solo nylon" in solo


def test_build_request_attaches_both_clips(tmp_path):
    a = tmp_path / "a.wav"
    a.write_bytes(b"RIFX-a")
    b = tmp_path / "b.wav"
    b.write_bytes(b"RIFX-b")
    request = listen.build_request("mimo", "question", a, b)
    parts = request["messages"][0]["content"]
    audio = [p["input_audio"] for p in parts if p["type"] == "input_audio"]
    assert len(audio) == 2 and audio[0]["format"] == "wav"
    assert audio[0]["data"] != audio[1]["data"]


@pytest.mark.parametrize(
    "content",
    [
        '```json\n{"A": {"adherence": 4, "musicality": 4, "instruments": 4, "cleanliness": 5, '
        '"vocals": 4}, "B": {"adherence": 2, "musicality": 3, "instruments": 3, "cleanliness": 5, '
        '"vocals": 3}, "winner": "A"}\n```',
        'Here is my answer:\n{"A": {"adherence": 4, "musicality": 4, "instruments": 4, '
        '"cleanliness": 5, "vocals": 4}, "B": {"adherence": 2, "musicality": 3, "instruments": 3, '
        '"cleanliness": 5, "vocals": 3}, "winner": "A"}',
    ],
)
def test_parse_answer_accepts_json_behind_fences_or_prose(content):
    assert listen.parse_answer(content)["winner"] == "A"


@pytest.mark.parametrize(
    "content",
    [
        "",
        "CANNOT_PERCEIVE",
        "no json here",
        '{"A": {"adherence": 0}, "B": {}}',
        '{"A": {"adherence": 4, "musicality": 4, "instruments": 4, "cleanliness": 5, "vocals": 4}}',
    ],
)
def test_parse_answer_rejects_anything_that_is_not_a_full_score(content):
    assert listen.parse_answer(content) is None


def _mock_listener(tmp_path, answer, *, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, json={"error": "boom"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": answer}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens_details": {"audio_tokens": 376}},
            },
        )

    return listen.Listener("https://api.example/v1", "k", transport=httpx.MockTransport(handler))


def _answer(a_winner="A"):
    return json.dumps(
        {
            "A": {
                "adherence": 4,
                "musicality": 4,
                "instruments": 4,
                "cleanliness": 5,
                "vocals": 4,
                "lyrics": "hold the line",
                "elements": ["guitar"],
                "notes": "fine",
            },
            "B": {
                "adherence": 2,
                "musicality": 3,
                "instruments": 3,
                "cleanliness": 5,
                "vocals": 3,
                "lyrics": "chorus only",
                "elements": ["synth"],
                "notes": "missing verse",
            },
            "winner": a_winner,
            "why": "B drops the verse",
        }
    )


def test_score_pair_unblinds_the_drawn_order(tmp_path):
    a = tmp_path / "c.wav"
    a.write_bytes(b"c")
    b = tmp_path / "i.wav"
    b.write_bytes(b"i")
    pair = listen.Pair(
        _receipt("cand", "candidate", 1, a, rank=1), _receipt("inc", "incumbent", 1, b)
    )
    listener = _mock_listener(tmp_path, _answer("A"))
    receipt = listen.score_pair(listener, "mimo", CATALOG, pair, seed=20261120)
    assert receipt["status"] == "ok" and receipt["audio_tokens"] == 376
    slot = receipt["candidate_slot"]
    assert receipt["candidate_scores"]["adherence"] == 4
    assert receipt["incumbent_scores"]["adherence"] == 2
    assert receipt["winner"] == ("candidate" if slot == "A" else "incumbent")


def test_score_pair_records_an_http_failure_without_raising(tmp_path):
    a = tmp_path / "c.wav"
    b = tmp_path / "i.wav"
    a.write_bytes(b"c")
    b.write_bytes(b"i")
    pair = listen.Pair(
        _receipt("cand", "candidate", 1, a, rank=1), _receipt("inc", "incumbent", 1, b)
    )
    receipt = listen.score_pair(
        _mock_listener(tmp_path, "", status=500), "mimo", CATALOG, pair, seed=1
    )
    assert receipt["status"] == "unparsed" and "HTTPStatusError" in receipt["error"]


def test_listen_run_writes_the_sheet_and_one_receipt_per_pair(tmp_path):
    run = _write_run(
        tmp_path,
        [
            _receipt("inc", "incumbent", 1, tmp_path / "i1.wav"),
            _receipt("cand", "candidate", 1, tmp_path / "c1.wav", rank=1),
        ],
    )
    (tmp_path / "c1.wav").write_bytes(b"c")
    (tmp_path / "i1.wav").write_bytes(b"i")
    listener = _mock_listener(tmp_path, _answer("B"))
    sheet, receipts = listen.listen_run(
        run, listener="mimo", api_key="k", transport=listener.transport, seed=7
    )
    text = sheet.read_text()
    assert "| cand p1 |" in text and "order: candidate in slot" in text
    rows = [json.loads(line) for line in receipts.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["listener"] == "mimo" and rows[0]["status"] == "ok"


def test_listen_run_without_a_candidate_pair_writes_nothing(tmp_path):
    run = _write_run(tmp_path, [_receipt("inc", "incumbent", 1, tmp_path / "i1.wav")])
    (tmp_path / "i1.wav").write_bytes(b"i")
    assert listen.listen_run(run, api_key="k") == (None, None)


def test_resolve_api_key_prefers_the_environment(tmp_path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"xiaomi": {"key": "stored"}}))
    monkeypatch.setenv("SCREEN_KEY", "env-key")
    assert listen.resolve_api_key("SCREEN_KEY", "https://api.xiaomimimo.com/v1", auth) == "env-key"
    monkeypatch.delenv("SCREEN_KEY")
    assert listen.resolve_api_key("SCREEN_KEY", "https://api.xiaomimimo.com/v1", auth) == "stored"
    with pytest.raises(ValueError):
        listen.resolve_api_key("SCREEN_KEY", "https://api.openrouter.ai/v1", auth)
