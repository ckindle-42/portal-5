"""WFE end-to-end rig: the REAL pipeline app, fake engines, the real harness CLI.

    uv run python -m tests.wfe.e2e.rig [--keep] [--ports 21434,28085,29099]

Starts fake Ollama and oMLX and the pipeline on their own ports (refusing ports in
use, so no live service is touched), runs twelve scenarios through
tests/wfe/run_arm.py, asserts each one's exit code and evidence, writes a JSON
receipt and exits 0 only if every scenario passed. Rig campaigns (`rig_*`) are
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
        return 1 if failed or len(self.results) < 12 else 0

    def scenarios(self) -> None:
        self.happy_path()
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
        self.check(
            "S2 --preflight asks the pipeline what it serves",
            r.returncode == 0 and models <= set(SERVED.values()),
            f"rc={r.returncode} served={sorted(models)}",
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
