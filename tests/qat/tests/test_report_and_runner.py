"""Offline tests: report writers and the runner (all clients mocked)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest

from tests.qat import artifacts as art
from tests.qat import preflight as pf
from tests.qat import report as rp
from tests.qat import runner as rn
from tests.qat.models import (
    DefectClass,
    GateReport,
    QATResult,
    QATScenario,
    RubricCriterion,
    Status,
)

from .test_config_and_scenarios import make_discovery, make_settings

# ---------------------------------------------------------------- fixtures


def _scn(
    sid: str, stage: int = 2, phase: str = "media_heavy", tier: int = 10, model: str = "auto", **kw
) -> QATScenario:
    kw.setdefault("prompts", ("prompt text",))
    return QATScenario(
        scenario_id=sid, title=sid, stage=stage, phase=phase, tier=tier, model_slug=model, **kw
    )


def _res(
    sid: str, status: Status, detail: str = "ok", defect: DefectClass | None = None
) -> QATResult:
    return QATResult(sid, status, detail, defect_class=defect)


REPORT_SETTINGS = make_settings(Path("/tmp"))


class TestReportWriters:
    def test_jsonl_roundtrip(self, tmp_path: Path) -> None:
        results = [
            _res("a", Status.PASS, "fine"),
            _res("b", Status.FAIL, "broken", DefectClass.MODEL_QUALITY_GAP),
        ]
        path = rp.write_results_jsonl(tmp_path, results)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert [r["scenario_id"] for r in rows] == ["a", "b"]
        assert rows[1]["defect_class"] == "MODEL_QUALITY_GAP"
        assert QATResult.from_dict(rows[1]).defect_class is DefectClass.MODEL_QUALITY_GAP

    def test_markdown_matrix_gaps_and_defects(self, tmp_path: Path) -> None:
        discovery = make_discovery()
        discovery.gaps = ("designed-not-seeded: auto-x",)
        scenarios = [
            _scn("s2-media-a", model="auto-audio"),
            _scn("s2-media-b", model="auto-audio"),
            _scn("s4-core", stage=4, phase="adaptive_deep", tier=200),
        ]
        results = [
            _res("s2-media-a", Status.PASS, "validated"),
            _res("s2-media-b", Status.FAIL, "bad bytes", DefectClass.PRODUCT_BUG),
            _res("s4-core", Status.WARN, "operator to score"),
        ]
        path = rp.write_markdown(tmp_path, discovery, scenarios, results)
        text = path.read_text()
        assert "2 PASS / 0 WARN" not in text  # sanity: counts actually rendered
        assert "1 PASS / 1 WARN / 1 FAIL" in text
        assert "designed-not-seeded: auto-x" in text
        assert "PRODUCT_BUG: 1" in text
        assert "| s2-media-b | PRODUCT_BUG |" in text

    def test_markdown_compliance_annotation_present(self, tmp_path: Path) -> None:
        discovery = make_discovery()
        scenario = _scn("s2-p8-auto-compliance", phase="compliance_smoke")
        scenario.notes = "IN_SERVICE=False: pending V6"
        path = rp.write_markdown(
            tmp_path, discovery, [scenario], [_res(scenario.scenario_id, Status.PASS, "smoke ok")]
        )
        assert "## Annotations" in path.read_text()

    def test_review_html_verdicts_and_escaping(self, tmp_path: Path) -> None:
        scenario = _scn("s2-x", model="auto")
        results = [
            _res("s2-x", Status.FAIL, "leaked <script>alert(1)</script>", DefectClass.UX_RENDER_GAP)
        ]
        path = rp.write_review_html(tmp_path, [scenario], results)
        text = path.read_text()
        assert "<script>alert(1)</script>" not in text
        assert "&lt;script&gt;" in text
        verdicts = json.loads(
            text.split("<script id='verdicts' type='application/json'>")[1]
            .split("</script>")[0]
            .replace("<\\/", "</")
        )
        assert verdicts[0]["status"] == "FAIL"
        assert "Export verdicts JSON" in text

    def test_review_html_gallery(self, tmp_path: Path) -> None:
        shots = tmp_path / "screenshots"
        shots.mkdir()
        (shots / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\nrest")
        path = rp.write_review_html(tmp_path, [], [], shots_dir=shots)
        assert "screenshots/shot.png" in path.read_text()


# ---------------------------------------------------------------- runner helpers


class TestPlanAndOrder:
    def test_dry_run_prints_plan_without_network(self, capsys: pytest.CaptureFixture) -> None:
        settings = make_settings(Path("/tmp"))
        opts = rn.RunnerOptions(
            stages={0, 1, 2, 3, 4}, phases=set(), only_scenarios=set(), dry_run=True
        )
        state = rn.run_selected(settings, opts)
        out = capsys.readouterr().out
        assert "dry run" in out.lower()
        assert "stage 0 · phase preflight" in out
        assert "stage 1 · phase hardening" in out
        assert "stage 2 · phase smoke_routing" in out
        assert "stage 4 · phase adaptive_deep" in out
        assert state.results == []  # zero execution
        assert "scenarios       :" in out

    def test_qat_run_meta_records_cleaned_and_restored_owui_memories(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        class MemoryClient:
            memories = [{"type": "user", "path": None, "content": "private baseline"}]
            restored = False
            events: list[str] = []

            def snapshot_memories(self, token: str) -> list[dict[str, str | None]]:
                assert token == "token"
                self.events.append("snapshot")
                return list(self.memories)

            def clear_memories(self, token: str) -> None:
                assert token == "token"
                self.events.append("clear")
                self.memories = []

            def restore_memories(self, token: str, snapshot: list[dict[str, str | None]]) -> None:
                assert token == "token"
                self.events.append("restore")
                self.memories = list(snapshot)
                self.restored = True

        client = MemoryClient()
        settings = make_settings(tmp_path)
        state = rn.RunState(settings, tmp_path, make_discovery())
        scenario = _scn("s5-memory-cross-session", stage=5, kind="uat")
        options = rn.RunnerOptions({5}, set(), set())
        scenario_facts: dict[str, str] = {}

        def execute(*_args: object, **_kwargs: object) -> None:
            assert client.memories == []
            meta = json.loads((tmp_path / "run_meta.json").read_text())
            assert meta["owui_memory_state"]["status"] == "clean"
            client.events.append("save-chat")
            assert client.memories == []
            scenario_facts.update({"project_code": "QATUAT-42", "preferred_color": "cobalt"})
            client.events.append("recall-chat")
            assert client.memories == []
            assert scenario_facts == {"project_code": "QATUAT-42", "preferred_color": "cobalt"}

        monkeypatch.setattr(rn, "_execute", execute)
        rn._run_with_clean_owui_memories(client, "token", settings, [scenario], state, options, {})

        meta = json.loads((tmp_path / "run_meta.json").read_text())
        assert meta["owui_memory_state"]["status"] == "restored"
        assert meta["owui_memory_state"]["baseline_count"] == 1
        assert meta["owui_memory_state"]["restored_count"] == 1
        assert "private baseline" not in json.dumps(meta)
        assert client.restored
        assert client.events == ["snapshot", "clear", "save-chat", "recall-chat", "restore"]

    def test_cascade_order_tier_model_id(self) -> None:
        plan = [
            _scn("b", tier=10, model="z"),
            _scn("a", tier=5, model="b"),
            _scn("c", tier=10, model="a"),
        ]
        ordered = sorted(plan, key=lambda s: s.cascade_key())
        assert [s.scenario_id for s in ordered] == ["a", "c", "b"]

    def test_want_filters(self) -> None:
        opts = rn.RunnerOptions(
            stages={2}, phases={"media_heavy"}, only_scenarios=set(), browser_only=True
        )
        media_browser = _scn("x", stage=2, phase="media_heavy", browser=True)
        media_api = _scn("y", stage=2, phase="media_heavy")
        other_stage = _scn("z", stage=3, phase="security_hunt")
        assert rn._want(media_browser, opts)
        assert not rn._want(media_api, opts)
        assert not rn._want(other_stage, opts)

    def test_full_plan_runs_stages_in_order_with_contiguous_phases(self) -> None:
        """Stages 0→5 in order, one contiguous block per (stage, phase): no tier collision."""
        settings = make_settings(Path("/tmp"))
        _, plan = rn.build_plan(settings)
        assert any(s.stage == 5 for s in plan)
        blocks: list[tuple[int, str]] = []
        for s in plan:
            if not blocks or blocks[-1] != (s.stage, s.phase):
                blocks.append((s.stage, s.phase))
        assert len(blocks) == len(set(blocks))
        assert [stage for stage, _ in blocks] == sorted(stage for stage, _ in blocks)

    def test_every_preflight_executor_has_a_stage0_scenario(self) -> None:
        """A wired executor without a plan scenario never runs (the load-guard
        probe sat dead this way); the plan and the executor map must match."""
        planned = {s.scenario_id for s in rn._stage0_scenarios()}
        assert planned == set(rn.PREFLIGHT_FNS)


class TestPreflightInterpreter:
    def test_preflight_subprocesses_use_current_interpreter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        commands: list[list[str]] = []

        def fake_run_cmd(cmd: list[str], cwd: Path, timeout_s: int = 900) -> tuple[int, str]:
            commands.append(cmd)
            if cmd[1:] == [pf.PREFLIGHT_SCRIPT, "--json"]:
                return 0, '{"production_workspaces": [], "personas": []}'
            return 0, "ok"

        monkeypatch.setattr(pf, "run_cmd", fake_run_cmd)
        settings = make_settings(Path("/tmp"))
        pf.run_preflight_script(settings)
        pf.run_routing_regression(settings)
        pf.run_trace_sections(settings)
        pf.run_lab_ready(settings)

        assert [cmd[0] for cmd in commands] == [sys.executable] * 4
        assert commands[2][:4] == [
            sys.executable,
            "-m",
            "portal.platform.inference.cli",
            "trace",
        ]


@dataclass
class FakeResponse:
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


@dataclass
class FakeOutcome:
    chat_id: str = "chat-1"
    text: str = "the answer"
    done: bool = True
    served_model: str = "d:8b"
    artifact_urls: tuple[str, ...] = ()
    leak_marker: str | None = None
    trace: dict = field(default_factory=lambda: {"backend": "omlx-general"})
    tool_calls: tuple[dict, ...] = ()


VALID_WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16
VALID_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16


class FakeOWUI:
    """Class-level `mode` drives poll/download behaviour per test."""

    instances: list[FakeOWUI] = []
    mode: str = "valid"  # valid | missing | bad | leak

    def __init__(self, settings: object, transport: object = None) -> None:
        self.settings = settings
        self.renamed: list[tuple[str, str]] = []
        self.archived: list[str] = []
        self.deleted: list[str] = []
        self.sent_images: list[bytes | None] = []
        FakeOWUI.instances.append(self)

    def signin(self) -> str:
        return "token"

    def create_chat(self, token: str, model_slug: str, title: str, prompt: str = "") -> str:
        return "chat-1"

    def send_turn(
        self,
        token: str,
        chat_id: str,
        model_slug: str,
        prompt: str,
        tool_ids: tuple[str, ...] = (),
        function_calling: bool = False,
        prior_messages: list[dict] | None = None,
        files: list[dict] | None = None,
        image_png: bytes | None = None,
        deadline: float | None = None,
    ) -> FakeResponse:
        self.sent_images.append(image_png)
        if type(self).mode == "http404":
            return FakeResponse(status_code=404)
        return FakeResponse()

    def poll_turn(self, token: str, chat_id: str, **kwargs: object) -> FakeOutcome:
        mode = type(self).mode
        requested = str(kwargs.get("model_slug") or "")
        routed = requested if rn.primary_model_for(requested) else "auto-daily"
        return FakeOutcome(
            text="leak JSONDecodeError happened" if mode == "leak" else "the answer",
            leak_marker="JSONDecodeError" if mode == "leak" else None,
            artifact_urls=()
            if mode == "missing"
            else ("/files/a.mp4",)
            if mode == "short_mp4"
            else ("/files/a.wav",),
            trace={
                "workspace": routed,
                "requested": requested,
                "model": rn.primary_model_for(routed),
                "backend": "omlx-general",
            },
        )

    def download_artifact(self, token: str, url: str) -> bytes:
        if type(self).mode == "short_mp4":
            return VALID_MP4
        return VALID_WAV if type(self).mode == "valid" else b"not-a-wav"

    def rename_chat(self, token: str, chat_id: str, title: str) -> None:
        self.renamed.append((chat_id, title))

    def archive_chat(self, token: str, chat_id: str, date: str) -> tuple[bool, str]:
        self.archived.append(chat_id)
        return True, "archived"

    def delete_chat(self, token: str, chat_id: str) -> bool:
        self.deleted.append(chat_id)
        return True


@pytest.fixture()
def fake_owui(monkeypatch: pytest.MonkeyPatch) -> type[FakeOWUI]:
    FakeOWUI.instances = []
    FakeOWUI.mode = "valid"
    monkeypatch.setattr(rn, "OWUIClient", FakeOWUI)
    return FakeOWUI


def _chat_opts(**kw) -> rn.RunnerOptions:
    base: dict = {"stages": {2}, "phases": set(), "only_scenarios": set(), "dry_run": False}
    base.update(kw)
    return rn.RunnerOptions(**base)


class TestChatExecution:
    def test_pass_flow_renames_and_archives(self, fake_owui, tmp_path: Path) -> None:
        settings = make_settings(tmp_path)
        scenario = _scn("s2-chat", model="auto-daily")
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        result = rn._execute_one(settings, scenario, state, _chat_opts())
        assert result.status is Status.PASS
        client = fake_owui.instances[0]
        assert client.archived == ["chat-1"]
        assert client.deleted == []
        assert client.renamed[0][1].startswith("[PASS]")
        assert result.backend == "omlx-general"

    def test_cleanup_deletes_instead_of_archiving(self, fake_owui, tmp_path: Path) -> None:
        settings = make_settings(tmp_path)
        scenario = _scn("s2-chat", model="auto-daily")
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        rn._execute_one(settings, scenario, state, _chat_opts(cleanup_chats=True))
        client = fake_owui.instances[0]
        assert client.deleted == ["chat-1"]
        assert client.archived == []

    def test_send_turn_4xx_is_infra_not_model_miss(self, fake_owui, tmp_path: Path) -> None:
        FakeOWUI.mode = "http404"
        settings = make_settings(tmp_path)
        scenario = _scn("s2-chat", model="auto-daily")
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        result = rn._execute_one(settings, scenario, state, _chat_opts())
        assert result.status is Status.FAIL
        assert "HTTP 404" in result.detail
        assert result.defect_class is DefectClass.INFRA_ENV_GAP

    def test_artifact_validation_pass(self, fake_owui, tmp_path: Path) -> None:
        settings = make_settings(tmp_path)
        scenario = _scn("s2-media", model="auto-audio::music", artifact_kind="wav")
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        result = rn._execute_one(settings, scenario, state, _chat_opts())
        assert result.status is Status.PASS
        assert result.artifacts == ("/files/a.wav",)

    def test_artifact_validation_bad_bytes_fails(self, fake_owui, tmp_path: Path) -> None:
        FakeOWUI.mode = "bad"
        settings = make_settings(tmp_path)
        scenario = _scn("s2-media", model="auto-audio::music", artifact_kind="wav")
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        result = rn._execute_one(settings, scenario, state, _chat_opts())
        assert result.status is Status.FAIL
        assert "validation" in result.detail
        assert result.defect_class is DefectClass.PRODUCT_BUG

    def test_short_mp4_fails_the_requested_duration(self, fake_owui, tmp_path: Path, monkeypatch):
        from types import SimpleNamespace

        FakeOWUI.mode = "short_mp4"
        monkeypatch.setattr(art.shutil, "which", lambda _name: "/usr/bin/ffprobe")
        monkeypatch.setattr(
            art.subprocess,
            "run",
            lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="1.0\n", stderr=""),
        )
        settings = make_settings(tmp_path)
        scenario = _scn(
            "s2-video",
            model="auto-audio::video",
            artifact_kind="mp4",
            artifact_min_duration_s=3.0,
        )
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())

        result = rn._execute_one(settings, scenario, state, _chat_opts())

        assert result.status is Status.FAIL
        assert "MP4 duration 1.00s is below required 3.00s" in result.detail
        assert result.defect_class is DefectClass.PRODUCT_BUG

    def test_missing_artifact_fails(self, fake_owui, tmp_path: Path) -> None:
        FakeOWUI.mode = "missing"
        settings = make_settings(tmp_path)
        scenario = _scn("s2-media", model="auto-audio::music", artifact_kind="wav")
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        result = rn._execute_one(settings, scenario, state, _chat_opts())
        assert result.status is Status.FAIL
        assert "no artifact URL matches wav" in result.detail

    def test_leak_marker_is_product_bug(self, fake_owui, tmp_path: Path) -> None:
        FakeOWUI.mode = "leak"
        settings = make_settings(tmp_path)
        scenario = _scn("s2-chat", model="auto")
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        result = rn._execute_one(settings, scenario, state, _chat_opts())
        assert result.status is Status.FAIL
        assert result.defect_class is DefectClass.PRODUCT_BUG


class TestDisabledAndRequires:
    def test_disabled_scenario_skips_with_annotation(self, tmp_path: Path) -> None:
        settings = make_settings(tmp_path)
        scenario = _scn(
            "s3-canonical",
            stage=3,
            phase="security_canonical",
            notes="disabled: module security_redteam off",
        )
        scenario.enabled = False
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        result = rn._execute_one(settings, scenario, state, _chat_opts())
        assert result.status is Status.SKIP
        assert "security_redteam" in result.detail

    def test_requires_gate_skips(self, fake_owui, tmp_path: Path) -> None:
        settings = make_settings(tmp_path)
        scenario = _scn(
            "s3-lab-exec",
            stage=3,
            phase="security_adversarial",
            tier=120,
            requires=("p0-lab-ready",),
        )
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        state.results.append(_res("p0-lab-ready", Status.WARN, "lab not ready"))
        result = rn._execute_one(settings, scenario, state, _chat_opts())
        assert result.status is Status.SKIP
        assert "requirement not met" in result.detail

    def test_compliance_annotation_appended(self, tmp_path: Path) -> None:
        scenario = _scn(
            "s2-p8-auto-compliance",
            phase="compliance_smoke",
            tags=("compliance", "in_service_false"),
        )
        result = _res(scenario.scenario_id, Status.PASS, "smoke ok")
        rn._annotate(scenario, result)
        assert "IN_SERVICE=False" in result.detail


class TestInfraExecution:
    def test_infra_probes_fleet_health(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path in ("/health", "/ready"):
                return httpx.Response(200, json={"status": "ok"})
            return httpx.Response(500)

        monkeypatch.setattr(rn.httpx, "Client", _client_factory(httpx.MockTransport(handler)))
        settings = make_settings(tmp_path)
        scenario = _scn("s2-p3-data-mcp", kind="infra", tags=("mcp", "data"))
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        result = rn._execute_one(settings, scenario, state, _chat_opts())
        assert result.status is Status.PASS
        assert "8939" in result.detail

    def test_infra_down_fails(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(
            rn.httpx,
            "Client",
            _client_factory(httpx.MockTransport(lambda request: httpx.Response(503))),
        )
        settings = make_settings(tmp_path)
        scenario = _scn("s2-p3-data-mcp", kind="infra", tags=("mcp", "data"))
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        result = rn._execute_one(settings, scenario, state, _chat_opts())
        assert result.status is Status.FAIL

    def test_infra_without_targets_skips(self, tmp_path: Path) -> None:
        settings = make_settings(tmp_path)
        scenario = _scn("s-x", kind="infra", tags=("nope",))
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        result = rn._execute_one(settings, scenario, state, _chat_opts())
        assert result.status is Status.SKIP


def _client_factory(transport: object):
    real_client = httpx.Client

    def factory(**kwargs: object) -> httpx.Client:
        kwargs.pop("timeout", None)
        return real_client(transport=transport)

    return factory


class TestCascade:
    def test_gate_block_cascades_blocked_rows(
        self, monkeypatch: pytest.MonkeyPatch, fake_owui, tmp_path: Path
    ) -> None:
        gate_calls = 0

        def gate_sequence(*args: object, **kwargs: object) -> GateReport:
            nonlocal gate_calls
            gate_calls += 1
            blocked = gate_calls > 1
            return GateReport(phase="p2", ok=not blocked, blocked=blocked)

        monkeypatch.setattr(rn.gate, "run_gate", gate_sequence)
        settings = make_settings(tmp_path)
        plan = [
            _scn("s2-p1-a", tier=10),
            _scn("s2-p2-b", phase="reasoning", tier=20),
            _scn("s2-p2-c", phase="reasoning", tier=20),
        ]
        state = rn.RunState(
            settings=settings, run_dir=tmp_path, discovery=make_discovery(), scenarios=plan
        )
        rn._execute(settings, plan, state, _chat_opts(), previous={})
        statuses = {r.scenario_id: r.status for r in state.results}
        assert statuses["s2-p1-a"] is Status.PASS
        assert statuses["s2-p2-b"] is Status.BLOCKED
        assert statuses["s2-p2-c"] is Status.BLOCKED
        assert state.stages[1].gate is not None and state.stages[1].gate.blocked

    def test_append_and_rerun_failed_loading(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        rows = [
            _res("keep-pass", Status.PASS),
            _res("keep-warn", Status.WARN),
            _res("fix-me", Status.FAIL, detail="old"),
        ]
        rp.write_results_jsonl(run_dir, rows)
        append, sha = rn._load_previous(_chat_opts(resume_dir=run_dir, resume_mode="append"))
        assert set(append) == {"keep-pass", "keep-warn", "fix-me"}
        assert sha == ""  # dir predates provenance records
        rerun, _ = rn._load_previous(_chat_opts(resume_dir=run_dir, resume_mode="rerun-failed"))
        assert set(rerun) == {"keep-pass", "keep-warn"}
        with pytest.raises(FileNotFoundError):
            rn._load_previous(_chat_opts(resume_dir=tmp_path / "nope", resume_mode="append"))

    def test_resume_sha_read_from_run_meta(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        rp.write_results_jsonl(run_dir, [_res("keep-pass", Status.PASS)])
        (run_dir / "run_meta.json").write_text(
            json.dumps({"git_sha": "abc1234", "resume_mode": ""}) + "\n", encoding="utf-8"
        )
        _, sha = rn._load_previous(_chat_opts(resume_dir=run_dir, resume_mode="rerun-failed"))
        assert sha == "abc1234"

    def test_provenance_marks_stitched_rows_in_the_report(self, tmp_path: Path) -> None:
        """A stitched report must say which code graded which rows — without
        this, --rerun-failed mixes SHAs silently."""
        discovery = make_discovery()
        scenarios = [_scn("keep-pass", model="auto")]
        results = [_res("keep-pass", Status.PASS)]
        provenance = {
            "created_at": "2026-11-25T00:00:00+00:00",
            "git_sha": "newsha",
            "resume_dir": "/results/qat/old",
            "resume_mode": "rerun-failed",
            "stitched_rows": 1,
            "resume_sha": "oldsha",
        }
        path = rp.write_markdown(tmp_path, discovery, scenarios, results, provenance)
        text = path.read_text(encoding="utf-8")
        assert "## Run provenance" in text
        assert "newsha" in text
        assert "stitched rows: 1 of 1 from /results/qat/old (rerun-failed)" in text
        assert "oldsha" in text

    def test_unknown_resume_sha_is_reported_as_unknown(self, tmp_path: Path) -> None:
        discovery = make_discovery()
        scenarios = [_scn("keep-pass", model="auto")]
        results = [_res("keep-pass", Status.PASS)]
        provenance = {
            "created_at": "",
            "git_sha": "",
            "resume_dir": "/results/qat/old",
            "resume_mode": "append",
            "stitched_rows": 1,
            "resume_sha": "",
        }
        path = rp.write_markdown(tmp_path, discovery, scenarios, results, provenance)
        text = path.read_text(encoding="utf-8")
        assert "unknown (no git metadata)" in text
        assert "unknown (predates provenance records)" in text

    def test_report_without_provenance_has_no_provenance_section(self, tmp_path: Path) -> None:
        path = rp.write_markdown(tmp_path, make_discovery(), [_scn("s", model="auto")], [])
        assert "## Run provenance" not in path.read_text(encoding="utf-8")

    def test_rerun_failed_latest_failure_drops_an_earlier_pass(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        rp.write_results_jsonl(
            run_dir,
            [
                _res("same", Status.PASS),
                _res("same", Status.FAIL, detail="later"),
                _res("dep", Status.SKIP, detail="requirement not met: p0-lab-ready"),
                _res("held-skip", Status.SKIP, detail="disabled"),
            ],
        )
        rerun, _ = rn._load_previous(_chat_opts(resume_dir=run_dir, resume_mode="rerun-failed"))
        assert set(rerun) == {"held-skip"}


class TestWorksheets:
    def test_emit_and_ingest_roundtrip(self, tmp_path: Path) -> None:
        scenario = _scn("s4-core", stage=4, phase="adaptive_deep", tier=200)
        scenario.rubric = (RubricCriterion(key="core", label="Core", guidance="5: complete"),)
        rn._emit_worksheets(tmp_path, [scenario])
        ws = tmp_path / "worksheets" / "s4-core.json"
        data = json.loads(ws.read_text())
        assert data["operator_score"] is None
        assert data["criteria"][0]["key"] == "core"
        data["operator_score"] = 4
        data["operator_notes"] = "solid"
        ws.write_text(json.dumps(data))
        rn._ingest_worksheets(tmp_path, [scenario])
        frozen = json.loads((tmp_path / "worksheets_frozen.json").read_text())
        assert frozen == {"s4-core": {"score": 4, "notes": "solid"}}

    def test_ingest_rejects_out_of_range_scores(self, tmp_path: Path) -> None:
        scenario = _scn("s4-core", stage=4, phase="adaptive_deep", tier=200)
        rn._emit_worksheets(tmp_path, [scenario])
        ws = tmp_path / "worksheets" / "s4-core.json"
        data = json.loads(ws.read_text())
        data["operator_score"] = 9
        ws.write_text(json.dumps(data))
        rn._ingest_worksheets(tmp_path, [scenario])
        assert json.loads((tmp_path / "worksheets_frozen.json").read_text()) == {}


class TestIntraPhaseEviction:
    def test_change_evicts_and_same_primary_does_not(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        evicted: list[str] = []
        hints = {"ws-a": "model-a", "ws-b": "model-b", "ws-b2": "model-b"}
        real_change = rn._evict_on_primary_change

        def evict(settings: object) -> list[QATResult]:
            evicted.append("evict")
            return []

        def on_change(
            settings: object, previous: str | None, scenario: QATScenario
        ) -> tuple[str | None, QATResult | None]:
            before = len(evicted)
            primary, failed = real_change(settings, previous, scenario)  # type: ignore[arg-type]
            if len(evicted) != before:
                evicted[-1] = scenario.scenario_id
            return primary, failed

        monkeypatch.setattr(rn, "_evict_resident_engines", evict)
        monkeypatch.setattr(rn, "_evict_on_primary_change", on_change)
        monkeypatch.setattr(rn.gate, "run_gate", lambda *a, **k: GateReport(phase="p", ok=True))
        monkeypatch.setattr(
            rn, "primary_model_for", lambda slug, portal_data=None: hints.get(slug, "")
        )
        monkeypatch.setattr(
            rn,
            "_execute_one",
            lambda settings, scenario, state, opts: QATResult(scenario.scenario_id, Status.PASS),
        )
        disabled = _scn("disabled-b", phase="one", model="ws-b")
        disabled.enabled = False
        plan = [
            _scn("same-1", phase="one", model="ws-a"),
            disabled,
            _scn("same-2", phase="one", model="ws-a"),
            _scn("switch-b", phase="one", model="ws-b"),
            _scn("same-hint", phase="one", model="ws-b2"),
            _scn("infra", phase="one", model="ws-a", kind="infra"),
            _scn("switch-pipe", phase="one", model="ws-a", kind="pipeline"),
            _scn("phase-reset", phase="two", model="ws-b"),
            _scn("phase-switch", phase="two", model="ws-a"),
        ]
        settings = make_settings(tmp_path)
        state = rn.RunState(
            settings=settings, run_dir=tmp_path, discovery=make_discovery(), scenarios=plan
        )
        rn._execute(settings, plan, state, _chat_opts(), previous={})
        assert evicted == ["switch-b", "switch-pipe", "phase-switch"]

    def test_resumed_scenario_does_not_arm_eviction(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        evicted: list[str] = []
        monkeypatch.setattr(rn, "_evict_resident_engines", lambda settings: evicted.append("x"))
        monkeypatch.setattr(rn.gate, "run_gate", lambda *a, **k: GateReport(phase="p", ok=True))
        monkeypatch.setattr(
            rn,
            "primary_model_for",
            lambda slug, portal_data=None: {"ws-a": "model-a", "ws-b": "model-b"}.get(slug, ""),
        )
        monkeypatch.setattr(
            rn,
            "_execute_one",
            lambda settings, scenario, state, opts: QATResult(scenario.scenario_id, Status.PASS),
        )
        plan = [
            _scn("ran-earlier", phase="one", model="ws-a"),
            _scn("first-this-process", phase="one", model="ws-b"),
        ]
        settings = make_settings(tmp_path)
        state = rn.RunState(
            settings=settings, run_dir=tmp_path, discovery=make_discovery(), scenarios=plan
        )
        previous = {"ran-earlier": QATResult("ran-earlier", Status.PASS)}
        rn._execute(settings, plan, state, _chat_opts(), previous=previous)
        assert evicted == []

    def test_resident_engines_unload_only_when_resident(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        calls: list[tuple[str, tuple[str, ...]]] = []

        def cold(client: object, settings: object) -> tuple[QATResult, list[str]]:
            return QATResult("gate", Status.PASS, "cold"), []

        monkeypatch.setattr(rn.gate, "ollama_residency", cold)
        monkeypatch.setattr(rn.gate, "omlx_residency", cold)
        monkeypatch.setattr(
            rn.gate, "evict_ollama", lambda *a, **k: calls.append(("ol", ())) or QATResult("g")
        )
        monkeypatch.setattr(
            rn.gate, "evict_omlx", lambda *a, **k: calls.append(("ox", ())) or QATResult("g")
        )
        rn._evict_resident_engines(make_settings(tmp_path))
        assert calls == []

        monkeypatch.setattr(
            rn.gate,
            "ollama_residency",
            lambda c, s: (QATResult("g", Status.WARN, "resident"), ["gguf:a"]),
        )
        monkeypatch.setattr(
            rn.gate,
            "omlx_residency",
            lambda c, s: (QATResult("g", Status.WARN, "resident"), ["mlx-a"]),
        )
        monkeypatch.setattr(
            rn.gate,
            "evict_ollama",
            lambda c, s, resident: calls.append(("ol", tuple(resident))) or QATResult("g"),
        )
        monkeypatch.setattr(
            rn.gate,
            "evict_omlx",
            lambda c, s, resident: calls.append(("ox", tuple(resident))) or QATResult("g"),
        )
        rn._evict_resident_engines(make_settings(tmp_path))
        assert calls == [("ol", ("gguf:a",)), ("ox", ("mlx-a",))]


class TestVisionImage:
    def test_auto_vision_turn_sends_png_bytes(
        self, fake_owui: type[FakeOWUI], tmp_path: Path
    ) -> None:
        from tests.qat import scenarios as scn

        settings = make_settings(tmp_path)
        scenario = _scn(
            "s2-p2-auto-vision",
            model="auto-vision",
            phase="reasoning_vision_research",
            attachment=scn.INLINE_VISION_PNG,
            prompts=(scn.VISION_PROBE,),
        )
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        result = rn._execute_one(settings, scenario, state, _chat_opts())
        assert result.status is Status.PASS
        png = fake_owui.instances[0].sent_images[0]
        assert png is not None
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert png[16:24] == b"\x00\x00\x00@\x00\x00\x00@"


class TestBrowserExecution:
    def test_browser_skip_without_playwright(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from tests.qat import browser_ui as bu

        def boom() -> object:
            raise bu.PlaywrightUnavailable("Playwright not installed — run uv sync")

        monkeypatch.setattr(bu, "load_playwright", boom)
        settings = make_settings(tmp_path)
        scenario = _scn("s2-p1-ui-roster", browser=True)
        state = rn.RunState(settings=settings, run_dir=tmp_path, discovery=make_discovery())
        result = rn._execute_one(settings, scenario, state, _chat_opts())
        assert result.status is Status.SKIP
        assert "playwright" in result.detail.lower()


class TestPipelineChat:
    def test_pipeline_turn_pass(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content.decode())
            captured["auth"] = request.headers.get("authorization", "")
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "T1566 then T1078"}}]}
            )

        monkeypatch.setattr(rn.httpx, "Client", _client_factory(httpx.MockTransport(handler)))
        settings = make_settings(tmp_path)
        scenario = _scn(
            "s3-canonical-auto-security-blueteam",
            stage=3,
            phase="security_canonical",
            model="auto-security::blueteam",
            kind="pipeline",
        )
        monkeypatch.setattr(
            rn.OWUIClient,
            "lookup_trace",
            lambda self, **kwargs: {
                "workspace": scenario.model_slug,
                "model": rn.primary_model_for(scenario.model_slug),
                "backend": "ollama-security",
            },
        )
        result = rn._run_pipeline_chat(settings, scenario)
        assert result.status is Status.PASS
        assert captured["body"]["model"] == "auto-security::blueteam"
        assert captured["auth"] == "Bearer test-key"

    def test_pipeline_turn_5xx_is_infra_gap(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(502)

        monkeypatch.setattr(rn.httpx, "Client", _client_factory(httpx.MockTransport(handler)))
        settings = make_settings(tmp_path)
        scenario = _scn(
            "s3-x",
            stage=3,
            phase="security_canonical",
            model="auto-security::blueteam",
            kind="pipeline",
        )
        result = rn._run_pipeline_chat(settings, scenario)
        assert result.status is Status.FAIL
        assert result.defect_class is DefectClass.INFRA_ENV_GAP

    def test_pipeline_turn_4xx_is_infra_not_model_miss(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A 4xx is pre-inference (auth, addressing, request shape): the model
        never produced output, so it must not count as MODEL_QUALITY_GAP."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": "no such model"})

        monkeypatch.setattr(rn.httpx, "Client", _client_factory(httpx.MockTransport(handler)))
        settings = make_settings(tmp_path)
        scenario = _scn(
            "s3-x",
            stage=3,
            phase="security_canonical",
            model="auto-security::blueteam",
            kind="pipeline",
        )
        result = rn._run_pipeline_chat(settings, scenario)
        assert result.status is Status.FAIL
        assert result.defect_class is DefectClass.INFRA_ENV_GAP

    def test_pipeline_turn_leak_is_product_bug(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            content = "Traceback (most recent call last): oops"
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

        monkeypatch.setattr(rn.httpx, "Client", _client_factory(httpx.MockTransport(handler)))
        settings = make_settings(tmp_path)
        scenario = _scn(
            "s3-x",
            stage=3,
            phase="security_canonical",
            model="auto-security::blueteam",
            kind="pipeline",
        )
        monkeypatch.setattr(
            rn.OWUIClient,
            "lookup_trace",
            lambda self, **kwargs: {
                "workspace": scenario.model_slug,
                "model": rn.primary_model_for(scenario.model_slug),
                "backend": "ollama-security",
            },
        )
        result = rn._run_pipeline_chat(settings, scenario)
        assert result.status is Status.FAIL
        assert result.defect_class is DefectClass.PRODUCT_BUG


class TestDiscoveryInRunState:
    def test_fleet_ports(self, tmp_path: Path) -> None:
        state = rn.RunState(
            settings=make_settings(tmp_path), run_dir=tmp_path, discovery=make_discovery()
        )
        assert state.fleet_ports["data"] == 8939
        assert state.fleet_ports["proxmox"] == 8927
