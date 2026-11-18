from __future__ import annotations

import json

from portal.modules.security.core.hunt.notables.cards import (
    CardCache,
    SourceCard,
    answer_cards,
    apply_answer,
    ask_model,
    assemble_cards,
    build_card,
    build_cards,
    build_prompt,
    cadence_facts,
    is_alert_event,
    is_alert_line,
    prepare_cards,
    reconcile_kind,
    value_facts,
)
from portal.modules.security.core.hunt.notables.parse import (
    choose_partition,
    field_stats,
    parse_events,
    parse_json,
    parse_kv,
    parse_row,
    parse_sample,
    parse_xml,
    partition_groups,
    words,
)
from portal.modules.security.core.hunt.notables.run import _sample_source, card_from_dict
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


def test_a_multi_line_xml_event_is_read_whole():
    raw = """<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
  <EventData>
    <Data Name="Image">C:\\Windows\\System32\\cmd.exe</Data>
    <Data Name="User">bob</Data>
  </EventData>
</Event>"""
    parsed = parse_events([raw])
    assert parsed[0].fmt == "xml"
    assert parsed[0].fields["Data[Name=Image]"].endswith("cmd.exe")
    assert parsed[0].fields["Data[Name=User]"] == "bob"


def _mixed_rows() -> list[dict[str, object]]:
    rows = []
    for index in range(8):
        if index % 2 == 0:
            raw = json.dumps({"kind": "alert", "sig": f"s{index}", "src": "a"})
        else:
            raw = json.dumps({"kind": "flow", "src": "a", "dst": "b", "bytes": index})
        rows.append({"_raw": raw, "_time": 1000.0 + index, "host": "h1"})
    return rows


def test_kind_facts_measure_numeric_and_recurring_values():
    rows = [
        json.dumps({"n": str(index % 2), "who": "bob" if index % 2 else "amy"})
        for index in range(4)
    ]
    parsed = parse_events(rows)
    stats = field_stats(parsed)
    facts = value_facts(parsed, stats)
    assert facts == {"numeric_share": 0.5, "identity_share": 1.0}
    assert cadence_facts(
        SourceFacts(
            "ix",
            "st",
            10,
            0.0,
            1.0,
            (),
            0,
            (),
            0,
            active_periods=10,
            periods=20,
            count_cv=0.3,
        )
    ) == {"active_periods": 10, "periods": 20, "active_share": 0.5, "count_cv": 0.3}


def test_facts_overrule_a_non_numeric_measurement_and_record_other_conflicts():
    assert reconcile_kind("measurement", {"numeric_share": 0.1}) == (
        "activity",
        "facts_override:measurement_numeric_share=0.10",
    )
    assert reconcile_kind("measurement", {"numeric_share": 0.9}) == ("measurement", None)
    assert reconcile_kind("activity", {"numeric_share": 0.9}) == (
        "activity",
        "kind_conflict:activity_numeric_share=0.90",
    )
    assert reconcile_kind("alert", {"numeric_share": 0.9}) == ("alert", None)


def test_a_process_creation_source_classed_measurement_stays_in_behaviours(tmp_path):
    answer = json.dumps({"kind": "measurement", "actor": ["user"], "action": ["image"]})
    card = build_card(
        _facts(),
        _rows(),
        windows=1,
        client=_Client(answer),
        model="seat",
        cache=CardCache(tmp_path),
    )
    assert card.kind == "activity"
    assert card.kind_said == "measurement"
    assert str(card.kind_note).startswith("facts_override:")
    assert card.usable is True


def test_identical_structures_share_one_request_and_report_reuse(tmp_path):
    answer = json.dumps({"kind": "activity", "actor": ["user"], "action": ["image"]})
    client = _Client(answer)
    other = SourceFacts("ix2", "st2", 999, 5.0, 6.0, ("h9",), 1, ("s9",), 1)
    prepared = [
        *prepare_cards(_facts(), _rows(), 1, "seat"),
        *prepare_cards(other, _rows(), 1, "seat"),
    ]
    answers, stats = answer_cards(prepared, client, "seat", CardCache(tmp_path))
    cards = assemble_cards(prepared, answers)
    assert stats["structures"] == 1
    assert stats["requests"] == 1
    assert stats["disk_hits"] == 0
    assert len(client.calls) == 1
    assert [card.model["requests"] for card in cards] == [1, 0]
    assert all(card.kind == "activity" for card in cards)
    _answers, again = answer_cards(prepared[:1], client, "seat", CardCache(tmp_path))
    assert again["requests"] == 0
    assert again["disk_hits"] == 1
    assert len(client.calls) == 1


def test_identical_structure_gets_the_same_card_key_and_kind(tmp_path):
    answer = json.dumps({"kind": "activity", "actor": ["user"], "action": ["image"]})
    client = _Client(answer)
    first = build_card(
        _facts(), _rows(), windows=1, client=client, model="seat", cache=CardCache(tmp_path)
    )
    other = SourceFacts("ix2", "st2", 999, 5.0, 6.0, ("h9",), 1, ("s9",), 1)
    second = build_card(
        other, _rows(), windows=1, client=client, model="seat", cache=CardCache(tmp_path)
    )
    assert first.cache_key == second.cache_key
    assert first.kind == second.kind
    assert len(client.calls) == 1


def test_a_low_variety_field_that_selects_the_field_set_splits_the_source():
    parsed = parse_events([str(row["_raw"]) for row in _mixed_rows()])
    partition = choose_partition(parsed)
    assert partition is not None
    assert partition.field == "kind"
    assert partition.values == ("alert", "flow")
    groups = partition_groups(parsed, _mixed_rows(), partition)
    assert [len(groups[value][0]) for value in partition.values] == [4, 4]


def test_build_cards_gives_each_structure_its_own_card(tmp_path):
    class _MixedClient:
        def complete(self, **request: object) -> dict[str, object]:
            messages = request.get("messages", [])
            prompt = "\n".join(
                str(message.get("content") or "")
                for message in messages
                if isinstance(message, dict)
            )
            answer = (
                {"kind": "alert", "actor": ["src"], "action": ["sig"]}
                if "- sig present=" in prompt
                else {"kind": "activity", "actor": ["src"], "action": ["bytes"]}
            )
            return {"choices": [{"message": {"content": json.dumps(answer)}}]}

    cards = build_cards(
        _facts(),
        _mixed_rows(),
        windows=1,
        client=_MixedClient(),  # type: ignore[arg-type]
        model="seat",
        cache=CardCache(tmp_path),
    )
    assert len(cards) == 2
    assert {card.part_value for card in cards} == {"alert", "flow"}
    assert {card.source_id for card in cards} == {"ix:st"}
    assert len({card.card_id for card in cards}) == 2
    assert all(card.understood for card in cards)
    assert [len(card.fields) for card in cards] == [3, 4]
    assert {card.part_value: card.kind for card in cards} == {"alert": "alert", "flow": "activity"}


def test_is_alert_event_reads_the_event_type_property() -> None:
    assert is_alert_event({"_raw": json.dumps({"event_type": "alert", "src_ip": "a"})}) is True
    assert is_alert_event({"_raw": json.dumps({"event_type": "flow", "src_ip": "a"})}) is False
    assert is_alert_event({"_raw": "Mar 24 10:00:00 sshd: not json"}) is False


def test_sample_source_adds_probe_alerts_missed_by_the_general_sample() -> None:
    from portal.modules.security.core.hunt.executor import Read

    class _ProbeExecutor:
        def __init__(self, sample: list[dict[str, object]], probe: list[dict[str, object]]):
            self.sample = sample
            self.probe = probe
            self.kinds: list[str] = []

        def read(
            self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
        ) -> Read:
            del query, start, end, row_cap
            self.kinds.append(kind)
            rows = self.probe if kind == "alert_probe" else self.sample
            return Read([dict(row) for row in rows], False, None)

    flow = {
        "_raw": json.dumps({"event_type": "flow", "src_ip": "a", "dest_ip": "b"}),
        "_time": 1000.0,
        "host": "h1",
    }
    alert = {
        "_raw": json.dumps(
            {"event_type": "alert", "alert": {"signature": "ET scan"}, "src_ip": "a"}
        ),
        "_time": 1001.0,
        "host": "h1",
    }

    executor = _ProbeExecutor([flow], [alert])
    _facts_value, read = _sample_source(executor, _facts())  # type: ignore[arg-type]
    assert "alert_probe" in executor.kinds
    assert any(is_alert_event(row) for row in read.rows)
    assert any(row["_raw"] == flow["_raw"] for row in read.rows)

    sampled_alerts = _ProbeExecutor([alert] * 6, [])
    _facts_value, read = _sample_source(sampled_alerts, _facts())  # type: ignore[arg-type]
    assert "alert_probe" not in sampled_alerts.kinds


_SYSLOG = [
    "Mar 24 10:00:00 web01 sshd[123]: Accepted password for bob from 10.0.0.5 port 22 ssh2",
    "Mar 24 10:00:05 web02 sshd[124]: Accepted password for amy from 10.0.0.6 port 22 ssh2",
    "Mar 24 10:01:00 web01 sshd[125]: Accepted password for bob from 10.0.0.5 port 22 ssh2",
    "Mar 24 10:02:00 web02 sshd[126]: Failed password for root from 10.0.0.7 port 22 ssh2",
    "Mar 25 11:00:00 web01 sshd[127]: Accepted password for amy from 10.0.0.6 port 22 ssh2",
    "Mar 25 11:01:00 web02 sshd[128]: Accepted password for bob from 10.0.0.5 port 22 ssh2",
]


def test_a_line_oriented_log_is_mined_into_a_header_and_templates():
    parsed, model = parse_sample(_SYSLOG)
    assert model is not None
    assert (model.header_tokens, model.program_position) == (5, 4)
    assert {item.fmt for item in parsed} == {"template"}
    assert model.states["existed"] == 1
    assert model.states["kept"] == 1
    assert model.states["explained"] == 6
    assert parsed[0].fields["program"] == "sshd"
    assert parsed[0].fields["template"] == "* password for * from * port 22 ssh2"
    assert parsed[0].fields["v1"] == "Accepted"
    assert parsed[0].fields["v2"] == "bob"
    assert parsed[0].fields["v3"] == "10.0.0.5"
    assert parsed[3].fields["v1"] == "Failed"


def test_template_events_read_with_the_learned_model_after_the_sample():
    _parsed, model = parse_sample(_SYSLOG)
    assert model is not None
    row = parse_row(_SYSLOG[5], "template", template=model)
    assert row.fields["program"] == "sshd"
    assert row.fields["v2"] == "bob"
    assert parse_row(_SYSLOG[5], "template", template=None).fields == {}


def test_a_line_oriented_source_is_one_card_and_is_never_partitioned_on_time(tmp_path):
    rows = [
        {"_raw": line, "_time": 1000.0 + index, "host": "h1"} for index, line in enumerate(_SYSLOG)
    ]
    client = _Client("{}")
    cards = build_cards(
        _facts(), rows, windows=1, client=client, model="seat", cache=CardCache(tmp_path)
    )
    assert len(cards) == 1
    card = cards[0]
    assert card.fmt == "template"
    assert card.kind == "activity"
    assert card.roles["actor"] == ("program",)
    assert card.roles["action"] == ("template",)
    assert "v1" in card.roles["object"]
    assert card.template_model is not None
    assert len(client.calls) == 0


def test_a_suricata_fast_log_sample_is_flagged_as_an_alert_source(monkeypatch):
    from portal.modules.security.core.hunt.notables import cards as cards_module
    from portal.modules.security.core.hunt.notables.parse import Parsed, TemplateModel

    lines = [
        "01/24/2022-03:56:58.599059  [**] [1:2220006:1] SURICATA SMTP no server welcome "
        "message [**] [Classification: Generic Protocol Command Decode] [Priority: 3] {TCP} "
        "172.19.130.4:587 -> 192.168.230.122:49954",
        "01/24/2022-03:56:59.159788  [**] [1:2220000:1] SURICATA SMTP invalid reply [**] "
        "[Classification: Generic Protocol Command Decode] [Priority: 3] {TCP} "
        "172.19.130.4:587 -> 192.168.230.122:49954",
    ]
    rows = [
        {"_raw": line, "_time": 1000.0 + index, "host": "h1"} for index, line in enumerate(lines)
    ]
    parsed = [
        Parsed("template", {"program": "suricata", "template": "SURICATA SMTP", "v1": "x"})
        for _line in lines
    ]
    model = TemplateModel(0, 0, (), {})
    monkeypatch.setattr(cards_module, "parse_sample", lambda _raws: (parsed, model))

    prepared = prepare_cards(_facts(), rows, 1, "seat")

    assert prepared[0].alert is True
    card = assemble_cards(prepared, {})[0]
    assert card.kind == "alert"
    assert card.roles["action"] == ("template",)


def test_a_json_source_is_probed_by_its_alert_event_type():
    from portal.modules.security.core.hunt.executor import Read

    flow = {
        "_raw": json.dumps({"event_type": "flow", "src_ip": "a"}),
        "_time": 1000.0,
        "host": "h1",
    }
    alert = {
        "_raw": json.dumps({"event_type": "alert", "src_ip": "a"}),
        "_time": 1001.0,
        "host": "h1",
    }

    class _Executor:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def read(
            self, query: str, start: float, end: float, *, kind: str, row_cap: int | None = None
        ) -> Read:
            del start, end, kind, row_cap
            self.queries.append(query)
            rows = [alert] if 'event_type="alert"' in query else [flow]
            return Read([dict(row) for row in rows], False, None)

    executor = _Executor()
    _facts_value, read = _sample_source(executor, _facts())  # type: ignore[arg-type]

    assert any('event_type="alert"' in query for query in executor.queries)
    assert any(is_alert_event(row) for row in read.rows)


def test_is_alert_line_reads_a_suricata_fast_log_line() -> None:
    assert is_alert_line(
        "01/24/2022-03:56:58.599059  [**] [1:2220006:1] SURICATA SMTP no server welcome "
        "message [**] [Classification: Generic Protocol Command Decode] [Priority: 3] {TCP} "
        "172.19.130.4:587 -> 192.168.230.122:49954"
    )
    assert is_alert_line(json.dumps({"event_type": "alert", "src_ip": "a"}))
    assert is_alert_line("Mar 24 10:00:00 sshd: not json") is False
    assert is_alert_line(json.dumps({"event_type": "flow"})) is False


def test_a_time_ordered_discriminator_never_splits_a_source():
    rows = []
    for day in (1, 2, 3):
        for _index in range(4):
            fields = {"day": str(day), "a": "x"}
            for extra in "bcd"[:day]:
                fields[extra] = extra
            rows.append(json.dumps(fields))
    parsed = parse_events(rows)
    assert choose_partition(parsed) is None


def test_words_keep_a_bracketed_stamp_whole_and_split_a_quoted_phrase():
    line = '1.2.3.4 - - [01/Jan/2020:00:00:00 +0000] "GET /a b HTTP/1.1" 200 12'
    positions = words(line)
    assert positions[3] == "[01/Jan/2020:00:00:00 +0000]"
    assert positions[4:9] == ["GET", "/a", "b", "HTTP/1.1", "200"]


def test_a_web_access_line_separates_the_client_method_and_path():
    lines = [
        '1.2.3.4 - - [01/Jan/2020:00:00:00 +0000] "GET /a HTTP/1.1" 200 12',
        '1.2.3.5 - - [01/Jan/2020:00:00:01 +0000] "GET /b HTTP/1.1" 200 34',
        '1.2.3.6 - - [01/Jan/2020:00:00:02 +0000] "POST /c HTTP/1.1" 404 56',
        '1.2.3.4 - - [01/Jan/2020:00:00:03 +0000] "GET /a HTTP/1.1" 200 12',
    ]
    parsed, model = parse_sample(lines)
    assert model is not None
    assert model.header_tokens == 0
    assert parsed[0].fields["v1"] == "1.2.3.4"
    assert parsed[0].fields["v3"] == "GET"
    assert parsed[0].fields["v4"] == "/a"
    assert parsed[2].fields["v3"] == "POST"
    assert "HTTP/1.1" in parsed[0].fields["template"]


def test_an_apostrophe_does_not_swallow_the_rest_of_a_line():
    assert words("a b don't stop c d") == ["a", "b", "don't", "stop", "c", "d"]


def test_key_value_needs_two_pairs_and_delimited_uses_its_header():
    assert parse_kv("user=bob action=login") == {"user": "bob", "action": "login"}
    assert parse_kv("just one=thing") == {}
    parsed = parse_events(["time,user,action", "1,bob,login", "2,amy,run"])
    assert [item.fmt for item in parsed] == ["header", "delimited", "delimited"]
    assert parsed[1].fields == {"time": "1", "user": "bob", "action": "login"}


# Real botsv2 wineventlog:security shape: a KV header then a colon-labelled detail body.
_SECURITY_4720 = (
    "08/23/2017 09:18:55 PM\nLogName=Security\n"
    "SourceName=Microsoft Windows security auditing.\nEventCode=4720\nEventType=0\n"
    "Type=Information\nComputerName=mercury.frothly.local\nTaskCategory=User Account Management\n"
    "OpCode=Info\nRecordNumber=1700527\nKeywords=Audit Success\nMessage=A user account was created.\n"
    "\nSubject:\n\tSecurity ID:\t\tFROTHLY\\service3\n\tAccount Name:\t\tservice3\n"
    "\tAccount Domain:\t\tFROTHLY\n\tLogon ID:\t\t0x927DF4B\n"
    "\nNew Account:\n\tSecurity ID:\t\tFROTHLY\\svcvnc\n\tAccount Name:\t\tsvcvnc\n"
    "\nAttributes:\n\tSAM Account Name:\tsvcvnc\n\tDisplay Name:\t\t<value not set>\n"
)
_SECURITY_4688 = (
    "08/23/2017 09:16:40 PM\nLogName=Security\nEventCode=4688\n"
    "ComputerName=mercury.frothly.local\nTaskCategory=Process Creation\n"
    "Message=A new process has been created.\n\nSubject:\n\tAccount Name:\t\tservice3\n"
    "\nProcess Information:\n\tNew Process ID:\t\t0x16e4\n"
    "\tNew Process Name:\tC:\\Windows\\System32\\ftp.exe\n"
    '\tProcess Command Line:\t"C:\\Windows\\System32\\ftp.exe" -s:C:\\Users\\public\\ftpscript.txt\n'
)


def test_kv_reads_the_colon_labelled_body_of_a_rendered_security_event():
    fields = parse_kv(_SECURITY_4720)
    assert fields["EventCode"] == "4720"
    assert fields["SAM Account Name"] == "svcvnc"
    assert fields["ComputerName"] == "mercury.frothly.local"
    process = parse_kv(_SECURITY_4688)
    assert process["New Process Name"] == "C:\\Windows\\System32\\ftp.exe"
    assert process["Account Name"] == "service3"
    # a detail value may itself contain '=' (a command line); the label still keys it
    assert "ftpscript.txt" in process["Process Command Line"]


def test_kv_colon_body_does_not_change_auditd_or_dovecot_lines():
    from portal.modules.security.core.hunt.notables.parse import _KV

    audit = (
        "type=USER_ACCT msg=audit(1616458141.526:150): pid=1899 uid=0 auid=4294967295 "
        'ses=4294967295 msg=\'op=PAM:accounting acct="root" exe="/usr/sbin/cron" res=success\''
    )
    mail = (
        "Mar 23 08:06:26 mail dovecot: imap-login: Login: user=<konstantin.braun>, "
        "method=PLAIN, rip=172.16.100.30, lip=172.16.100.30, mpid=4044, TLS, session=<x>"
    )
    journal = (
        "2021-03-22T20:21:49+00:00 ubuntu kernel: Command line: "
        "BOOT_IMAGE=/boot/vmlinuz root=LABEL=cloudimg-rootfs ro console=tty1"
    )
    for line in (audit, mail, journal):
        kv_keys = {m.group(1) for m in _KV.finditer(line)}
        # the colon-label rule adds no field these single-line KV logs do not already carry
        assert set(parse_kv(line)) == kv_keys


def test_free_text_stays_text_and_field_stats_count_repeats():
    parsed = parse_events(["x"] * 4)
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


def test_quoted_delimited_records_keep_their_real_columns():
    lines = [
        '"time","user","action"',
        '"2020-01-01 00:00:00",bob,"login, ok"',
        "host,[01/Jan/2020:00:00:00,123],logout",
    ]
    parsed = parse_events(lines)
    assert {item.fmt for item in parsed} == {"header", "delimited"}
    assert parsed[1].fields == {
        "time": "2020-01-01 00:00:00",
        "user": "bob",
        "action": "login, ok",
    }
    assert parsed[2].fields == {
        "time": "host",
        "user": "[01/Jan/2020:00:00:00,123]",
        "action": "logout",
    }


def test_one_field_in_several_core_roles_is_rejected():
    answer = apply_answer(
        json.dumps({"kind": "activity", "actor": ["c1"], "action": ["c1"], "object": ["c1"]}),
        ["c1", "c2", "c3"],
    )
    assert answer.error == "ambiguous_roles:c1"
    assert answer.roles == {}


def test_a_card_with_one_field_in_every_core_role_is_not_understood(tmp_path):
    answer = json.dumps({"kind": "activity", "actor": ["user"], "action": ["user"], "object": []})
    card = build_card(
        _facts(),
        _rows(),
        windows=1,
        client=_Client(answer),
        model="seat",
        cache=CardCache(tmp_path),
    )
    assert card.understood is False
    assert card.reason == "ambiguous_roles:user"


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


def test_a_card_answer_naming_a_field_the_sample_lacks_is_rejected(tmp_path):
    answer = json.dumps({"kind": "activity", "actor": ["user", "invented"]})
    card = build_card(
        _facts(),
        _rows(),
        windows=1,
        client=_Client(answer),
        model="seat",
        cache=CardCache(tmp_path),
    )
    assert card.understood is False
    assert card.reason == "unknown_fields:invented"
    assert card.roles == {}


def test_card_says_why_it_is_not_understood(tmp_path):
    client = _Client("not json")
    card = build_card(
        _facts(), _rows(), windows=1, client=client, model="seat", cache=CardCache(tmp_path)
    )
    assert card.understood is False
    assert card.reason == "model_no_answer"
    blank = build_card(
        _facts(), [], windows=1, client=client, model="seat", cache=CardCache(tmp_path)
    )
    assert blank.reason == "no_sample"
    unparsed = build_card(
        _facts(),
        [{"_raw": "x", "_time": 1.0}],
        windows=1,
        client=client,
        model="seat",
        cache=CardCache(tmp_path),
    )
    assert unparsed.reason == "unparsed_sample:coverage=0.00"
    assert len(client.calls) == 1


def test_a_no_answer_response_records_tokens_and_finish_reason():
    class _Full:
        def complete(self, **request: object) -> dict[str, object]:
            del request
            return {
                "model": "seat",
                "usage": {"prompt_tokens": 5, "completion_tokens": 84},
                "choices": [{"finish_reason": "stop", "message": {"content": "retry"}}],
            }

    answer = ask_model(_Full(), "seat", "prompt")
    assert answer.error == "no_answer"
    assert answer.completion_tokens == 84
    assert answer.finish_reason == "stop"
    assert answer.prompt_tokens == 5


def test_no_answer_is_its_own_reason_and_the_raw_text_is_kept(tmp_path):
    placeholder = "The model did not produce an answer. Please retry."
    card = build_card(
        _facts(),
        _rows(),
        windows=1,
        client=_Client(placeholder),
        model="seat",
        cache=CardCache(tmp_path),
    )
    assert card.understood is False
    assert card.reason == "model_no_answer"
    assert card.model["raw_answer"] == placeholder
    assert card.model["answer_chars"] == len(placeholder)


def test_a_bad_answer_keeps_its_raw_text_and_is_not_confused_with_no_answer(tmp_path):
    bad = '{"kind": "activity",'
    card = build_card(
        _facts(), _rows(), windows=1, client=_Client(bad), model="seat", cache=CardCache(tmp_path)
    )
    assert card.reason == "unparseable_answer"
    assert card.model["raw_answer"] == bad


def test_a_template_card_reload_keeps_its_learned_templates(tmp_path):
    rows = [
        {"_raw": line, "_time": 1000.0 + index, "host": "h1"} for index, line in enumerate(_SYSLOG)
    ]
    cards = build_cards(
        _facts(), rows, windows=1, client=_Client("{}"), model="seat", cache=CardCache(tmp_path)
    )
    loaded = card_from_dict(cards[0].as_dict())
    assert loaded.template_model is not None
    assert cards[0].template_model is not None
    assert loaded.template_model.to_dict() == cards[0].template_model.to_dict()


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
