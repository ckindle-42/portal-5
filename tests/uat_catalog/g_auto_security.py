"""UAT catalog group: auto-security (security workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import REFUSAL_PHRASES, _CC01_ASSERTIONS, _CC01_ASSERTIONS_BENCH  # noqa: F401

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-05",
        "name": "Security Analyst — OT/ICS Hardening",
        "section": "auto-security",
        "model_slug": "auto-security",
        "timeout": 120,
        "workspace_tier": "mlx_large",
        "prompt": (
            "/nothink\n"
            "Our utility has a Historian server that sits at the boundary between the OT network "
            "(Level 2) and the IT DMZ. It runs Windows Server 2019, OSIsoft PI, has RDP enabled "
            "for vendor support, and is backed up nightly over the corporate LAN. Identify the "
            "top security concerns and recommend mitigations."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "RDP risk identified",
                "keywords": ["rdp", "remote desktop"],
            },
            {
                "type": "any_of",
                "label": "Boundary/DMZ risk",
                "keywords": [
                    "boundary",
                    "lateral",
                    "dmz",
                    "segmentation",
                    "isolation",
                    "network segment",
                    "purdue",
                    "zone",
                    "conduit",
                    "network boundary",
                    "air gap",
                    "firewall",
                    "network architecture",
                    "segment",
                ],
            },
            {
                "type": "any_of",
                "label": "Framework cited",
                "keywords": [
                    "iec 62443",
                    "nerc cip",
                    "nist",
                    "cis",
                    "purdue model",
                    "ot security",
                    "isa/iec",
                    "security framework",
                    "security standard",
                    "compliance",
                ],
                "critical": False,
            },
            {"type": "min_length", "label": "Substantive response", "chars": 400},
        ],
    },
    {
        "id": "P-S01",
        "name": "Cyber Security Specialist — Defense-in-Depth",
        "section": "auto-security",
        "model_slug": "cybersecurityspecialist",
        "timeout": 120,
        "workspace_tier": "mlx_large",
        "prompt": (
            "/nothink\n"
            "Our SOC is seeing a 400% increase in alerts but the team size is flat. "
            "Leadership wants to 'just block more at the firewall.' Analyze this using a "
            "defense-in-depth framework and recommend a structured response. "
            "Cite specific controls by framework (NIST CSF, CIS Controls, or MITRE ATT&CK)."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "Firewall-only rejected",
                "keywords": ["firewall is enough", "just block"],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Framework cited",
                "keywords": [
                    "nist csf",
                    "nist cybersecurity framework",
                    "nist 800-53",
                    "nist sp 800",
                    "cis controls",
                    "cis control",
                    "cis benchmark",
                    "mitre att&ck",
                    "mitre attack",
                    "iso 27001",
                    "iso/iec 27001",
                    "defense in depth",
                    "defense-in-depth",
                    "layered defense",
                    "zero trust",
                ],
            },
            {
                "type": "any_of",
                "label": "Alert tuning mentioned",
                "keywords": [
                    "tuning",
                    "false positive",
                    "soar",
                    "triage",
                    "noise",
                    "fidelity",
                    "false positive rate",
                    "alert fatigue",
                    "prioritization",
                    "deduplication",
                    "suppression",
                    "rule tuning",
                ],
                "critical": False,
            },
            {"type": "min_length", "label": "Substantive response", "chars": 500},
        ],
    },
    {
        "id": "P-S05",
        "name": "Network Engineer — OT Segmentation Design",
        "section": "auto-security",
        "model_slug": "networkengineer",
        "timeout": 120,
        "workspace_tier": "mlx_large",
        "prompt": (
            "/nothink\n"
            "Design network segmentation for a substation automation system. Components: "
            "SEL-751 protective relays (IEC 61850 GOOSE), an HMI workstation, a data "
            "concentrator/historian, and a corporate WAN link for remote SCADA access. "
            "Threat model: prevent ransomware from IT from reaching protection relays. "
            "Specify how each component is isolated, which zone/level each sits in, "
            "and what controls sit between IT and the relays."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Relay isolation specified",
                "keywords": [
                    "relay",
                    "isolat",
                    "level 1",
                    "level1",
                    "protection",
                    "sel-751",
                    "goose",
                    "firewall between",
                ],
            },
            {
                "type": "any_of",
                "label": "Historian in DMZ",
                "keywords": [
                    "dmz",
                    "one-way",
                    "data diode",
                    "historian",
                    "demilitarized",
                    "buffer zone",
                ],
            },
            {
                "type": "any_of",
                "label": "Framework cited",
                "keywords": [
                    "iec 62443",
                    "purdue",
                    "zone",
                    "iec 61850",
                    "nist",
                    "nerc",
                    "level 1",
                    "level 2",
                    "vlan",
                    "segment",
                ],
            },
            {
                "type": "any_of",
                "label": "Safety warning included",
                "keywords": [
                    "safety",
                    "change management",
                    "protection relay",
                    "outage",
                    "maintenance window",
                ],
                "critical": False,
            },
        ],
    },
    {
        "id": "T-11",
        "name": "Security MCP — Vulnerability Classification",
        "section": "auto-security",
        "model_slug": "auto-security",
        "timeout": 180,
        "workspace_tier": "mlx_large",
        "prompt": (
            "/nothink\n"
            "Classify this vulnerability by severity (CVSS score and rating) and explain your rationale: "
            '"An unauthenticated remote attacker can send a crafted HTTP request to the '
            "management interface of a network switch, triggering a stack buffer overflow "
            'and executing arbitrary code with root privileges."'
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "CRITICAL severity",
                "keywords": [
                    "critical",
                    "9.0",
                    "9.8",
                    "10.0",
                    "severe",
                    "high",
                    "very high",
                    "highest",
                    "maximum",
                    "critical severity",
                    "most severe",
                ],
            },
            {
                "type": "any_of",
                "label": "Score >= 9.0",
                "keywords": [
                    "9.8",
                    "10.0",
                    "9.9",
                    "9.0",
                    "9.5",
                    "9.1",
                    "9.2",
                    "9.3",
                    "9.4",
                    "9.6",
                    "9.7",
                    "critical",
                    "cvss",
                    "cvss v3",
                    "cvss score",
                    "cvss: 9",
                ],
            },
            {
                "type": "any_of",
                "label": "Rationale includes key factors",
                "keywords": [
                    "unauthenticated",
                    "remote",
                    "code execution",
                    "overflow",
                    "root",
                    "buffer",
                    "arbitrary code",
                    "network-accessible",
                    "no authentication",
                    "without authentication",
                ],
            },
        ],
    },
    {
        "id": "T-12",
        "name": "Web Search — Recent CVEs via SearXNG",
        "section": "auto-security",
        "model_slug": "auto-security",
        "timeout": 120,
        "workspace_tier": "mlx_large",
        "prompt": (
            "/nothink\n"
            "Search for and summarize the three most significant CVEs disclosed in the past "
            "60 days affecting network infrastructure equipment (routers, switches, firewalls). "
            "For each: CVE ID, affected vendor/product, severity, and remediation status."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "CVE or vendor advisory IDs present",
                "keywords": [
                    "cve-",
                    "cve ",
                    "cve_",
                    "cve id",
                    "cve identifier",
                    "kb",
                    "rhsa-",
                    "cisco-sa-",
                    "advisory",
                    "vulnerability id",
                ],
            },
            {"type": "min_length", "label": "Substantive results", "chars": 300},
            {
                "type": "not_contains",
                "label": "No 'no results'",
                "keywords": ["no results found", "could not find any"],
            },
        ],
    },]
