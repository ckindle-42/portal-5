"""BenchConfig — per-run context replacing mutable module globals.

All fields that were previously mutated at module level by main() and read
by chain/blue/lab runners are now fields on this dataclass. Functions that
need these values receive ``cfg: BenchConfig`` instead of reading globals.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BenchConfig:
    """Per-run configuration threaded through all bench functions."""

    # ── Scenario state (swapped per-scenario in the run loop) ──────────────
    chain_expected_order: list[str] = field(default_factory=list)
    chain_initial_prompt: str = ""

    # ── Mode flags (set once from CLI args) ────────────────────────────────
    dynamic_cve_mode: bool = False
    judgment_mode: bool = False
    evasion_mode: bool = False

    # ── Derived constants (read-only after __post_init__) ──────────────────
    ollama_url: str = "http://localhost:11434"
    scope_decoy_host: str = "10.0.0.99"
    max_stall_steps: int = 4
    step_timeout_s: float = 90.0

    # ── Mutable tool list (appended to in dynamic-CVE mode) ────────────────
    chain_tools: list[dict] = field(default_factory=list)

    def set_scenario(self, red_order: list[str], red_prompt: str) -> None:
        """Swap scenario context — replaces global mutation."""
        self.chain_expected_order = red_order
        self.chain_initial_prompt = red_prompt
