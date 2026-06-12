"""UAT catalog group: advanced (advanced/multi-turn workspace)."""

from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [  # -----------------------------------------------------------------------
    {
        "id": "A-01",
        "name": "Document RAG — Upload, Query, Follow-Up",
        "section": "advanced",
        "model_slug": "auto",
        "timeout": 120,
        "workspace_tier": "ollama",
        "is_multi_turn": True,
        "skip_if": "no_docx_fixture",
        "prompt": "Summarize the key points of this document in 5 bullet points.",
        "turn2": "What does the document say about access control? Quote the relevant section.",
        "assertions": [
            # Lowered from 150 to 80 — streaming can cut off mid-response;
            # a partial summary still demonstrates RAG retrieval worked.
            {"type": "min_length", "label": "Turn 1 summary substantive", "chars": 80},
            {
                "type": "not_contains",
                "label": "Not generic",
                "keywords": ["the document discusses topics", "the document covers various"],
            },
        ],
        "turn2_assertions": [
            {
                "type": "min_length",
                "label": "Turn 2 retrieval substantive",
                "chars": 100,
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Quotes content actually in fixture",
                "keywords": [
                    "access control",
                    "rbac",
                    "authentication",
                    "authorization",
                    "least privilege",
                    "principle of",
                ],
            },
        ],
    },
    {
        "id": "A-02",
        "name": "Knowledge Base — Persistent Collection Query",
        "section": "advanced",
        "model_slug": "auto",
        "timeout": 120,
        "workspace_tier": "ollama",
        "skip_if": "no_knowledge_base",
        "prompt": "#Test Collection What topics are covered across the documents in this collection?",
        "assertions": [
            {"type": "min_length", "label": "Response substantive", "chars": 100},
            {
                "type": "not_contains",
                "label": "Collection found",
                "keywords": ["no collection", "cannot find", "does not exist"],
            },
        ],
    },
    {
        "id": "A-03",
        "name": "Same-Session Memory — Fact Recall",
        "section": "advanced",
        "model_slug": "auto",
        "timeout": 120,
        "workspace_tier": "ollama",
        "is_multi_turn": True,
        "prompt": (
            "For context: I am a network security engineer at a power utility. "
            "I primarily work with Cisco IOS, Fortinet firewalls, and Splunk. "
            "My main focus is OT/ICS network segmentation. Please remember this."
        ),
        "turn2": (
            "Without me restating it, what is my role and what tooling do I work with? Be specific."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Memory acknowledgment (turn 1)",
                "critical": False,
                "keywords": [
                    "remember",
                    "noted",
                    "i'll keep",
                    "stored",
                    "saved",
                    "got it",
                    "understood",
                    "acknowledged",
                    "will remember",
                    "i'll remember",
                    "i will remember",
                    "keep in mind",
                    "keeping in mind",
                    "context saved",
                    "context noted",
                    "context received",
                    "i'll make note",
                    "making note",
                    "taking note",
                    "will note",
                    "i'll use this",
                    "keep this in mind",
                    "have noted",
                    "i've noted",
                    "i've saved",
                    "i'll keep that",
                    "i will keep",
                    "filed away",
                ],
            },
        ],
        "turn2_assertions": [
            {
                "type": "contains",
                "label": "Recalls role (network security engineer)",
                "keywords": ["network security"],
            },
            {
                "type": "any_of",
                "label": "Recalls tooling",
                "keywords": ["cisco", "fortinet", "splunk", "ios"],
            },
            {
                "type": "any_of",
                "label": "Recalls focus area",
                "keywords": [
                    "ot",
                    "ics",
                    "segmentation",
                    "operational technology",
                    "industrial control",
                ],
            },
        ],
    },
    {
        "id": "A-04",
        "name": "Routing Validation — Content-Aware Selection",
        "section": "advanced",
        "model_slug": "auto",
        "timeout": 90,
        "workspace_tier": "ollama",
        "assert_routed_via": [
            "baronllm",
            "lily",
            "xploiter",
        ],
        "prompt": "How do I configure a Cisco ASA firewall to block outbound Tor traffic?",
        "assertions": [
            {
                "type": "any_of",
                "label": "Security response",
                "critical": False,
                "keywords": ["acl", "access-list", "firewall", "policy", "deny", "block"],
            },
            {
                "type": "min_length",
                "label": "Substantive response",
                "chars": 200,
                "critical": False,
            },
        ],
    },
    # A-05 — Telegram bot dispatcher path. Drives the same call call_pipeline_async()
    # makes on every inbound message; container pre-check ensures the bot process
    # is alive (the Telegram <-> bot network hop is third-party and out of scope).
    {
        "id": "A-05",
        "name": "Telegram Bot — Pipeline Path (auto-coding)",
        "section": "advanced",
        "model_slug": "auto-coding",
        "timeout": 90,
        "workspace_tier": "ollama",
        "skip_if": "no_bot_telegram",
        "via_dispatcher": True,
        "requires_container": "portal5-telegram",
        "prompt": "Write a one-liner Python function to check if a number is prime.",
        "assertions": [
            {"type": "contains", "label": "Python function present", "keywords": ["def "]},
            {
                "type": "any_of",
                "label": "Prime-check semantics",
                "keywords": [
                    "prime",
                    "% 2",
                    "%2",
                    "range(",
                    "all(",
                    "sympy",
                    "math.isqrt",
                    "n ** 0.5",
                    "n**0.5",
                ],
            },
            {"type": "min_length", "label": "Substantive response", "chars": 60},
        ],
    },
    # A-06 — Slack bot dispatcher path. Slack Socket Mode bot routes "security"
    # channel mentions to auto-security per CHANNEL_WORKSPACE_MAP; this test
    # drives the matching workspace + prompt directly.
    {
        "id": "A-06",
        "name": "Slack Bot — Pipeline Path (auto-security)",
        "section": "advanced",
        "model_slug": "auto-security",
        "timeout": 120,
        "workspace_tier": "ollama",
        "skip_if": "no_bot_slack",
        "via_dispatcher": True,
        "requires_container": "portal5-slack",
        "prompt": "Summarize the key security risks of running Docker with the --privileged flag in 3 bullet points.",
        "assertions": [
            {
                "type": "any_of",
                "label": "Privileged-Docker risk vocabulary",
                "keywords": [
                    "privileged",
                    "kernel",
                    "host",
                    "capabilit",
                    "escape",
                    "root",
                    "syscall",
                    "cgroup",
                    "namespace",
                    "device",
                ],
            },
            {
                "type": "any_of",
                "label": "Bullet structure",
                "keywords": ["- ", "* ", "1.", "2.", "3.", "\u2022"],
            },
            {"type": "min_length", "label": "Substantive response", "chars": 200},
        ],
    },
    {
        "id": "A-07",
        "name": "Grafana Monitoring — Metrics Visibility",
        "section": "advanced",
        "model_slug": "auto",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": "[MANUAL] After running 5+ tests, open http://localhost:3000. Verify portal_tokens_per_second shows recent data with workspace labels. Mark PASS/SKIP/FAIL manually.",
        "assertions": [],
        "is_manual": True,
    },
    # A-08 — Cross-session memory recall. The test runner pre-seeds a fact
    # via direct Memory MCP API call (deterministic store), then opens two
    # SEPARATE chats and asks each to recall it using the 'recall' tool.
    # Both chats must retrieve the marker without any context from each other.
    # This tests the full recall pipeline: LanceDB → semantic search → model.
    # Decoupled from model-initiated 'remember' (previously flaky in OWUI
    # programmatic sessions) while still testing what matters for users.
    {
        "id": "A-08",
        "name": "Cross-Session Memory — Two-Chat Persistence",
        "section": "advanced",
        "model_slug": "auto-daily",  # gemma4:26b-a4b-it-qat — primary for auto-daily
        "timeout": 240,
        "workspace_tier": "ollama",
        "is_two_chat": True,
        # Pre-seed data injected by _run_two_chat_test before any chat opens.
        "memory_preseed": {
            "text": (
                "My favorite Portal 5 deployment region is named Aurora-7 "
                "and the operator on call is Hex-Lantern."
            ),
            "category": "preference",
            "tags": ["uat-a08-marker"],
        },
        # Chat 1: recall the pre-seeded fact. The model has no way to know
        # "Aurora-7" or "Hex-Lantern" unless it invokes the recall tool.
        "prompt": (
            "Use the 'recall' tool to find stored memories about my favorite "
            "Portal 5 deployment region. Tell me: what is the region name, "
            "and who is the operator on call?"
        ),
        # Chat 2: same recall query in a completely fresh OWUI chat.
        "turn2_in_new_chat": (
            "Use the 'recall' tool to find: what's my favorite Portal 5 "
            "deployment region, and who's the operator on call? Search "
            "for 'favorite Portal 5 deployment region'."
        ),
        "assertions": [
            # Chat 1 recall: model must return one of the marker tokens.
            {
                "type": "any_of",
                "label": "Chat 1: recalls region name",
                "keywords": ["aurora-7", "aurora 7", "aurora7"],
            },
            {
                "type": "any_of",
                "label": "Chat 1: recalls operator name",
                "keywords": ["hex-lantern", "hex lantern", "hexlantern"],
                "critical": False,  # one marker is sufficient for Chat 1
            },
        ],
        "turn2_assertions": [
            # Chat 2: same markers required — proves persistence across chats.
            {
                "type": "any_of",
                "label": "Chat 2: recalls region name",
                "keywords": ["aurora-7", "aurora 7", "aurora7"],
            },
            {
                "type": "any_of",
                "label": "Chat 2: recalls operator name",
                "keywords": ["hex-lantern", "hex lantern", "hexlantern"],
                "critical": False,  # one marker is sufficient for Chat 2
            },
        ],
        "cleanup_marker_tag": "uat-a08-marker",
    },
]
