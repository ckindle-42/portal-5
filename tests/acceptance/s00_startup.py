"""S0: Prerequisites and environment check."""
import subprocess
import sys

from tests.acceptance._common import (
    API_KEY,
    ROOT,
    _git_sha,
    record,
)


async def run() -> None:
    """S0: Prerequisites and environment check."""
    print("\n━━━ S0. PREREQUISITES ━━━")
    sec = "S0"

    # S0-01: Python version
    t0 = time.time()
    py_ver = sys.version_info
    record(
        sec,
        "S0-01",
        "Python version",
        "PASS" if py_ver >= (3, 10) else "FAIL",
        f"Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}",
        t0=t0,
    )

    # S0-02: Required packages
    t0 = time.time()
    required = ["httpx", "yaml", "mcp"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    record(
        sec,
        "S0-02",
        "Required packages",
        "PASS" if not missing else "FAIL",
        f"missing: {missing}" if missing else "all present",
        t0=t0,
    )

    # S0-03: .env file exists
    t0 = time.time()
    env_exists = (ROOT / ".env").exists()
    record(
        sec,
        "S0-03",
        ".env file exists",
        "PASS" if env_exists else "FAIL",
        str(ROOT / ".env"),
        t0=t0,
    )

    # S0-04: API key configured
    t0 = time.time()
    has_key = bool(API_KEY)
    record(
        sec,
        "S0-04",
        "PIPELINE_API_KEY configured",
        "PASS" if has_key else "FAIL",
        f"key length: {len(API_KEY)}" if has_key else "not set",
        t0=t0,
    )

    # S0-05: Git repository
    t0 = time.time()
    sha = _git_sha()
    record(
        sec,
        "S0-05",
        "Git repository",
        "PASS" if sha != "unknown" else "WARN",
        f"SHA: {sha}",
        t0=t0,
    )

    # S0-06: MLX watchdog must be STOPPED during testing.
    # The watchdog triggers its own evictions and proxy restarts while the runner
    # is waiting for a model to load, causing interference and false empty responses.
    # Step 2 pre-flight stops it; this check enforces that it stayed stopped.
    t0 = time.time()
    try:
        r = subprocess.run(
            ["pgrep", "-f", "mlx-watchdog"], capture_output=True, text=True, timeout=5
        )
        running = r.returncode == 0 and bool(r.stdout.strip())
        if running:
            record(
                sec,
                "S0-06",
                "MLX watchdog stopped",
                "WARN",
                f"watchdog still running (PID {r.stdout.strip()}) — stop it: ./launch.sh stop-mlx-watchdog",
                t0=t0,
            )
        else:
            record(sec, "S0-06", "MLX watchdog stopped", "PASS", "watchdog not running — safe to test", t0=t0)
    except Exception as e:
        record(sec, "S0-06", "MLX watchdog stopped", "WARN", str(e)[:80], t0=t0)

    # S0-07: Deployed MLX proxy matches source (catches P5-ROAD-MLX-002 staleness)
    t0 = time.time()
    import filecmp  # noqa: PLC0415

    src = ROOT / "scripts/mlx-proxy.py"
    deployed = Path.home() / ".portal5/mlx/mlx-proxy.py"
    if not deployed.exists():
        record(
            sec,
            "S0-07",
            "Deployed MLX proxy",
            "INFO",
            "not yet deployed (run ./launch.sh install-mlx)",
            t0=t0,
        )
    elif filecmp.cmp(src, deployed, shallow=False):
        record(
            sec,
            "S0-07",
            "Deployed MLX proxy matches source",
            "PASS",
            "deployed copy in sync",
            t0=t0,
        )
    else:
        record(
            sec,
            "S0-07",
            "Deployed MLX proxy matches source",
            "WARN",
            "deployed != source — run ./launch.sh install-mlx",
            t0=t0,
        )
