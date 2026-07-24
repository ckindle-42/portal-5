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
    # Set for objective-based scenarios (empty red_order — no scripted
    # sequence). Names a lab_observations key (e.g. "compromise_confirmed",
    # "data_extracted") that, once truthy, ends the turn loop early.
    chain_mission_objective: str | None = None
    gate_result: dict | None = None  # readiness gate result for current scenario

    # ── Mode flags (set once from CLI args) ────────────────────────────────
    dynamic_cve_mode: bool = False
    judgment_mode: bool = False
    evasion_mode: bool = False

    # ── Derived constants (read-only after __post_init__) ──────────────────
    ollama_url: str = "http://localhost:11434"
    scope_decoy_host: str = "10.0.0.99"
    max_stall_steps: int = 4
    step_timeout_s: float = 90.0
    # Explicit num_ctx for chain /api/chat calls. Ollama 0.31+ defaults num_ctx to a
    # model's full native max context when unset (262144 for qwen3-coder), which forces
    # a 4-parallel-slot KV cache of ~1M tokens, spills off-GPU, and makes every call time
    # out (~480s = max_stall_steps x per-turn timeout) well before generating a token.
    # 32768 comfortably covers the longest chain (17 steps, including verbose tool
    # output like captured Kerberoast hashes) while staying far below the pathological
    # default. Verified live: identical request completes in ~30s (mostly one-time
    # model reload) with this set, vs. hard timeout without it.
    chain_num_ctx: int = 32768

    # ── Mutable tool list (appended to in dynamic-CVE mode) ────────────────
    chain_tools: list[dict] = field(default_factory=list)

    def set_scenario(
        self,
        red_order: list[str],
        red_prompt: str,
        runtime_env: dict | None = None,
        mission_objective: str | None = None,
    ) -> None:
        """Swap scenario context — replaces global mutation.

        If runtime_env is provided (from ensure_target_ready), substitute
        $TARGET_HOST and $TARGET_PORT in the prompt so the model attacks
        the container's REAL published port. $TARGET_VMID similarly
        substitutes the real current Proxmox vmid for the resolved host
        (never hand-typed per-scenario text -- vmids can and do change, see
        exec_chain.py's _HOST_TO_VMID for the live env-driven source).
        """
        self.chain_expected_order = red_order
        self.chain_mission_objective = mission_objective
        prompt = red_prompt
        if runtime_env:
            if runtime_env.get("TARGET_HOST"):
                prompt = prompt.replace("$TARGET_HOST", str(runtime_env["TARGET_HOST"]))
            if runtime_env.get("TARGET_PORT"):
                prompt = prompt.replace("$TARGET_PORT", str(runtime_env["TARGET_PORT"]))
            if runtime_env.get("TARGET_VMID"):
                prompt = prompt.replace("$TARGET_VMID", str(runtime_env["TARGET_VMID"]))
        self.chain_initial_prompt = prompt
