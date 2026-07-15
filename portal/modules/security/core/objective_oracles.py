"""Terminal-state objective oracles (DESIGN_EMERGENT_LAB_AGENT_V2 D3).

Path-independent verifiers of *objective end-states* for emergent runs. One
oracle per terminal-state class (not per objective) — new objectives map onto
an existing class. Registered `experimental` until bench-gated to `stable`.

Each oracle proves ONE state and says so verbatim in its honesty_claim. State
is read from `observations` (live perception / executor results at run time);
no model touches the verdict.
"""

from __future__ import annotations

from portal.modules.security.core.oracles import Oracle, register_oracle

# ── Terminal-state classes ───────────────────────────────────────────────────
# Each check reads only observed lab state. Absence of proof => False (never
# assumed). Checks are deterministic and side-effect free.


def _has_da_equivalent(finding: dict, lab_output: str, observations: dict) -> bool:
    """A session/credential with domain-admin-equivalent rights exists on the DC."""
    sessions = observations.get("sessions", [])
    return any(
        s.get("host_role") == "dc"
        and s.get("privilege") == "da_equivalent"
        and s.get("verified") is True
        for s in sessions
    )


def _has_host_foothold(finding: dict, lab_output: str, observations: dict) -> bool:
    """An interactive/exec-capable session exists on any in-lab host."""
    sessions = observations.get("sessions", [])
    return any(s.get("exec_capable") is True and s.get("verified") is True for s in sessions)


def _has_credential(finding: dict, lab_output: str, observations: dict) -> bool:
    """At least one validated credential (not merely captured) is held."""
    creds = observations.get("credentials", [])
    return any(c.get("validated") is True for c in creds)


def _has_data_access(finding: dict, lab_output: str, observations: dict) -> bool:
    """Read access to a target-designated sensitive artifact is proven."""
    artifacts = observations.get("data_access", [])
    return any(a.get("read_confirmed") is True for a in artifacts)


_OBJECTIVE_ORACLES = (
    Oracle(
        id="obj_da_equivalent",
        kind="da_equivalent_state",
        honesty_claim="proves a verified DA-equivalent session exists on the DC, not that the path was optimal",
        tier="experimental",
        check=_has_da_equivalent,
    ),
    Oracle(
        id="obj_host_foothold",
        kind="host_foothold_state",
        honesty_claim="proves a verified exec-capable session exists on an in-lab host, nothing about persistence",
        tier="experimental",
        check=_has_host_foothold,
    ),
    Oracle(
        id="obj_credential",
        kind="credential_state",
        honesty_claim="proves a validated credential is held, not that it grants any specific access",
        tier="experimental",
        check=_has_credential,
    ),
    Oracle(
        id="obj_data_access",
        kind="data_access_state",
        honesty_claim="proves confirmed read of a designated artifact, not exfiltration",
        tier="experimental",
        check=_has_data_access,
    ),
)

# Map objective-class name -> oracle id. New objectives extend this map only.
OBJECTIVE_CLASS_ORACLE: dict[str, str] = {
    "da_equivalent": "obj_da_equivalent",
    "host_foothold": "obj_host_foothold",
    "credential": "obj_credential",
    "data_access": "obj_data_access",
}


def register_objective_oracles() -> None:
    """Idempotent registration into the shared ORACLES registry."""
    for oracle in _OBJECTIVE_ORACLES:
        register_oracle(oracle)


register_objective_oracles()
