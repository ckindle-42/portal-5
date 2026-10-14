"""WFE end-to-end rig: the REAL pipeline app, fake engines, the real harness CLI.

    uv run python -m tests.wfe.e2e.rig [--keep] [--ports 21434,28085,29099]

Starts fake Ollama and oMLX and the pipeline on their own ports (refusing ports in
use, so no live service is touched), runs sixteen scenarios through
tests/wfe/run_arm.py, asserts each one's exit code and evidence, writes a JSON
receipt and exits 0 only if every scenario passed. The fake oMLX models get
checkpoint directories of their own (OMLX_MODEL_DIR), so identity is observed the
way production observes it, and the I scenarios change them on purpose. Rig campaigns (`rig_*`) are
deleted afterwards unless --keep.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import yaml

from tests.wfe.campaign import SEAT_BLOCK

REPO = Path(__file__).resolve().parents[3]
PLAN = REPO / "tests/wfe/plans/decision_run_v1.yaml"
INC = "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k"
CH = "granite4.1:30b-ctx64k"
SERVED = {INC: "Qwen3.8-27B-oQ4e-mtp", CH: "granite-4.1-30b-4bit"}
CAMPAIGNS = REPO / "tests/wfe/results/campaigns"
DRIFT_PROBE = REPO / "tests/wfe/_rig_drift_probe.py"


class Rig:
    def __init__(self, ports: tuple[int, int, int], keep: bool):
        self.ol, self.om, self.pp = ports
        self.keep = keep
        self.tmp = Path(tempfile.mkdtemp(prefix="wfe-rig-"))
        self.procs: dict[str, subprocess.Popen] = {}
        self.stamp = str(int(time.time()))
        self.campaigns: list[str] = []
        self.results: list[dict] = []
        self.head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
        ).stdout.strip()
        # A checkpoint for every model the fake oMLX serves, as fake_engines lists them,
        # so the build behind any workspace's seat is observable, as in production.
        self.omlx = self.tmp / "omlx-models"
        backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())["backends"]
        omlx_ids = {
            m["id"] if isinstance(m, dict) else m
            for b in backends
            if b["type"] != "ollama"
            for m in [*(b.get("models") or []), *(b.get("aliases") or {}).values()]
        }
        for served in sorted(omlx_ids | set(SERVED.values())):
            d = self.omlx / served
            d.mkdir(parents=True)
            (d / "config.json").write_text(json.dumps({"model": served, "quant": 4}))
            (d / "tokenizer_config.json").write_text("{}")
            (d / "model.safetensors").write_bytes(served.encode() * 8)
        (self.tmp / "model_settings.json").write_text('{"models": {}}')

    # ── services ────────────────────────────────────────────────────────────
    def _free(self, port: int) -> bool:
        with socket.socket() as s:
            return s.connect_ex(("127.0.0.1", port)) != 0

    def start_fakes(self) -> None:
        cmd = [
            sys.executable,
            "-m",
            "tests.wfe.e2e.fake_engines",
            str(REPO / "config/backends.yaml"),
            str(self.ol),
            str(self.om),
            str(self.tmp),
        ]
        self.procs["fakes"] = subprocess.Popen(
            cmd, cwd=REPO, stdout=open(self.tmp / "fakes.out", "w"), stderr=subprocess.STDOUT
        )
        self._wait(f"http://127.0.0.1:{self.om}/health")

    def start_pipeline(self, build: str) -> None:
        self.stop("pipeline")
        env = {
            **os.environ,
            "PIPELINE_API_KEY": "rig-key",
            "OLLAMA_URL": f"http://127.0.0.1:{self.ol}",
            "OMLX_URL": f"http://127.0.0.1:{self.om}",
            "LOAD_GUARD_WAIT_S": "5",
            "PORTAL_BUILD_SHA": build,
            "PORTAL_TRACE_DIR": str(self.tmp / "traces"),
        }
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "portal.platform.inference.router.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.pp),
        ]
        self.procs["pipeline"] = subprocess.Popen(
            cmd,
            cwd=REPO,
            env=env,
            stdout=open(self.tmp / "pipeline.out", "a"),
            stderr=subprocess.STDOUT,
        )
        self._wait(f"http://127.0.0.1:{self.pp}/health")

    def _wait(self, url: str, timeout: float = 90) -> None:
        end = time.time() + timeout
        while time.time() < end:
            try:
                with urllib.request.urlopen(url, timeout=2):
                    return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError(f"rig: {url} did not come up; see {self.tmp}")

    def stop(self, name: str) -> None:
        p = self.procs.pop(name, None)
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()

    # ── harness ─────────────────────────────────────────────────────────────
    def env(self) -> dict:
        return {
            **os.environ,
            "WFE_ENGINE": "pipeline",
            "PIPELINE_API_KEY": "rig-key",
            "WFE_CHAT_BASE_URL": f"http://127.0.0.1:{self.pp}",
            "WFE_OLLAMA_URL": f"http://127.0.0.1:{self.ol}",
            "WFE_OMLX_URL": f"http://127.0.0.1:{self.om}",
            "WFE_ALLOW_DIRTY_INSTRUMENT": "1",
            "OMLX_MODEL_DIR": str(self.omlx),
            "OMLX_SETTINGS": str(self.tmp / "model_settings.json"),
        }

    def cid(self, n: str) -> str:
        c = f"rig_{self.stamp}_{n}"
        self.campaigns.append(c)
        return c

    def cli(self, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "tests.wfe.campaign", *args],
            cwd=REPO,
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def arm(
        self,
        campaign: str,
        arm: str,
        *extra: str,
        plan: Path = PLAN,
        timeout: int = 300,
        during=None,
    ) -> int:
        log = CAMPAIGNS / campaign / "arm_exits.log"
        cmd = [
            sys.executable,
            "-m",
            "tests.wfe.run_arm",
            "--pid-file",
            str(self.tmp / "pids"),
            "--exit-log",
            str(log),
            "--label",
            arm,
            "--",
            "--plan",
            str(plan),
            "--campaign-id",
            campaign,
            "--arm",
            arm,
            *extra,
        ]
        p = subprocess.Popen(
            cmd,
            cwd=REPO,
            env=self.env(),
            stdout=open(self.tmp / f"{campaign}.out", "a"),
            stderr=subprocess.STDOUT,
        )
        if during:
            during()
        return p.wait(timeout)

    def manifest(self, campaign: str) -> dict:
        return json.loads((CAMPAIGNS / campaign / "manifest.json").read_text())

    def rebuild(self, served: str, body: str = '{"rebuilt": true}') -> str:
        """Change a fake checkpoint the way a re-quantization would; returns the old config."""
        cfg = self.omlx / served / "config.json"
        old = cfg.read_text()
        cfg.write_text(body)
        return old

    def hp(self, ledger: Path) -> dict:
        """Check HP, run as the validator runs it, against a scratch ledger."""
        code = (
            "import json; from scripts.validation import wfe as hp\n"
            "s, d, subs = hp.check_wfe_fitness_ledger()\n"
            "cov = {(str(c.get('workspace')), str(c.get(k))) for c in hp._cells()"
            " for k in ('model', 'incumbent')}\n"
            "print(json.dumps({'status': s, 'subs': [x['status'] for x in subs],"
            " 'stale': subs[1]['detail'],"
            " 'covered': [w for w, m in hp._seats().items() if (w, m) in cov]}))"
        )
        out = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO,
            env={**self.env(), "WFE_FITNESS_LEDGER": str(ledger)},
            capture_output=True,
            text=True,
        )
        return json.loads(out.stdout.strip().splitlines()[-1]) if out.returncode == 0 else {}

    def rows(self, campaign: str) -> list[dict]:
        return [json.loads(f.read_text()) for f in (CAMPAIGNS / campaign / "rows").glob("*.json")]

    def engine_calls(self, since: int = 0) -> list[dict]:
        lines = (self.tmp / "engine.log").read_text().splitlines()[since:]
        return [json.loads(x) for x in lines if '"path"' in x and "chat" in x]

    def mark(self) -> int:
        return len((self.tmp / "engine.log").read_text().splitlines())

    def check(self, name: str, ok: bool, evidence: str) -> None:
        self.results.append(
            {"scenario": name, "status": "PASS" if ok else "FAIL", "evidence": evidence}
        )
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {evidence}", flush=True)

    # ── scenarios ───────────────────────────────────────────────────────────
    def run(self) -> int:
        for port in (self.ol, self.om, self.pp):
            if not self._free(port):
                raise SystemExit(f"rig: port {port} is in use; pass --ports to use free ones")
        (self.tmp / "pids").write_text("")
        try:
            self.start_fakes()
            self.start_pipeline(self.head)
            self.scenarios()
        finally:
            DRIFT_PROBE.unlink(missing_ok=True)
            for name in list(self.procs):
                self.stop(name)
            if not self.keep:
                for c in self.campaigns:
                    shutil.rmtree(CAMPAIGNS / c, ignore_errors=True)
        receipt = {
            "head": self.head,
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "results": self.results,
            "workdir": str(self.tmp),
        }
        (self.tmp / "receipt.json").write_text(json.dumps(receipt, indent=1))
        failed = [r for r in self.results if r["status"] != "PASS"]
        print(
            f"\nrig: {len(self.results) - len(failed)}/{len(self.results)} PASS; receipt {self.tmp}/receipt.json"
        )
        return 1 if failed or len(self.results) < 16 else 0

    def scenarios(self) -> None:
        self.happy_path()
        self.identity()
        self.failures()
        self.gates_and_builds()

    def happy_path(self) -> None:
        self.two = two = ["--task", "comp-p6j-01", "--repeats", "1"]
        self.c1 = c1 = self.cid("main")
        r = self.cli("--plan", str(PLAN), "--campaign-id", c1, *two, "--dry-run")
        self.check(
            "S1 dry-run gates controls",
            r.returncode == 0 and "controls: PASS" in r.stdout,
            f"rc={r.returncode}",
        )

        m = self.mark()
        r = self.cli("--plan", str(PLAN), "--campaign-id", c1, *two, "--preflight")
        models = {c["model"] for c in self.engine_calls(m)}
        frozen = self.manifest(c1).get("identity_map") or {}
        contents = [v.get("content") for v in frozen.values()]
        self.check(
            "S2 --preflight asks the pipeline what it serves, and freezes what serves it",
            r.returncode == 0
            and models <= set(SERVED.values())
            and set(frozen) == {f"auto-compliance|{INC}", f"auto-compliance|{CH}"}
            and all(contents)
            and len(set(contents)) == 2,
            f"rc={r.returncode} served={sorted(models)} frozen={sorted(frozen)}",
        )

        rcs = [self.arm(c1, a, *two) for a in (INC, CH)]
        rows = self.rows(c1)
        turns = [
            (row["arm"].split("@")[0], t.get("served") or {})
            for row in rows
            for t in row["transcript"]
        ]
        right = all(s.get("model") == SERVED[a] and s.get("options") for a, s in turns)
        self.check(
            "S3 rows served through ?model=, options recorded",
            rcs == [0, 0] and right and turns,
            f"rcs={rcs} turns={len(turns)}",
        )

        vc = self.cli("--plan", str(PLAN), "--campaign-id", c1, *two, "--verify-complete")
        rep = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.wfe.report",
                "--campaign",
                c1,
                "--out-dir",
                str(self.tmp),
            ],
            cwd=REPO,
            env=self.env(),
            capture_output=True,
            text=True,
        )
        self.check(
            "S4 completion and report",
            vc.returncode == 0 and rep.returncode == 0,
            f"verify={vc.returncode} report={rep.returncode}",
        )

    def identity(self) -> None:
        """Identity is observed in the engine's store, frozen at preflight, checked
        at every arm start and after every row, and carried into the ledger, where
        check HP compares it with what production serves now (doc: identity)."""
        self.identity_at_arm_start()
        self.identity_mid_arm()
        self.identity_unobservable()
        self.identity_in_the_ledger()

    def identity_at_arm_start(self) -> None:
        two = self.two
        c = self.cid("rebuilt")
        self.cli("--plan", str(PLAN), "--campaign-id", c, *two, "--preflight")
        old = self.rebuild(SERVED[CH])
        try:
            rc = self.arm(c, CH, *two)
        finally:
            self.rebuild(SERVED[CH], old)
        notes = [r.get("note", "") for r in self.manifest(c)["rows"] if r.get("model") == CH]
        self.check(
            "I1 a rebuild since the freeze blocks the arm",
            rc == 6 and notes and all("IDENTITY DRIFT" in n for n in notes),
            f"rc={rc} notes={[n[:60] for n in notes]}",
        )

    def identity_mid_arm(self) -> None:
        c = self.cid("midrebuild")
        rows_dir = CAMPAIGNS / c / "rows"
        saved: dict = {}

        def rebuild_after_first_row():
            end = time.time() + 240
            while time.time() < end and not (rows_dir.exists() and any(rows_dir.glob("*.json"))):
                time.sleep(0.2)
            saved["old"] = self.rebuild(SERVED[INC])

        try:
            rc = self.arm(c, INC, "--repeats", "1", during=rebuild_after_first_row, timeout=600)
        finally:
            if "old" in saved:
                self.rebuild(SERVED[INC], saved["old"])
        q = [r for r in self.rows(c) if str(r.get("notes", "")).startswith("IDENTITY DRIFT")]
        self.check(
            "I2 a rebuild mid-arm quarantines the row and stops the arm",
            rc == 5 and len(q) == 1,
            f"rc={rc} quarantined={len(q)} rows={len(self.rows(c))}",
        )

    def identity_unobservable(self) -> None:
        c = self.cid("unobservable")
        two = self.two
        home, away = self.omlx / SERVED[INC], self.tmp / "moved-away"
        home.rename(away)
        try:
            rc = self.arm(c, INC, *two)
        finally:
            away.rename(home)
        notes = [r.get("note", "") for r in self.manifest(c)["rows"]]
        self.check(
            "I3 a build that cannot be observed blocks the arm",
            rc == 6 and notes and all("cannot be observed" in n for n in notes),
            f"rc={rc} notes={[n[:60] for n in notes]}",
        )

    def identity_in_the_ledger(self) -> None:
        led = self.tmp / "ledger.yaml"
        rec = subprocess.run(
            [sys.executable, "-m", "tests.wfe.report", "--campaign", self.c1, "--record"]
            + ["--ledger", str(led)],
            cwd=REPO,
            env=self.env(),
            capture_output=True,
            text=True,
        )
        cells = (yaml.safe_load(led.read_text()) or {}).get("cells") if led.exists() else []
        frozen = self.manifest(self.c1).get("identity_map") or {}
        recorded = (
            rec.returncode == 0
            and len(cells) == 1
            and cells[0].get("incumbent") == INC
            and cells[0].get("served") == frozen.get(f"auto-compliance|{CH}")
            and cells[0].get("incumbent_served") == frozen.get(f"auto-compliance|{INC}")
        )
        now = self.hp(led)
        old = self.rebuild(SERVED[CH])
        try:
            later = self.hp(led)
        finally:
            self.rebuild(SERVED[CH], old)
        self.check(
            "I4 --record carries both served identities; check HP covers the seat, then sees a rebuild",
            recorded
            and now.get("subs", [])[:2] == ["PASS", "PASS"]
            and now.get("covered") == ["auto-compliance"]
            and later.get("subs", [None, None])[1] == "WARN"
            and "rebuilt" in later.get("stale", ""),
            f"record={rec.returncode} cells={len(cells or [])} hp={now.get('subs')} "
            f"covered={now.get('covered')} after_rebuild={later.get('subs')}",
        )

    def failures(self) -> None:
        two = self.two
        c5 = self.cid("down")
        (self.tmp / "fail_omlx").touch()
        rc = self.arm(c5, INC, *two)
        (self.tmp / "fail_omlx").unlink()
        self.check("S5 engine down for a whole arm -> blocked", rc == 6, f"rc={rc}")

        c6 = self.cid("midfail")

        def fail_later():
            time.sleep(4)
            (self.tmp / "fail_omlx").touch()

        rc = self.arm(c6, INC, "--repeats", "1", during=fail_later, timeout=600)
        (self.tmp / "fail_omlx").unlink(missing_ok=True)
        errs = sum(1 for row in self.rows(c6) if row["outcome"] == "HARNESS_ERROR")
        seat = sum(1 for row in self.rows(c6) if str(row.get("notes", "")).startswith(SEAT_BLOCK))
        self.check(
            "S6 engine fails mid-arm -> arm stops (3 instrument errors, or a failover blocked)",
            rc == 5 and (errs >= 3 or seat >= 1),
            f"rc={rc} harness_errors={errs} failover_blocked={seat}",
        )

        c7 = self.cid("drift")

        def drift_later():
            time.sleep(4)
            DRIFT_PROBE.write_text("# rig drift probe\n")

        rc = self.arm(c7, INC, "--repeats", "1", during=drift_later)
        DRIFT_PROBE.unlink(missing_ok=True)
        q = [
            row for row in self.rows(c7) if str(row.get("notes", "")).startswith("INSTRUMENT DRIFT")
        ]
        self.check(
            "S7 instrument drift mid-arm -> row quarantined, arm stopped",
            rc == 5 and len(q) == 1,
            f"rc={rc} quarantined={len(q)}",
        )

        c8 = self.cid("kill")
        pids = self.tmp / "pids"

        def kill_later():
            time.sleep(4)
            os.kill(int(pids.read_text().split()[-1]), signal.SIGTERM)

        rc1 = self.arm(c8, INC, "--repeats", "1", during=kill_later)
        v1 = self.cli(
            "--plan", str(PLAN), "--campaign-id", c8, "--repeats", "1", "--verify-complete"
        ).returncode
        rc2 = self.arm(c8, INC, "--repeats", "1")
        v2 = self.cli(
            "--plan", str(PLAN), "--campaign-id", c8, "--repeats", "1", "--verify-complete"
        ).returncode
        rows = self.rows(c8)
        self.check(
            "S8 SIGTERM, resume, complete with no lost or duplicate rows",
            (rc1, v1, rc2, v2) == (143, 8, 0, 0) and len(rows) == len({r["run_id"] for r in rows}),
            f"kill={rc1} verify={v1} resume={rc2} verify={v2} rows={len(rows)}",
        )

    def gates_and_builds(self) -> None:
        two, c1 = self.two, self.c1
        gap = self.tmp / "gap_plan.yaml"
        gap.write_text(
            "workloads:\n  auto-compliance:\n    home: compliance_reading_contract\n"
            f"    discovery: []\n    arms:\n      incumbent: {INC}\n      challengers: []\n"
        )
        r = self.cli(
            "--plan", str(gap), "--campaign-id", self.cid("gap"), "--repeats", "1", "--dry-run"
        )
        self.check(
            "S9 a task needing tools the row cannot offer is refused",
            r.returncode == 4 and "needs tools not offered" in r.stdout,
            f"rc={r.returncode}",
        )

        self.start_pipeline("0" * 40)
        rc = self.arm(c1, INC, "--task", "comp-p6j-02", "--repeats", "1", "--append")
        self.check("S10 resume under a different deployed build is refused", rc == 4, f"rc={rc}")
        rc = self.arm(self.cid("stale"), INC, *two)
        self.check("S11 a new campaign under a non-HEAD build is blocked", rc == 6, f"rc={rc}")
        self.start_pipeline(self.head)

        m = self.mark()
        r = self.cli(
            "--plan",
            str(PLAN),
            "--smoke",
            "--campaign-id",
            self.cid("smoke"),
            "--arm",
            CH,
            "--task",
            "comp-p6j-03",
        )
        models = {c["model"] for c in self.engine_calls(m)}
        self.check(
            "S12 smoke serves the challenger",
            r.returncode == 0 and models == {SERVED[CH]},
            f"rc={r.returncode} served={sorted(models)}",
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keep", action="store_true", help="keep rig campaigns and logs")
    ap.add_argument("--ports", default="21434,28085,29099", help="fake Ollama, fake oMLX, pipeline")
    a = ap.parse_args()
    ports = tuple(int(p) for p in a.ports.split(","))
    return Rig(ports, a.keep).run()


if __name__ == "__main__":
    raise SystemExit(main())
