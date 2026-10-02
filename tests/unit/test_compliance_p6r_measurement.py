"""P6R regression controls: measure the served system and each Part's scope."""

from types import SimpleNamespace

import pytest

from portal.modules.compliance.core import requirement_scope
from portal.modules.compliance.core.repository import Repository
from portal.platform.inference.config import load_portal_config
from portal.platform.inference.sync_config import _owui_preset
from scripts.compliance.truth import substrate_vs_key
from scripts.compliance_acceptance import WorkspaceThread


def test_workspace_window_check_uses_measured_native_window(monkeypatch):
    from scripts.compliance.truth import citation_integrity
    from scripts.compliance_acceptance import check_workspace_cell

    monkeypatch.setattr(
        citation_integrity,
        "integrity",
        lambda *_args, **_kwargs: {"lines": []},
    )
    record = {
        "served_model": "mlx-community--gemma-4-26b-a4b-it-4bit",
        "prompt_tokens_high_water": 40000,
        "serving": {"serving_window": 262144},
    }
    rows = check_workspace_cell({}, record)
    window = next(r for r in rows if r["assertion"] == "applied_window_known_and_not_exceeded")
    assert window["ok"]
    record["serving"] = {}
    rows = check_workspace_cell({}, record)
    assert not next(r for r in rows if r["assertion"] == "applied_window_known_and_not_exceeded")[
        "ok"
    ]


def test_every_compliance_preset_system_is_the_harness_system():
    config = load_portal_config()
    found = 0
    for name, spec in config.workspaces.items():
        if "compliance" not in name or not spec.owui_system_prompt:
            continue
        thread = WorkspaceThread(None, name, "http://unused")
        assert thread.messages == [
            {"role": "system", "content": _owui_preset(name, spec)["params"]["system"]}
        ]
        import hashlib

        assert (
            thread.system_text_sha256
            == hashlib.sha256(
                (spec.owui_system_prompt + (spec.system_prompt_append or "")).encode()
            ).hexdigest()
        )
        found += 1
    assert found > 0


def test_part_rows_are_measured_under_parent_without_r20_leakage(tmp_path):
    repo = Repository(tmp_path / "scope.sqlite")
    try:
        scope = SimpleNamespace(
            resolve=lambda _repo, ref: requirement_scope.Scope(
                ref=ref,
                leaves=["CIP-007-6 R2 Part 2.1", "CIP-007-6 R2 Part 2.2"]
                if ref == "CIP-007-6 R2"
                else [],
            )
        )

        def coverage(**kwargs):
            assert kwargs == {"standard": "CIP-007-6", "requirement": "R2"}
            return {
                "requirements": [
                    {
                        "requirement": "CIP-007-6 R2 Part 2.1",
                        "linked_sections": [{"section_id": "synthetic-a"}],
                    },
                    {
                        "requirement": "CIP-007-6 R2 Part 2.2",
                        "linked_sections": [{"section_id": "synthetic-b"}],
                    },
                    {
                        "requirement": "CIP-007-6 R20",
                        "linked_sections": [{"section_id": "synthetic-wrong"}],
                    },
                ]
            }

        assert substrate_vs_key._coverage_surface(repo, scope, coverage, "CIP-007-6 R2") == {
            "synthetic-a",
            "synthetic-b",
        }
        assert substrate_vs_key._coverage_surface(
            repo, scope, coverage, "CIP-007-6 R2 Part 2.1"
        ) == {"synthetic-a"}
    finally:
        repo.close()


def test_verdict_checks_do_not_pool_another_parts_evidence():
    scope = SimpleNamespace(resolve=lambda repo, ref: requirement_scope.Scope(ref=ref))
    entry = {
        "question_id": "synthetic",
        "facts": [
            {
                "part": "CIP-007-6 R2 Part 2.1",
                "coverage": "covered",
                "evidence": ["isection-synthetic"],
            },
            {"part": "CIP-007-6 R2 Part 2.2", "coverage": "not_covered", "evidence": []},
        ],
    }
    checks = substrate_vs_key._verdict_checks(
        entry,
        {
            "CIP-007-6 R2 Part 2.1": set(),
            "CIP-007-6 R2 Part 2.2": {"isection-synthetic"},
        },
        None,
        scope,
    )
    assert [c["agrees"] for c in checks] == [False, False]


def test_window_pressure_uses_serving_window_and_retains_unknowns():
    from scripts.compliance.truth.served_turn import window_fields

    assert window_fields(32768, 262144)["window_pressure"] == 0.125
    assert window_fields(32768, 262144)["window_exceeded"] is False
    assert window_fields(32768, 32768)["window_exceeded"] is True
    assert window_fields(None, 32768)["window_exceeded"] is None
    assert window_fields(32000, None)["window_pressure"] is None


@pytest.mark.parametrize("workspace", ["compliance-reading", "auto-compliance"])
def test_stream_retains_exact_tool_arguments_and_outputs(monkeypatch, workspace):
    import json
    import time

    from scripts.compliance_acceptance import _consume_workspace_stream

    class Response:
        status_code = 200
        headers = {
            "x-portal-route": "compliance-reading;synthetic;build",
            "x-correlation-id": "synthetic",
        }

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_lines(self):
            audit = {
                "type": "exec_audit",
                "tool_calls": [
                    {
                        "tool": "compliance_read",
                        "arguments": '{"ref":"synthetic"}',
                        "output": '{"text":"synthetic source"}',
                    }
                ],
            }
            return iter(
                [
                    "data: " + json.dumps(audit),
                    'data: {"choices":[{"delta":{"content":"answer"},"finish_reason":"stop"}],"usage":{"prompt_tokens":12}}',
                    "data: [DONE]",
                ]
            )

    class Session:
        def stream(self, method, url, **kwargs):
            assert kwargs["json"]["exec_audit"] is True
            return Response()

    monkeypatch.setattr("scripts.compliance_acceptance._api_key", lambda: "synthetic")
    stream = _consume_workspace_stream(
        Session(),
        "http://synthetic",
        workspace,
        [],
        started=time.monotonic(),
        turn_budget_s=10,
        timeout=10,
    )
    assert stream["tool_audit_seen"] is True
    assert stream["tool_outputs"] == [
        {
            "tool": "compliance_read",
            "arguments": '{"ref":"synthetic"}',
            "output": '{"text":"synthetic source"}',
        }
    ]
    assert stream["content_parts"] == ["answer"]
    assert stream["correlation_id"] == "synthetic"


def test_campaign_restores_each_rep_and_preserves_model_writes(tmp_path, monkeypatch):
    import json
    import sqlite3

    from scripts.compliance.truth import run_campaign, store_snapshot

    db = tmp_path / "store.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE notes(body TEXT)")
    snapshot = tmp_path / "campaign.sqlite"
    store_snapshot.snapshot(db, snapshot)
    monkeypatch.setattr("portal.modules.compliance.core.repository.DEFAULT_DB_PATH", db)
    monkeypatch.setattr(
        run_campaign, "index_state", lambda: {"synthetic": {"version": 1, "rows": 0}}
    )
    seen = []

    def rep(out, key, build):
        assert build == "synthetic-build"
        with sqlite3.connect(db) as conn:
            seen.append(conn.execute("SELECT count(*) FROM notes").fetchone()[0])
            conn.execute("INSERT INTO notes VALUES ('synthetic model note')")
        return {"valid": True}

    monkeypatch.setattr(run_campaign, "run_rep", rep)
    out = tmp_path / "runs"
    assert (
        run_campaign.main(
            [
                "--snapshot",
                str(snapshot),
                "--db",
                str(db),
                "--build",
                "synthetic-build",
                "--out-dir",
                str(out),
                "--reps",
                "2",
            ]
        )
        == 0
    )
    assert seen == [0, 0]
    for n in (1, 2):
        assert (out / f"rep{n}" / "post_rep_store.sqlite").exists()
        assert (
            json.loads((out / f"rep{n}" / "isolation.json").read_text())["restore"]["restored"]
            is True
        )


def test_campaign_halts_on_unrestored_external_write(tmp_path, monkeypatch):
    import sqlite3

    from scripts.compliance.truth import run_campaign, store_snapshot

    db = tmp_path / "store.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE notes(body TEXT)")
    snapshot = tmp_path / "campaign.sqlite"
    store_snapshot.snapshot(db, snapshot)
    monkeypatch.setattr("portal.modules.compliance.core.repository.DEFAULT_DB_PATH", db)
    states = iter(
        [
            {"synthetic": {"version": 1, "rows": 0}},
            {"synthetic": {"version": 1, "rows": 0}},
            {"synthetic": {"version": 2, "rows": 1}},
        ]
    )
    monkeypatch.setattr(run_campaign, "index_state", lambda: next(states))
    reps = []
    monkeypatch.setattr(
        run_campaign, "run_rep", lambda out, key, build: reps.append(out) or {"valid": True}
    )
    assert (
        run_campaign.main(
            [
                "--snapshot",
                str(snapshot),
                "--db",
                str(db),
                "--build",
                "synthetic-build",
                "--out-dir",
                str(tmp_path / "runs"),
                "--reps",
                "2",
            ]
        )
        == 1
    )
    assert len(reps) == 1


def test_corrupted_bullet_is_reported_without_claiming_whole_list_match():
    from portal.modules.compliance.core.citation_by_quote import _fold
    from scripts.compliance.truth.citation_integrity import _quote_record

    source = "The vendor portal does not directly access any BES Cyber System"
    other = "Every approved session remains logged for ninety days"
    store = SimpleNamespace(
        _citation_by_quote_index={
            "synthetic-first": (_fold(source), "synthetic-doc"),
            "synthetic-second": (_fold(other), "synthetic-doc"),
        }
    )
    quote = source.replace("does not", "does car") + " • " + other
    record = _quote_record(store, quote, 2)
    assert record["status"] == "near_verbatim"
    assert record["match_scope"] == "bullet_segment"
    assert record["sections"] == []
    assert record["near_matches"][0]["distance"] == 3
    assert record["near_matches"][0]["span"] != quote


def test_campaign_treats_non_pass_receipt_exit_as_valid_but_crash_as_invalid(tmp_path, monkeypatch):
    import subprocess

    from scripts.compliance.truth import run_campaign

    key = tmp_path / "key.yaml"
    key.write_text(
        "status: AGENT_FINAL\nentries:\n- {question_id: 'product:CIP-007-6:exceedance', split: dev}\n"
    )

    def problems(code):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, code))
        out = tmp_path / f"out{code}"
        out.mkdir()
        return run_campaign.run_rep(out, key, "build")["problems"]

    assert not any("harness exit" in p for p in problems(1))
    assert any("harness exit 2" in p for p in problems(2))
