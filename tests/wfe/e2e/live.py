"""Live acceptance: the rig's scenarios against the DEPLOYED production stack and real models.

    uv run python -m tests.wfe.e2e.rig --live

The fake rig proves the code paths offline; this proves the real-life use case. It talks to
the pipeline and MCPs at their production addresses (the harness's own defaults), reads every
piece of evidence from production's own trace and stores, and refuses to start unless the
deployed pipeline is HEAD and every MCP answers with this code.

What it writes: rig campaigns (deleted unless --keep), scoped data that each row's cleanup
deletes, and ONE unscoped marker memory (S16, to prove injection works at all), deleted by id
in a finally and verified gone. S6 (an engine failing mid-arm) and S11 (a non-HEAD deployed
build) are offline-only: proving them live would mean breaking a production engine or
deploying a stale build. S5 runs live as a model that is not installed.
"""

from __future__ import annotations

import http.client
import json
import os
import signal
import time
import urllib.request
import uuid
from pathlib import Path

import yaml

from tests.wfe import campaign, eval_mode
from tests.wfe.e2e.rig import CAMPAIGNS, DRIFT_PROBE, PLAN, REPO, Rig

PIPE = os.environ.get("WFE_CHAT_BASE_URL", "http://localhost:9099").rstrip("/")
MCP = {
    "documents": eval_mode.DOCUMENTS_MCP_URL,
    "data": eval_mode.DATA_MCP_URL,
    "memory": eval_mode.MEMORY_MCP_URL,
    "rag": eval_mode.RAG_MCP_URL,
}
SCOPE_ALL = {"campaign": "wfe_" + "0" * 16, "run": "wfe_" + "0" * 40, "allow": []}


def _seat(ws: str) -> str:
    from portal.platform.inference.config import effective_workspace

    workspaces = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    return effective_workspace(workspaces, ws)["model_hint"]


class LiveRig(Rig):
    def __init__(self, keep: bool):
        super().__init__((0, 0, 0, 0, 0), keep)
        self.key = eval_mode.setting("PIPELINE_API_KEY", "")

    def env(self) -> dict:
        return {**os.environ, "WFE_ENGINE": "pipeline", "PIPELINE_API_KEY": self.key}

    # ── production's own evidence ──────────────────────────────────────────
    def _req(
        self, url: str, body: dict | None = None, cid: str | None = None, auth: bool = False
    ) -> dict:
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self.key}"
        if cid:
            headers["X-Correlation-ID"] = cid
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, headers=headers, method="POST" if data else "GET"
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return {"status": r.status, **(json.loads(r.read() or b"{}") or {})}
        except urllib.error.HTTPError as e:
            return {"status": e.code, **(json.loads(e.read() or b"{}") or {})}

    def mcp(self, name: str, path: str, body: dict) -> dict:
        return self._req(f"{MCP[name]}{path}", body)

    def chat(self, ws: str, text: str, scope: dict | None = None) -> tuple[str, dict]:
        cid = f"wfe-live-{uuid.uuid4().hex[:12]}"
        body = {"model": ws, "stream": False, "messages": [{"role": "user", "content": text}]}
        self._req(
            f"{PIPE}/v1/chat/completions",
            {**body, **({"portal_eval": scope} if scope else {})},
            cid,
            True,
        )
        time.sleep(1)
        return cid, self._req(f"{PIPE}/v1/trace/{cid}", auth=True)

    def preconditions(self) -> list[str]:
        bad = []
        build = self._req(f"{PIPE}/health").get("build_sha")
        if not campaign.deployed_matches(build):
            bad.append(f"deployed pipeline build {build!r} is not HEAD's portal/: rebuild first")
        probes = (
            ("documents", "/tools/_unique_path", {"arguments": {}}, 404),
            ("data", "/eval/close_session", {}, 400),
            ("memory", "/eval/forget_scope", {}, 400),
            ("rag", "/eval/drop_kb", {}, 400),
        )
        bad += campaign.service_findings(campaign.deployed_services())
        for name, path, body, want in probes:
            got = self.mcp(name, path, body).get("status")
            if got != want:
                bad.append(
                    f"{name} MCP answered {got} to {path}, this code answers {want}: restart it"
                )
        return bad

    def run(self) -> int:
        self.compliance_before = operator_compliance_digest()
        (self.tmp / "pids").write_text("")
        bad = self.preconditions()
        if bad:
            for b in bad:
                print(f"PRECONDITION  {b}")
            return 2
        try:
            live_scenarios(self)
            after = operator_compliance_digest()
            self.check(
                "S19 the operator's compliance store is unchanged by the whole live run",
                self.compliance_before is not None and after == self.compliance_before,
                f"store={OPERATOR_COMPLIANCE_DB} digest_before={self.compliance_before} after={after}",
            )
        finally:
            DRIFT_PROBE.unlink(missing_ok=True)
            if not self.keep:
                import shutil

                for c in self.campaigns:
                    shutil.rmtree(CAMPAIGNS / c, ignore_errors=True)
        (self.tmp / "receipt.json").write_text(
            json.dumps({"head": self.head, "mode": "live", "results": self.results}, indent=1)
        )
        failed = [r for r in self.results if r["status"] == "FAIL"]
        print(
            f"\nlive: {sum(r['status'] == 'PASS' for r in self.results)}/{len(self.results)} PASS "
            f"({sum(r['status'] == 'OFFLINE-ONLY' for r in self.results)} offline-only); "
            f"receipt {self.tmp}/receipt.json"
        )
        return 1 if failed else 0

    def offline_only(self, name: str, why: str) -> None:
        self.results.append({"scenario": name, "status": "OFFLINE-ONLY", "evidence": why})
        print(f"OFFLINE-ONLY  {name}: {why}")


def live_scenarios(rig: LiveRig) -> None:
    inc, ch = _seat("auto-compliance"), "granite4.1:30b-ctx64k"
    one = ["--task", "comp-p6j-01", "--repeats", "1"]
    c1 = rig.cid("main")
    r = rig.cli("--plan", str(PLAN), "--campaign-id", c1, *one, "--dry-run")
    rig.check(
        "S1 dry-run gates controls",
        r.returncode == 0 and "controls: PASS" in r.stdout,
        f"rc={r.returncode}",
    )
    r = rig.cli("--plan", str(PLAN), "--campaign-id", c1, *one, "--preflight")
    frozen = rig.manifest(c1).get("identity_map") or {}
    contents = [v.get("content") for v in frozen.values()]
    rig.check(
        "S2 --preflight: the pipeline serves each arm's seat, and its real build is frozen",
        r.returncode == 0 and len(frozen) == 2 and all(contents) and len(set(contents)) == 2,
        f"rc={r.returncode} frozen={ {k: v.get('content', '')[:12] for k, v in frozen.items()} }",
    )
    rcs = [rig.arm(c1, a, *one, timeout=1800) for a in (inc, ch)]
    turns = [
        (row["workspace"], row["arm"].split("@")[0], t.get("served") or {})
        for row in rig.rows(c1)
        for t in row["transcript"]
    ]
    right = all(
        s.get("model") == campaign.seat_primary(ws, a) and s.get("options") for ws, a, s in turns
    )
    rig.check(
        "S3 real rows through ?model=: served by the seat, options recorded",
        rcs == [0, 0] and right and bool(turns),
        f"rcs={rcs} turns={len(turns)} served={sorted({s.get('model') for _, _, s in turns})}",
    )
    vc = rig.cli("--plan", str(PLAN), "--campaign-id", c1, *one, "--verify-complete").returncode
    rep = __import__("subprocess").run(
        [
            __import__("sys").executable,
            "-m",
            "tests.wfe.report",
            "--campaign",
            c1,
            "--out-dir",
            str(rig.tmp),
        ],
        cwd=REPO,
        env=rig.env(),
        capture_output=True,
    )
    rig.check(
        "S4 completion and report",
        vc == 0 and rep.returncode == 0,
        f"verify={vc} report={rep.returncode}",
    )

    missing = rig.tmp / "missing_plan.yaml"
    missing.write_text(
        "workloads:\n  auto-compliance:\n    tool_mode: sandbox\n    home: compliance_agentic_full\n    discovery: []\n"
        "    arms: {incumbent: rig-not-installed-model:latest, challengers: []}\n"
    )
    rc = rig.arm(rig.cid("missing"), "rig-not-installed-model:latest", *one, plan=missing)
    rig.check("S5 (live form) a model that is not installed is blocked", rc == 6, f"rc={rc}")
    rig.offline_only(
        "S6 engine fails mid-arm", "needs a production engine to fail; proven by the fake rig"
    )

    live_identity(rig, c1, inc)
    live_discipline(rig, inc, ch, one, c1)
    live_production(rig)


def live_identity(rig: LiveRig, c1: str, inc: str) -> None:
    """P1R's identity scenarios. I1-I3 rewrite the rig's own checkpoints, so they are
    offline-only here (P1R's live acceptance proved them on production). I4 runs on
    c1's real rows: --record into a scratch ledger, then check HP, then a changed build."""
    why = "rewrites the rig's own checkpoint directories; proven on production by P1R's L1-L4"
    for name in (
        "I1 a rebuild since the freeze blocks the arm",
        "I2 a rebuild mid-arm quarantines the row and stops the arm",
        "I3 a build that cannot be observed blocks the arm",
    ):
        rig.offline_only(name, why)
    led = rig.tmp / "ledger.yaml"
    rec = __import__("subprocess").run(
        [__import__("sys").executable, "-m", "tests.wfe.report", "--campaign", c1, "--record"]
        + ["--ledger", str(led)],
        cwd=REPO,
        env=rig.env(),
        capture_output=True,
        text=True,
    )
    cells = (yaml.safe_load(led.read_text()) or {}).get("cells") or [] if led.exists() else []
    frozen = rig.manifest(c1).get("identity_map") or {}
    recorded = rec.returncode == 0 and len(cells) == 1 and cells[0].get("incumbent") == inc
    recorded = recorded and cells[0].get("served") in frozen.values()
    now = rig.hp(led)
    if cells:
        cells[0]["served"]["content"] = "live-rig-rebuilt"
        led.write_text(yaml.safe_dump({"cells": cells}, sort_keys=False))
    later = rig.hp(led)
    rig.check(
        "I4 (live) --record carries both served identities; check HP covers the seat, then sees a rebuild",
        recorded
        and now.get("subs", [])[:2] == ["PASS", "PASS"]
        and now.get("covered") == ["auto-compliance"]
        and later.get("subs", [None, None])[1] == "WARN",
        f"record={rec.returncode} cells={len(cells)} hp={now.get('subs')} "
        f"covered={now.get('covered')} after_rebuild={later.get('subs')}",
    )


def live_discipline(rig: LiveRig, inc: str, ch: str, one: list[str], c1: str) -> None:
    """S7-S12: drift, SIGTERM and resume, the tool-gap gate, a changed baseline, smoke."""
    # --task selects one id, so S7/S8 use the 3-task rig_short suite (real model, cheap rows).
    short = rig.tmp / "short_plan.yaml"
    short.write_text(
        "workloads:\n  auto-compliance:\n    tool_mode: sandbox\n    home: rig_short\n    discovery: []\n"
        f"    arms: {{incumbent: {inc}, challengers: []}}\n"
    )
    three = ["--repeats", "5"]  # 15 cheap rows: there is always work left after the first
    c7 = rig.cid("drift")

    def drift_after_first_row():
        rig.act_after_first_row(c7, lambda pid: DRIFT_PROBE.write_text("# live rig drift probe\n"))

    rc = rig.arm(c7, inc, *three, plan=short, during=drift_after_first_row, timeout=3600)
    DRIFT_PROBE.unlink(missing_ok=True)
    q = [row for row in rig.rows(c7) if str(row.get("notes", "")).startswith("INSTRUMENT DRIFT")]
    rig.check(
        "S7 drift during a live arm: row quarantined, arm stopped",
        rc == 5 and len(q) == 1,
        f"rc={rc} quarantined={len(q)}",
    )

    c8 = rig.cid("kill")

    def kill_after_first_row():
        rig.act_after_first_row(c8, lambda pid: os.kill(pid, signal.SIGTERM))

    rc1 = rig.arm(c8, inc, *three, plan=short, during=kill_after_first_row, timeout=3600)
    v1 = rig.cli("--plan", str(short), "--campaign-id", c8, *three, "--verify-complete").returncode
    rc2 = rig.arm(c8, inc, *three, plan=short, timeout=3600)
    v2 = rig.cli("--plan", str(short), "--campaign-id", c8, *three, "--verify-complete").returncode
    ids = [row["run_id"] for row in rig.rows(c8)]
    rig.check(
        "S8 SIGTERM a live arm, resume, complete",
        (rc1, v1, rc2, v2) == (143, 8, 0, 0) and len(ids) == len(set(ids)),
        f"kill={rc1} verify={v1} resume={rc2} verify={v2} rows={len(ids)}",
    )

    gap = rig.tmp / "gap_plan.yaml"
    gap.write_text(
        "workloads:\n  auto-compliance:\n    home: compliance_reading_contract\n    discovery: []\n"
        f"    arms: {{incumbent: {inc}, challengers: []}}\n"
    )
    r = rig.cli("--plan", str(gap), "--campaign-id", rig.cid("gap"), "--repeats", "1", "--dry-run")
    rig.check(
        "S9 a task needing tools the row cannot offer is refused",
        r.returncode == 4,
        f"rc={r.returncode}",
    )

    mpath = CAMPAIGNS / c1 / "manifest.json"
    m = json.loads(mpath.read_text())
    m["instrument"] = {**m["instrument"], "deployed": "0" * 40, "fingerprint": "f" * 16}
    mpath.write_text(json.dumps(m, indent=1))
    rc = rig.arm(c1, inc, "--task", "comp-p6j-02", "--repeats", "1", "--append")
    rig.check("S10 resume under a different instrument baseline is refused", rc == 4, f"rc={rc}")
    rig.offline_only(
        "S11 a non-HEAD deployed build", "needs a stale build deployed; proven by the fake rig"
    )

    r = rig.cli(
        "--plan",
        str(PLAN),
        "--smoke",
        "--campaign-id",
        rig.cid("smoke"),
        "--arm",
        ch,
        "--task",
        "comp-p6j-03",
    )
    rig.check("S12 smoke on the live stack", r.returncode == 0, f"rc={r.returncode}")


OPERATOR_COMPLIANCE_DB = Path(
    eval_mode.setting(
        "COMPLIANCE_DB_PATH",
        str(
            REPO / "portal/modules/compliance/data/compliance_store.db"
        ),  # local-only: operator store
    )
)


def operator_compliance_digest() -> str | None:
    """A logical digest of the operator's compliance store: every table's rows, read-only."""
    import hashlib
    import sqlite3

    if not OPERATOR_COMPLIANCE_DB.exists():
        return None
    con = sqlite3.connect(f"file:{OPERATOR_COMPLIANCE_DB}?mode=ro", uri=True)
    h = hashlib.sha256()
    for (t,) in con.execute("select name from sqlite_master where type='table' order by name"):
        h.update(t.encode())
        h.update(repr(sorted(map(repr, con.execute(f'select * from "{t}"')))).encode())
    con.close()
    return h.hexdigest()[:16]


def live_compliance(rig: LiveRig, plan: Path) -> None:
    """S19: an auto-compliance row in production mode is served by the evaluation instance."""

    def served() -> int:
        try:
            with urllib.request.urlopen(f"{eval_mode.COMPLIANCE_EVAL_URL}/health", timeout=5) as r:
                return int(json.load(r).get("eval_tool_calls", -1))
        except Exception:  # noqa: BLE001
            return -1

    c, before = rig.cid("auto-compliance"), served()
    rc = rig.arm(
        c,
        _seat("auto-compliance"),
        "--workspace",
        "auto-compliance",
        "--task",
        "rig-comp-01",
        "--repeats",
        "1",
        plan=plan,
        timeout=1800,
    )
    row = (rig.rows(c) or [{}])[0]
    ev, after = row.get("evidence") or {}, served()
    calls = sum((t.get("served") or {}) != {} for t in row.get("transcript") or [])
    # Positive evidence: the evaluation instance served this row's call. "Unchanged" would also
    # be true if the model never called a compliance tool, which proves nothing about routing.
    ok = rc == 0 and ev.get("tool_mode") == "production" and before >= 0 and after > before
    rig.check(
        f"S19 auto-compliance in production mode (outcome {row.get('outcome')})",
        ok,
        f"rc={rc} mode={ev.get('tool_mode')} eval_instance_calls {before}->{after} turns={calls}",
    )


def _root_files() -> set[str]:
    return {str(p) for p in eval_mode.OUTPUT_ROOT.glob("*") if p.is_file()}


def live_production(rig: LiveRig) -> None:
    plan = rig.tmp / "prod_plan.yaml"
    plan.write_text(
        "workloads:\n"
        + "".join(
            f"  {ws}:\n    home: rig_production\n    discovery: []\n    arms: {{incumbent: {_seat(ws)}, challengers: []}}\n"
            for ws in (
                "auto-documents",
                "auto-research::data",
                "auto-research",
                "auto-compliance",
            )
        )
    )
    sess = Path(
        eval_mode.setting("DATA_MCP_SESSIONS", str(Path.home() / ".portal-data" / "sessions"))
    )
    before_root, before_sess = _root_files(), {p.name for p in sess.glob("*.duckdb")}
    for name, ws, task in (
        ("S13 documents", "auto-documents", "rig-doc-01"),
        ("S14 data", "auto-research::data", "rig-data-01"),
        ("S17 research (KB + memory seeds)", "auto-research", "rig-kb-01"),
    ):
        c = rig.cid(ws)
        kbs_before = {
            k["kb_id"] for k in rig.mcp("rag", "/tools/kb_list", {}).get("knowledge_bases", [])
        }
        rc = rig.arm(
            c,
            _seat(ws),
            "--workspace",
            ws,
            "--task",
            task,
            "--repeats",
            "1",
            plan=plan,
            timeout=1800,
        )
        row = (rig.rows(c) or [{}])[0]
        ev = row.get("evidence") or {}
        scope = ev.get("eval_scope") or {}
        kbs_after = {
            k["kb_id"] for k in rig.mcp("rag", "/tools/kb_list", {}).get("knowledge_bases", [])
        }
        mem_left = (
            rig.mcp("memory", "/tools/list_memories", {"arguments": {}, "eval": scope}).get(
                "memories"
            )
            or []
        )
        ok = (
            rc == 0
            and ev.get("tool_mode") == "production"
            and all(r.get("valid") is True for r in ev.get("receipts") or [])
            and "fixture seeding failed" not in str(row.get("notes"))
            and kbs_after == kbs_before
            and not mem_left
        )
        rig.check(
            f"{name} in production mode on a real model (outcome {row.get('outcome')})",
            ok,
            f"rc={rc} mode={ev.get('tool_mode')} receipts={[r.get('valid') for r in ev.get('receipts') or []]} "
            f"kb_list_unchanged={kbs_after == kbs_before} run_memories_left={len(mem_left)}",
        )
    left = (_root_files() - before_root) | ({p.name for p in sess.glob("*.duckdb")} - before_sess)
    rig.check(
        "S13-14 nothing published, orphaned or left in data sessions",
        not left,
        f"left={sorted(left)}",
    )

    live_compliance(rig, plan)
    live_no_leak(rig)
    live_memory(rig)


def live_no_leak(rig: LiveRig) -> None:
    """S15: on one connection, a scoped request then an unscoped one (production's trace)."""
    conn = http.client.HTTPConnection("localhost", int(PIPE.rsplit(":", 1)[-1]), timeout=600)
    traces = []
    for extra in ({"portal_eval": {**SCOPE_ALL, "allow": ["run_sql"]}}, {}):
        cid = f"wfe-live-{uuid.uuid4().hex[:12]}"
        body = {
            "model": "auto-research::data",
            "stream": False,
            "messages": [{"role": "user", "content": "total?"}],
            **extra,
        }
        conn.request(
            "POST",
            "/v1/chat/completions",
            json.dumps(body),
            {
                "Authorization": f"Bearer {rig.key}",
                "Content-Type": "application/json",
                "X-Correlation-ID": cid,
            },
        )
        conn.getresponse().read()
        time.sleep(1)
        traces.append(rig._req(f"{PIPE}/v1/trace/{cid}", auth=True))
    conn.close()
    ok = (
        traces[0].get("tools_offered") == ["run_sql"]
        and traces[0].get("eval")
        and not traces[1].get("eval")
        and len(traces[1].get("tools_offered") or []) > 1
    )
    rig.check(
        "S15 a scope does not outlive its request (same connection)",
        bool(ok),
        f"offered={[t.get('tools_offered') for t in traces]}",
    )


def live_memory(rig: LiveRig) -> None:
    marker = f"WFE live check: the orchid code is ORCHID-{uuid.uuid4().hex[:6]}"
    mid = rig.mcp(
        "memory", "/tools/remember", {"arguments": {"text": marker, "category": "fact"}}
    ).get("id")
    try:
        _, op = rig.chat("general-fast", "What is the orchid code from the WFE live check?")
        _, scoped = rig.chat(
            "general-fast",
            "What is the orchid code from the WFE live check?",
            {**SCOPE_ALL, "run": "wfe_" + uuid.uuid4().hex[:40].ljust(40, "0")},
        )
        ok = (op.get("memory_injected") or 0) >= 1 and (scoped.get("memory_injected") or 0) == 0
        rig.check(
            "S16 the operator's memory reaches an unscoped prompt and never a scoped one",
            ok,
            f"unscoped={op.get('memory_injected')} scoped={scoped.get('memory_injected')}",
        )
    finally:
        if mid:
            rig.mcp("memory", "/tools/forget", {"arguments": {"id": mid}})
        gone = marker not in json.dumps(
            rig.mcp("memory", "/tools/list_memories", {"arguments": {}})
        )
        rig.check(
            "S16 cleanup: the marker memory is gone from the operator's store",
            bool(mid) and gone,
            f"id={mid}",
        )

    token = f"TULIP-{uuid.uuid4().hex[:6]}"
    scope = {**SCOPE_ALL, "run": "wfe_" + uuid.uuid4().hex[:40].ljust(40, "0")}
    rig.chat(
        "general-fast", f"Please remember that the WFE live write-back token is {token}.", scope
    )
    found = False
    for _ in range(15):
        found = token in json.dumps(
            rig.mcp("memory", "/tools/list_memories", {"arguments": {}, "eval": scope})
        )
        if found:
            break
        time.sleep(1)
    in_operator = token in json.dumps(rig.mcp("memory", "/tools/list_memories", {"arguments": {}}))
    rig.mcp("memory", "/eval/forget_scope", {"eval": scope})
    rig.check(
        "S18 write-back lands in the run's memory, never the operator's",
        found and not in_operator,
        f"in_run={found} in_operator={in_operator}",
    )
