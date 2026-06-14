"""S0: Prerequisites and environment check."""
import sys
import time

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
