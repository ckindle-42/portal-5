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
