"""``portal trace`` — the live, hop-by-hop check of the running system."""

from __future__ import annotations

from .command import cmd_trace, register

__all__ = ["cmd_trace", "register"]
