"""Check family modules for validate_system.py.

Importing this package populates the check registry: every family module
registers its checks at import time via @register. The validate_system.py shim
imports the package and iterates ``all_checks()``.
"""

from . import (  # noqa: F401  (imports populate the check registry)
    blue_orchestration,
    config,
    inference,
    lab,
    personas,
    platform,
    security_bench,
    telemetry,
    wiki,
)
from .registry import all_checks, register

__all__ = ["all_checks", "register"]
