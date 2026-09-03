"""RAG/VL runtime gates (TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 D3).

`validate_system.py` is the pre-bench gate and the v9 acceptance path. Before
this it had no VL-server check, no LanceDB mount check, and no venv/lock drift
check — so a bench run or acceptance sweep passed green with retrieval down, the
same blind spot that let T9 ship a non-loading model. These three checks shell
out to the same primitives the runtime and the pytest gates use, so there is one
implementation with two entry points.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request

from ._shared import REPO_ROOT
from .registry import register


@register("vl_retrieval_ready", "GY. VL retrieval server", order=47)
def check_vl_retrieval_ready() -> tuple[str, str, list[dict]]:
    """GY — the Qwen3-VL retrieval server (:8942) answers /ready with the
    expected embedding dim. WARN (not FAIL) when nothing is listening at all —
    that is "stack down", the convention used by the fleet-health check — but
    FAIL when it answers wrongly (wrong dim, ready:false), which is the T9-shape
    failure this gate exists to catch.
    """
    port = os.environ.get("VL_PORT", "8942")
    want_dim = int(os.environ.get("VL_EMBEDDING_DIM", "2048"))
    url = f"http://localhost:{port}/ready"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:  # noqa: S310 - fixed localhost
            body = json.loads(r.read().decode())
            code = r.getcode()
    except urllib.error.HTTPError as e:  # 503 => ready:false, still a real answer
        try:
            body = json.loads(e.read().decode())
            code = e.code
        except Exception:  # noqa: BLE001
            return "FAIL", f"{url} returned HTTP {e.code} with no JSON body", []
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return "WARN", f"nothing listening on :{port} (stack down — not a failure)", []

    subs = [
        {
            "name": "ready",
            "status": "PASS" if body.get("ready") else "FAIL",
            "detail": str(body.get("ready")),
        },
        {
            "name": f"dim == {want_dim}",
            "status": "PASS" if body.get("dim") == want_dim else "FAIL",
            "detail": str(body.get("dim")),
        },
    ]
    ok = body.get("ready") and body.get("dim") == want_dim and code == 200
    return (
        "PASS" if ok else "FAIL",
        f"{url}: ready={body.get('ready')} dim={body.get('dim')}",
        subs,
    )


@register("memory_graph_intact", "HB. memory graph intact", order=50)
def check_memory_graph_intact() -> tuple[str, str, list[dict]]:
    """HB — the memory MCP's store has its graph tables, not just `memory`
    (C2). A restore that brings back the memory table but not
    memory_entities/relations shows as stored>0 with entities==0 — the exact
    shape that made T8's 73/216/193 hard to reconcile. WARN when :8920 is down.
    """
    try:
        with urllib.request.urlopen("http://localhost:8920/health", timeout=5) as r:  # noqa: S310
            body = json.loads(r.read().decode())
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return "WARN", "memory MCP :8920 not answering (stack down — not a failure)", []
    g = body.get("graph") or {}
    stored = body.get("stored", 0)
    intact = g.get("intact", stored == 0)
    return (
        "PASS" if intact else "FAIL",
        f"stored={stored} entities={g.get('entities')} relations={g.get('relations')} intact={intact}",
        [],
    )


@register("lance_volume_mounted", "GZ. LanceDB volume mounted", order=48)
def check_lance_volume_mounted() -> tuple[str, str, list[dict]]:
    """GZ — the configured PORTAL5_LANCE_DIR passes require_lance_dir: if it is
    under /Volumes/<vol>, <vol> is a real mount, not a stray boot-disk tree."""
    from portal.platform.lance_guard import LanceStoreUnavailableError, require_lance_dir

    lance_dir = os.environ.get("PORTAL5_LANCE_DIR", "/Volumes/data01/portal5_lance")
    try:
        require_lance_dir(lance_dir)
    except LanceStoreUnavailableError as e:
        return "FAIL", str(e), []
    return "PASS", f"{lance_dir} — volume ok", []


@register("venv_lock_no_drift", "HA. venv/lock drift", order=49)
def check_venv_lock_no_drift() -> tuple[str, str, list[dict]]:
    """HA — the project venv matches uv.lock. A bench/acceptance run against a
    silently-diverged runtime is how the VL runtime was lost. Same probe as
    scripts/lib/venv_preflight.sh and check_updates.check_python_deps."""
    try:
        r = subprocess.run(
            ["uv", "sync", "--all-extras", "--frozen", "--check"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=REPO_ROOT,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return "WARN", f"could not run uv sync --check: {e}", []
    if r.returncode == 0:
        return "PASS", "venv matches uv.lock", []
    diff = [
        ln.strip()
        for ln in (r.stdout + r.stderr).splitlines()
        if ln.strip().startswith(("+", "-", "~"))
    ]
    ahead = any(ln.startswith(("-", "~")) for ln in diff)
    where = "venv AHEAD of lock (do NOT `uv sync`)" if ahead else "venv behind lock"
    return (
        "FAIL",
        f"drift: {where}; {len(diff)} package(s)",
        [{"name": ln, "status": "FAIL", "detail": ""} for ln in diff[:20]],
    )


@register("evidence_headers", "HC. reports/runtime evidence headers", order=51)
def check_evidence_headers() -> tuple[str, str, list[dict]]:
    """HC — every evidence file under reports/runtime/ carries the C3 header
    (command / inputs / resolved-versions / timestamp) and is non-empty. A
    fingerprint without versions cannot say what it fingerprinted; an empty
    file proves nothing."""
    from scripts.lib.evidence_header import check_reports_headers

    bad = check_reports_headers(REPO_ROOT)
    if not bad:
        return "PASS", "all reports/runtime evidence files carry a C3 header", []
    return (
        "FAIL",
        f"{len(bad)} evidence file(s) missing a header / zero-byte",
        [{"name": f, "status": "FAIL", "detail": r} for f, r in bad],
    )


@register("kb_stage_set_stamp", "HD. KB stage-set stamps current", order=52)
def check_kb_stage_set_stamp() -> tuple[str, str, list[dict]]:
    """HD — every KB's meta stamp carries a ``stage_set`` matching the running
    rag_multimodal composition (SEAM V1 P6). A KB indexed under a different
    chunker / figure policy / fusion mode is a stale index against the shipped
    substrate — TASK_RAG_SUBSTRATE_MIGRATION migrates them one at a time, and a
    half-migrated fleet must be visible, not silent. WARN when the LanceDB
    volume is not mounted (that is "stack down"); a KB with no ``stage_set`` key
    predates the stamp and is reported as WARN, not FAIL.
    """
    from portal.platform.lance_guard import LanceStoreUnavailableError, require_lance_dir

    lance_dir = os.environ.get("PORTAL5_LANCE_DIR", "/Volumes/data01/portal5_lance")
    try:
        require_lance_dir(lance_dir)
    except LanceStoreUnavailableError:
        return "WARN", "LanceDB volume not mounted — stage-set stamps not checked", []

    try:
        from portal.modules.research.tools import rag_multimodal as rm
        from portal.platform.retrieval import store
    except ImportError as e:
        return "WARN", f"retrieval stack not importable: {e}", []

    running = rm._stage_set()
    try:
        kbs = store.list_kbs()
    except Exception as e:  # noqa: BLE001
        return "WARN", f"could not enumerate KBs: {e}", []
    if not kbs:
        return "PASS", "no KBs ingested", []

    stale, unstamped = [], []
    for kb_id in kbs:
        stamp = store.read_stamp(kb_id) or {}
        ss = stamp.get("stage_set")
        if ss is None:
            unstamped.append(kb_id)
        elif ss != running:
            changed = sorted(k for k in set(ss) | set(running) if ss.get(k) != running.get(k))
            stale.append((kb_id, ",".join(changed)))

    subs = [{"name": kb, "status": "FAIL", "detail": f"stage_set differs: {c}"} for kb, c in stale]
    subs += [
        {"name": kb, "status": "WARN", "detail": "no stage_set — predates P6"} for kb in unstamped
    ]
    if stale:
        return "FAIL", f"{len(stale)} KB(s) indexed under a stale stage set", subs
    if unstamped:
        return (
            "WARN",
            f"{len(unstamped)} KB(s) predate the stage-set stamp — re-ingest to stamp",
            subs,
        )
    return "PASS", f"all {len(kbs)} KB stamp(s) match the running stage set", []
