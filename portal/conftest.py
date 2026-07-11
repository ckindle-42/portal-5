"""
Pytest configuration for tests living under portal/ (module test trees —
BUILD-SPEC-PORTAL-MODULES-V1 Slice 7).

pytest's conftest.py discovery is directory-hierarchy based: tests/conftest.py
only applies to tests under tests/, not to sibling directories like
portal/modules/security/tests/. This mirrors that conftest's env-var
defaults so module test trees get the same deterministic CI posture,
without duplicating logic module-by-module as more modules gain their own
tests/ under portal/modules/<x>/tests/.
"""

import os
import sys
from pathlib import Path

# Provide a test API key so router_pipe module-level import doesn't call sys.exit(1).
# This must be set before any portal.platform.inference import.
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
# Same rationale as tests/conftest.py — see that file for the full explanation.
if sys.prefix == sys.base_prefix:
    venv_site_packages = Path(__file__).parent.parent / ".venv" / "lib"

    for child in venv_site_packages.iterdir() if venv_site_packages.exists() else []:
        if child.is_dir() and child.name.startswith("python"):
            site_packages = child / "site-packages"
            if site_packages.exists() and str(site_packages) not in sys.path:
                sys.path.insert(0, str(site_packages))
            break
