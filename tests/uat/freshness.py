"""Portal 5 UAT — running-image vs git-HEAD codebase freshness check.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase B).
"""

from __future__ import annotations

from pathlib import Path

# Codebase freshness check
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _check_image_freshness() -> list[str]:
    """Return list of warning strings for Docker images older than the latest git commit.

    Compares each portal image build timestamp against the most recent git commit that
    touched the files that image is built from. Stale images mean the running code does
    not match HEAD and tests will not reflect current behaviour.

    Prints a clear summary; returns list of stale image names (empty = all current).
    """
    import datetime
    import subprocess

    warnings: list[str] = []

    # Latest commit time for files that affect each image
    def _last_commit_ts(paths: list[str]) -> datetime.datetime | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(_REPO_ROOT), "log", "-1", "--format=%ct", "--", *paths],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ts = result.stdout.strip()
            if ts:
                return datetime.datetime.fromtimestamp(int(ts), tz=datetime.UTC)
        except Exception:
            pass
        return None

    # Image build time via docker inspect
    def _image_built_ts(image_name: str) -> datetime.datetime | None:
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.Created}}", image_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            raw = result.stdout.strip()
            if raw and raw != "[]":
                # Parse RFC3339/ISO format
                raw = raw.rstrip("Z") + "+00:00"
                return datetime.datetime.fromisoformat(raw)
        except Exception:
            pass
        return None

    checks = [
        # (label, docker_image_name, git_paths_that_affect_it)
        (
            "portal-pipeline",
            "portal-5-portal-pipeline",
            [
                "portal/platform/inference/",
                "config/backends.yaml",
                "config/personas/",
                "Dockerfile.pipeline",
                "pyproject.toml",
                "scripts/pipeline-entrypoint.sh",
            ],
        ),
        (
            "mcp-services",
            "portal-5-mcp-documents",
            [
                "portal/modules/",
                "portal/platform/mcp_host/",
                "portal/platform/memory/",
                "portal_mcp/",
                "portal_channels/",
                "Dockerfile.mcp",
                "pyproject.toml",
            ],
        ),
    ]

    print("  [freshness] Checking Docker image freshness against git HEAD...")
    all_fresh = True
    for label, image, paths in checks:
        built = _image_built_ts(image)
        committed = _last_commit_ts(paths)
        if built is None:
            print(f"  [freshness]   {label}: image not found — skip")
            continue
        if committed is None:
            print(f"  [freshness]   {label}: no git history — skip")
            continue
        lag = (committed - built).total_seconds()
        if lag > 30:  # >30s: image predates the commit
            mins = int(lag // 60)
            msg = (
                f"  [freshness] WARNING: {label} image is {mins}m behind HEAD — "
                f"run './launch.sh rebuild' before trusting results"
            )
            print(msg, flush=True)
            warnings.append(label)
            all_fresh = False
        else:
            print(f"  [freshness]   {label}: current (lag={lag:.0f}s)", flush=True)

    if all_fresh:
        print("  [freshness] All images are current.", flush=True)

    return warnings
