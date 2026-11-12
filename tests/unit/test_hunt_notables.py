from __future__ import annotations

import json

from portal.modules.security.core.hunt.notables.cards import (
    CardCache,
    SourceCard,
    apply_answer,
    build_card,
    build_prompt,
)
from portal.modules.security.core.hunt.notables.parse import (
    field_stats,
    parse_events,
    parse_json,
    parse_kv,
    parse_row,
    parse_xml,
)
from portal.modules.security.core.hunt.notables.run import card_from_dict
from portal.modules.security.core.hunt.notables.sample import SourceFacts


def _facts() -> SourceFacts:
    return SourceFacts(
        index="ix",
        sourcetype="st",
        events=100,
        first=1000.0,
        last=1500.0,
        hosts=("h1",),
        host_count=1,
        sources=("s1",),
        source_count=1,
    )


def _rows() -> list[dict[str, object]]:
    lines = [
        json.dumps({"user": f"u{index % 3}", "image": "cmd.exe", "line": f"echo {index}"})
        for index in range(12)
    ]
    return [
        {"_raw": line, "_time": 1000.0 + index, "host": "h1"} for index, line in enumerate(lines)
    ]


class _Client:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    def complete(self, **request: object) -> dict[str, object]:
        self.calls.append(request)
        return {
            "model": "seat",
            "usage": {"prompt_tokens": 42},
            "choices": [{"message": {"content": self.content}}],
        }


def test_json_fields_keep_their_paths_and_flatten_scalars():
    fields = parse_json('{"a": {"b": 1}, "c": ["x", "y"], "d": [{"e": 2}]}')
    assert fields["a.b"] == "1"
    assert fields["c"] == "x,y"
    assert fields["d[0].e"] == "2"


def test_xml_fields_are_named_by_tag_and_distinguishing_attribute():
    fields = parse_xml(
        '<Event><Data Name="Image">cmd.exe</Data><Data Name="User">bob</Data><ID>5</ID></Event>'
    )
    assert fields["Data[Name=Image]"] == "cmd.exe"
    assert fields["Data[Name=User]"] == "bob"
    assert fields["ID"] == "5"


def test_key_value_needs_two_pairs_and_delimited_uses_its_header():
    assert parse_kv("user=bob action=login") == {"user": "bob", "action": "login"}
    assert parse_kv("just one=thing") == {}
    parsed = parse_events(["time,user,action", "1,bob,login", "2,amy,run"])
    assert [item.fmt for item in parsed] == ["delimited", "delimited"]
    assert parsed[0].fields == {"time": "1", "user": "bob", "action": "login"}


def test_free_text_stays_text_and_field_stats_count_repeats():
    parsed = parse_events(["nothing here parses as any structure at all"] * 4)
    assert {item.fmt for item in parsed} == {"text"}
    assert not field_stats(parsed)
    stats = field_stats(parse_events([json.dumps({"a": index % 2}) for index in range(6)]))
    assert stats[0].present == 6
    assert stats[0].distinct == 2
    assert stats[0].repeats is True


def test_delimited_row_reads_with_the_columns_the_sample_established():
    parsed = parse_row("3,carl,stop", "delimited", ("time", "user", "action"))
    assert parsed.fields == {"time": "3", "user": "carl", "action": "stop"}
    assert parse_row("3,carl,stop", "delimited", ()) == parse_row("3,carl,stop", "text", ())


def test_model_answer_is_rejected_when_it_names_a_field_the_sample_lacks():
    answer = apply_answer(
        json.dumps({"kind": "activity", "actor": ["user", "invented"], "action": ["image"]}),
        ["user", "image"],
    )
    assert answer.error is None
    assert answer.roles == {"actor": ("user",), "action": ("image",)}
    assert answer.rejected == ("invented",)
    assert apply_answer("no json at all", ["user"]).error == "unparseable_answer"
    assert apply_answer('{"kind": "nonsense"}', ["user"]).error == "invalid_kind"


def test_card_asks_once_validates_and_caches_its_answer(tmp_path):
    answer = json.dumps(
        {"kind": "activity", "actor": ["user"], "action": ["image"], "object": [], "basis": "did"}
    )
    client = _Client(answer)
    facts = _facts()
    rows = _rows()
    cache = CardCache(tmp_path)
    first = build_card(facts, rows, windows=3, client=client, model="seat", cache=cache)
    assert first.understood is True
    assert first.kind == "activity"
    assert first.roles["actor"] == ("user",)
    assert first.model["requests"] == 1
    assert len(client.calls) == 1
    assert "user" in build_prompt(first.fields, len(rows))
    second = build_card(facts, rows, windows=3, client=client, model="seat", cache=cache)
    assert second.model["requests"] == 0
    assert second.model["cached"] is True
    assert len(client.calls) == 1


def test_card_says_why_it_is_not_understood(tmp_path):
    client = _Client("not json")
    card = build_card(
        _facts(), _rows(), windows=1, client=client, model="seat", cache=CardCache(tmp_path)
    )
    assert card.understood is False
    assert card.reason == "unparseable_answer"
    blank = build_card(
        _facts(), [], windows=1, client=client, model="seat", cache=CardCache(tmp_path)
    )
    assert blank.reason == "no_sample"
    unparsed = build_card(
        _facts(),
        [{"_raw": "prose without any fields", "_time": 1.0}],
        windows=1,
        client=client,
        model="seat",
        cache=CardCache(tmp_path),
    )
    assert unparsed.reason == "unparsed_sample"
    assert len(client.calls) == 1


def test_card_reload_keeps_everything_a_later_stage_needs(tmp_path):
    answer = json.dumps({"kind": "activity", "actor": ["user"], "action": ["image"]})
    card = build_card(
        _facts(),
        _rows(),
        windows=2,
        client=_Client(answer),
        model="seat",
        cache=CardCache(tmp_path),
    )
    loaded = card_from_dict(card.as_dict())
    assert isinstance(loaded, SourceCard)
    assert loaded.source_id == "ix:st"
    assert loaded.roles == card.roles
    assert loaded.fmt == card.fmt
    assert [stat.name for stat in loaded.fields] == [stat.name for stat in card.fields]
    assert loaded.facts["events"] == 100
