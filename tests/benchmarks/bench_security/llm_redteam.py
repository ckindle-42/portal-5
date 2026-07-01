"""LLM / AI Red-Team lane — dogfood Portal's own surface (Gap 5).

Probes Portal's own workspaces/MCP surface for OWASP LLM Top 10 vulnerabilities.
"""

OWASP_LLM_TOP10 = [
    "LLM01: Prompt Injection",
    "LLM02: Insecure Output Handling",
    "LLM03: Training Data Poisoning",
    "LLM04: Model Denial of Service",
    "LLM05: Supply Chain Vulnerabilities",
    "LLM06: Sensitive Information Disclosure",
    "LLM07: Insecure Plugin Design",
    "LLM08: Excessive Agency",
    "LLM09: Overreliance",
    "LLM10: Model Theft",
]


def bench_llm_redteam(target_workspace: str, *, dry_run: bool = False) -> dict:
    """Run OWASP LLM Top-10 probes against a target workspace."""
    if dry_run:
        return {
            "status": "dry_run",
            "target": target_workspace,
            "probes": OWASP_LLM_TOP10,
        }
    return {"status": "placeholder", "reason": "workspace probing requires live pipeline"}
