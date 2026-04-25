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

# Add uv venv site-packages to path if not already present
venv_site_packages = Path(__file__).parent.parent / ".venv" / "lib"

# Find the site-packages directory
for child in venv_site_packages.iterdir() if venv_site_packages.exists() else []:
    if child.is_dir() and child.name.startswith("python"):
        site_packages = child / "site-packages"
        if site_packages.exists() and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))
        break
