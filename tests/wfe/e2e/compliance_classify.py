"""Re-measure which compliance tools are safe for the evaluation instance (root-fix Part 2c-2).

    uv run python -m tests.wfe.e2e.compliance_classify [--workers 4] [--json OUT]

Builds a pristine evaluation store from public material only (eval_instance build), then for
every compliance tool: a fresh process on a fresh copy of that store, with the module's model
endpoints (PIPELINE_BASE, OLLAMA_BASE) pointed at a trap that records and refuses every request,
waiting for the store to go quiet before and after the call; then a store warmed by every other
candidate, to see whether the tool's answer depends on earlier calls. Exits 1 if any tool in
eval_instance.VERIFIED_TOOLS now calls a model, changes the store, errors, or depends on history.
Embeddings come from the live EmbeddingGemma (EG2_EMBEDDING_URL / VL_RETRIEVAL_URL).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
VAL = {
    "standard": "CIP-007-6",
    "requirement": "R2",
    "req_id": "CIP-007-6 R2 Part 2.1",
    "part": "2.1",
    "query": "patch management",
    "control_id": "AC-2",
    "framework": "nist_800_53",
    "kb_id": "operator_corpus",
    "cve_id": "CVE-2024-3094",
    "question": "What does CIP-007-6 R2 Part 2.1 require?",
    "text": "test note",
    "topic": "patching",
    "scope_text": "High impact BES",
    "source_frameworks": ["nist_800_53"],
    "target_framework": "csf_2_0",
    "keyword": "patch",
    "address": "CIP-007-6 R2 Part 2.1",
    "ref": "CIP-007-6 R2 Part 2.1",
    "requirement_id": "CIP-007-6 R2 Part 2.1",
    "start_ref": "CIP-007-6 R2 Part 2.1",
    "subject_ref": "CIP-007-6 R2 Part 2.1",
    "body": "t",
    "internal_text": "We evaluate security patches every 35 days.",
    "requirements": ["CIP-007-6 R2 Part 2.1"],
    "old_standard": "CIP-007-5",
    "new_standard": "CIP-007-6",
    "target": "CIP-007-6 R2 Part 2.1",
    "name": "CIP-007-6",
}
VOLATILE = [
    (re.compile(r"\d{4}-\d{2}-\d{2}T[\d:.+Z-]+"), "<ts>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<uuid>"),
    (re.compile(r"\b[0-9a-f]{16,64}\b"), "<hex>"),
    (re.compile(r'"(elapsed|duration|took)[a-z_]*": [\d.]+'), r'"\1": <n>'),
]


def _items(store: Path) -> dict[str, str]:
    """Logical state: each SQLite table's rows and each other file (WAL/SHM/locks excluded;
    LanceDB counted by presence, since its index files churn without a content change)."""
    out: dict[str, str] = {}
    for p in sorted(store.rglob("*")):
        if not p.is_file() or p.name.endswith(("-wal", "-shm", ".lock")):
            continue
        if p.suffix == ".db":
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            for (t,) in con.execute("select name from sqlite_master where type='table'"):
                rows = sorted(map(repr, con.execute(f'select * from "{t}"')))
                out[f"db:{t}"] = hashlib.sha256(repr(rows).encode()).hexdigest()[:12]
            con.close()
        elif "lance" not in p.parts:
            out[str(p.relative_to(store))] = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    return out


def _quiet(store: Path, timeout: float = 60) -> dict[str, str]:
    prev: dict[str, str] | None = None
    end = time.time() + timeout
    while time.time() < end:
        cur = _items(store)
        if cur == prev:
            return cur
        prev = cur
        time.sleep(1.5)
    return prev or {}


def _norm(x: object) -> str:
    s = json.dumps(x, sort_keys=True, default=str)
    for rx, rep in VOLATILE:
        s = rx.sub(rep, s)
    return s


class _Trap(BaseHTTPRequestHandler):
    hits = 0

    def _refuse(self) -> None:
        type(self).hits += 1
        self.send_response(503)
        self.end_headers()

    do_GET = do_POST = _refuse  # noqa: N815 — BaseHTTPRequestHandler's names

    def log_message(self, *a: object) -> None:
        pass


def run_one(store: Path, calls: list) -> list[dict]:
    """In THIS process: point model endpoints at a trap, then call each tool and observe."""
    trap = HTTPServer(("127.0.0.1", 0), _Trap)
    threading.Thread(target=trap.serve_forever, daemon=True).start()
    os.environ["PIPELINE_BASE"] = f"http://127.0.0.1:{trap.server_port}"
    os.environ["OLLAMA_BASE"] = f"http://127.0.0.1:{trap.server_port}/ollama"
    from portal.modules.compliance.tools import compliance_mcp as cm

    out = []
    for name, args in calls:
        before, hits = _quiet(store), _Trap.hits
        try:
            res = cm._DISPATCH[name](**args)
        except Exception as e:  # noqa: BLE001
            res = {"raised": f"{type(e).__name__}: {e}"}
        after = _quiet(store)
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        out.append(
            {"tool": name, "out": _norm(res), "model_calls": _Trap.hits - hits, "changed": changed}
        )
    return out


def _spawn(store: Path, calls: list, pristine: Path) -> list[dict]:
    from portal.modules.compliance.core.eval_instance import env_for

    shutil.rmtree(store, ignore_errors=True)
    shutil.copytree(pristine, store)
    (store / "calls.json").write_text(json.dumps(calls))
    env = {**os.environ, **env_for(store), "PYTHONPATH": str(REPO)}
    p = subprocess.run(
        [sys.executable, "-m", "tests.wfe.e2e.compliance_classify", "--run-one", str(store)],
        env=env,
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=3600,
    )
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith("[")]
    if not lines:
        return [
            {
                "tool": c[0],
                "out": "RUNNER FAILED: " + p.stderr[-300:],
                "model_calls": -1,
                "changed": [],
            }
            for c in calls
        ]
    return json.loads(lines[-1])


def _calls(names: set[str] | None = None) -> list:
    manifest = json.loads(
        (REPO / "config/inference/tools_manifest_compliance_mcp.json").read_text()
    )
    calls = []
    for t in (m.get("function", m) for m in manifest):
        if t["name"] in ("compliance_ingest", "refresh_catalogs") or (
            names and t["name"] not in names
        ):
            continue
        params = t.get("parameters") or {}
        if all(r in VAL for r in params.get("required") or []):
            calls.append(
                [t["name"], {k: VAL[k] for k in params.get("properties") or {} if k in VAL}]
            )
    return calls


def classify(workers: int) -> list[dict]:
    from portal.modules.compliance.core.eval_instance import env_for

    work = Path(tempfile.mkdtemp(prefix="compliance-classify-"))
    pristine = work / "pristine"
    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "portal.modules.compliance.core.eval_instance",
            "build",
            "--root",
            str(pristine),
        ],
        env={**os.environ, **env_for(pristine), "PYTHONPATH": str(REPO)},
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if build.returncode:
        raise SystemExit(f"could not build the pristine store: {build.stderr[-500:]}")
    calls = _calls()
    with ThreadPoolExecutor(workers) as ex:
        fresh = {
            c[0]: r[0]
            for c, r in zip(
                calls,
                ex.map(lambda c: _spawn(work / f"f_{c[0]}", [c], pristine), calls),
                strict=True,
            )
        }
    candidates = [
        c
        for c in calls
        if not fresh[c[0]]["changed"]
        and fresh[c[0]]["model_calls"] == 0
        and "raised" not in fresh[c[0]]["out"]
        and '"error"' not in fresh[c[0]]["out"]
    ]
    warm = {
        r["tool"]: r
        for r in _spawn(work / "warm", candidates + candidates, pristine)[len(candidates) :]
    }
    rows = []
    for c in calls:
        f, w = fresh[c[0]], warm.get(c[0])
        err = "raised" in f["out"] or '"error"' in f["out"]
        rows.append(
            {
                "tool": c[0],
                "model_calls": f["model_calls"],
                "changed": f["changed"],
                "error": err,
                "independent": (w is not None and w["out"] == f["out"]) if not err else None,
            }
        )
    shutil.rmtree(work, ignore_errors=True)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-one", help=argparse.SUPPRESS)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json", help="write the classification here")
    a = ap.parse_args(argv)
    if a.run_one:
        store = Path(a.run_one)
        print(json.dumps(run_one(store, json.loads((store / "calls.json").read_text()))))
        return 0
    from portal.modules.compliance.core.eval_instance import VERIFIED_TOOLS

    rows = classify(a.workers)
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1))
    bad = []
    for r in rows:
        safe = r["model_calls"] == 0 and not r["changed"] and not r["error"] and r["independent"]
        mark = "VERIFIED" if r["tool"] in VERIFIED_TOOLS else "        "
        print(
            f"{mark} {r['tool']:30} calls={r['model_calls']} changed={','.join(r['changed']) or '-'} "
            f"error={r['error']} independent={r['independent']} -> {'safe' if safe else 'NOT SAFE'}"
        )
        if r["tool"] in VERIFIED_TOOLS and not safe:
            bad.append(r["tool"])
    missing = sorted(VERIFIED_TOOLS - {r["tool"] for r in rows})
    print(
        f"\nclassify: {len(rows)} tools; verified-but-not-safe: {bad or 'none'}; verified-but-unmeasured: {missing or 'none'}"
    )
    return 1 if bad or missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
