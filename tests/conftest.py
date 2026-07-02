"""
Pytest configuration for Portal 6.0.4.

This conftest ensures tests run with the correct Python environment
by adding the uv virtualenv's site-packages to sys.path.
"""

import os
import sys
from pathlib import Path

# Provide a test API key so router_pipe module-level import doesn't call sys.exit(1).
# This must be set before any portal_pipeline import.
os.environ.setdefault("PIPELINE_API_KEY", "test-pipeline-key-for-unit-tests")

# Lab-env defaults — so CI's clean environment matches the "no live lab"
# posture deterministically. A populated local .env overrides these via
# setdefault. CI gets dry-run/synthetic behaviour; no more "works locally,
# fails CI" from absent LAB_* vars.
for _k, _v in {
    "LAB_TARGET_DC": "",
    "LAB_TARGET_SRV": "",
    "LAB_TARGET_WEB": "",
    "LAB_DC_VMID": "",
    "LAB_SRV_VMID": "",
    "LAB_VULHUB_VMID": "",
    "LAB_META3_VMID": "",
    "LAB_MBPTL_LXC_VMID": "",
    "SANDBOX_LAB_EXEC": "false",
}.items():
    os.environ.setdefault(_k, _v)

# Add the repo's dev .venv site-packages to path — but ONLY when pytest is running
# under a bare interpreter with no venv of its own (sys.prefix == sys.base_prefix).
# This lets `python3 -m pytest` work without activating .venv first. If pytest is
# already running inside a real venv (dev .venv, ci_local.sh's isolated
# .ci-local-venv, etc.), inserting a second, unrelated venv's site-packages ahead
# of it on sys.path shadows the active venv's own (correctly matched) packages —
# a compiled-extension mismatch (e.g. pydantic_core) in the repo .venv would then
# break every venv's test run, defeating ci_local.sh's whole point of testing in
# a clean, isolated environment.
if sys.prefix == sys.base_prefix:
    venv_site_packages = Path(__file__).parent.parent / ".venv" / "lib"

    # Find the site-packages directory
    for child in venv_site_packages.iterdir() if venv_site_packages.exists() else []:
        if child.is_dir() and child.name.startswith("python"):
            site_packages = child / "site-packages"
            if site_packages.exists() and str(site_packages) not in sys.path:
                sys.path.insert(0, str(site_packages))
            break
