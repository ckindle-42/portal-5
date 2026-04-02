"""
Pytest configuration for Portal 5.2.1.

This conftest ensures tests run with the correct Python environment
by adding the uv virtualenv's site-packages to sys.path.
"""

import sys
from pathlib import Path

# Add uv venv site-packages to path if not already present
venv_site_packages = Path(__file__).parent.parent / ".venv" / "lib"

# Find the site-packages directory
for child in venv_site_packages.iterdir() if venv_site_packages.exists() else []:
    if child.is_dir() and child.name.startswith("python"):
        site_packages = child / "site-packages"
        if site_packages.exists() and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))
        break
