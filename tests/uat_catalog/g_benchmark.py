"""UAT catalog group: g_benchmark module — auto-math tests + the CC-01
coding challenge shootout (section ``challenge``).

Two groups live here:

* ``auto-math`` — WS-MATH production-workspace tests (unchanged).
* ``challenge`` — the CC-01 Asteroids coding challenge shootout plus the
  BT-01 (SOC triage) and EX-01 (extraction) domain challenges. This was
  historically misfiled as a "benchmark": it never measured throughput —
  bench_tps.py owns that. It assigns one identical creative coding task to
  every distinct installed bench model to see what each can actually build.
  The comparative matrix is the deliverable (see
  tests/scripts/cc_challenge_matrix.py); no verdict, no auto-promotion
  (PROMOTE_POLICY). Restored from the pre-00ad696 inline driver catalog
  (TASK_UAT_CHALLENGE_RESTORE_V2). Run the group alone with
  ``--section challenge``.
"""

from __future__ import annotations

from tests.uat_catalog._shared import (
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    _CC01_PROMPT,
)

TESTS: list[dict] = [  # -----------------------------------------------------------------------
    {
        "id": "WS-MATH-01",
        "name": "Math Reasoner — Calculus Problem",
        "section": "auto-math",
        "model_slug": "auto-math",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Find the area enclosed by the curves y = x^2 and y = 2x. "
            "Show your work step by step: find intersection points, set up the integral, "
            "and evaluate it."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Intersection points found",
                "keywords": [
                    "x=0",
                    "x=2",
                    "x = 0",
                    "x = 2",
                    "x=0 and x=2",
                    "x = 0 and x = 2",
                    "(0, 0)",
                    "(2, 4)",
                    "(0,0)",
                    "(2,4)",
                    "0 and 2",
                ],
            },
            {
                "type": "any_of",
                "label": "Integral set up",
                "keywords": ["integral", "∫", "dx", "integrate", "2x - x^2", "x^2 - 2x"],
            },
            {
                "type": "any_of",
                "label": "Final answer 4/3",
                "keywords": [
                    "4/3",
                    "1.333",
                    "1.33",
                    "4 / 3",
                    "\\frac{4}{3}",
                    "frac{4}{3}",
                    "frac{4}",
                ],
            },
            {
                "type": "any_of",
                "label": "Math notation present",
                "critical": False,
                "keywords": ["```", "$$", "\\frac", "\\int", "\\["],
            },
        ],
    },
    {
        "id": "WS-MATH-02",
        "name": "Math Reasoner — Statistics Proof",
        "section": "auto-math",
        "model_slug": "auto-math",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Prove that for any dataset, the sample variance s^2 = (1/(n-1)) * sum((xi - xbar)^2) "
            "is an unbiased estimator of the population variance sigma^2. Show each step."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Expected value concept",
                "keywords": ["expected value", "E[", "expectation", "unbiased", "E(s"],
            },
            {
                "type": "any_of",
                "label": "Variance formula shown",
                "keywords": ["sigma^2", "σ²", "variance", "n-1", "degrees of freedom"],
            },
            {"type": "min_length", "label": "Substantive proof", "chars": 500},
        ],
    },
    # -----------------------------------------------------------------------
    # GROUP challenge — the CC-01 Asteroids coding challenge shootout.
    #
    # Not a benchmark (bench_tps.py owns throughput): the identical creative
    # coding task goes to every distinct installed bench model and the matrix
    # of what each one built is the deliverable. No verdict; promotions are
    # operator-only (PROMOTE_POLICY). Domain specialists get domain
    # challenges (BT-01 SOC triage, EX-01 extraction) per model-card scope.
    #
    # Restored from the pre-00ad696 inline catalog; fleet trued-up to HEAD +
    # live `ollama list`. Timeouts derive from measured V8 direct-bench TPS
    # (2026-06-10) — a capability challenge must give slow models room to
    # finish, or it grades the timeout, not the model.
    # One entry per DISTINCT installed model_hint; stand-in/duplicate-hint
    # workspaces are excluded (see TASK_UAT_CHALLENGE_RESTORE_V2 A-decisions).
    # -----------------------------------------------------------------------
    # CC-01-phi4, CC-01-phi4-reasoning, CC-01-dolphin8b removed 2026-06-11:
    # consistently WARN (≤5/10) — incapable of generating a complete Asteroids game.
    # phi4 (14B) and Dolphin-8B lack the output length / coherence for this task.
    {
        "id": "CC-01-qwen3-coder-30b",
        "name": "CC-01 Asteroids · Qwen3-Coder-30B",
        "section": "challenge",
        "model_slug": "bench-qwen3-coder-30b",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-gptoss",
        "name": "CC-01 Asteroids · GPT-OSS-20B",
        "section": "challenge",
        "model_slug": "bench-gptoss",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-llama33-70b",
        "name": "CC-01 Asteroids · Llama-3.3-70B",
        "section": "challenge",
        "model_slug": "bench-llama33-70b",
        "timeout": 1500,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-granite41-8b",
        "name": "CC-01 Asteroids · Granite-4.1 8B (IBM)",
        "section": "challenge",
        "model_slug": "bench-granite41-8b",
        "timeout": 600,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-granite41-30b",
        "name": "CC-01 Asteroids · Granite-4.1 30B (IBM)",
        "section": "challenge",
        "model_slug": "bench-granite41-30b",
        "timeout": 1500,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-qwen35-abliterated",
        "name": "CC-01 Asteroids · Qwen3.5-9B-abliterated (huihui-ai)",
        "section": "challenge",
        "model_slug": "bench-qwen35-abliterated",
        "timeout": 600,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        # P5-BENCH-001: reasoning/RL/base-style model — fenced HTML block not
        # guaranteed; has_code demoted via the _BENCH assertion variant.
        "assertions": _CC01_ASSERTIONS_BENCH,
    },
    {
        "id": "CC-01-qwen36-27b",
        "name": "CC-01 Asteroids · Qwen3.6-27B (Alibaba)",
        "section": "challenge",
        "model_slug": "bench-qwen36-27b",
        "timeout": 1500,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-qwen36-35b-a3b",
        "name": "CC-01 Asteroids · Qwen3.6-35B-A3B (Alibaba MoE)",
        "section": "challenge",
        "model_slug": "bench-qwen36-35b-a3b",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-omnicoder2",
        "name": "CC-01 Asteroids · OmniCoder-2-9B",
        "section": "challenge",
        "model_slug": "bench-omnicoder2",
        "timeout": 600,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        # P5-BENCH-001: reasoning/RL/base-style model — fenced HTML block not
        # guaranteed; has_code demoted via the _BENCH assertion variant.
        "assertions": _CC01_ASSERTIONS_BENCH,
    },
    {
        "id": "CC-01-negentropy",
        "name": "CC-01 Asteroids · bench-negentropy (DeepSeek-R1-32B Q4 stand-in)",
        "section": "challenge",
        "model_slug": "bench-negentropy",
        "timeout": 1500,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _CC01_PROMPT,
        # P5-BENCH-001: reasoning/RL/base-style model — fenced HTML block not
        # guaranteed; has_code demoted via the _BENCH assertion variant.
        "assertions": _CC01_ASSERTIONS_BENCH,
    },
    # CC-01-olmo3-32b removed 2026-06-11: consistently WARN — cannot produce complete game.
    {
        "id": "CC-01-qwen3-coder-next",
        "name": "CC-01 Asteroids · Qwen3-Coder-Next (80B/3B MoE)",
        "section": "challenge",
        "model_slug": "bench-qwen3-coder-next",
        "timeout": 600,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-qwen36-27b-mtp",
        "name": "CC-01 Asteroids · Qwen3.6-27B MTP-drafted (Q8_0)",
        "section": "challenge",
        "model_slug": "bench-qwen36-27b-mtp",
        "timeout": 1500,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-gemma4-e2b",
        "name": "CC-01 Asteroids · Gemma4-E2B QAT",
        "section": "challenge",
        "model_slug": "bench-gemma4-e2b",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-gemma4-e4b",
        "name": "CC-01 Asteroids · Gemma4-E4B (Q4_K_M)",
        "section": "challenge",
        "model_slug": "bench-gemma4-e4b",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-gemma4-e4b-qat",
        "name": "CC-01 Asteroids · Gemma4-E4B QAT",
        "section": "challenge",
        "model_slug": "bench-gemma4-e4b-qat",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-gemma4-12b",
        "name": "CC-01 Asteroids · Gemma4-12B QAT",
        "section": "challenge",
        "model_slug": "bench-gemma4-12b",
        "timeout": 900,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-gemma4-26b-qat",
        "name": "CC-01 Asteroids · Gemma4-26B-A4B QAT",
        "section": "challenge",
        "model_slug": "bench-gemma4-26b-qat",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-gemma4-26b-q4",
        "name": "CC-01 Asteroids · Gemma4-26B-A4B Q4_K_M (via bench-gemma4-26b-optiq)",
        "section": "challenge",
        "model_slug": "bench-gemma4-26b-optiq",
        "timeout": 600,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-gemma4-31b-qat",
        "name": "CC-01 Asteroids · Gemma4-31B QAT",
        "section": "challenge",
        "model_slug": "bench-gemma4-31b-qat",
        "timeout": 1500,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    # phi4-mini, phi4-mini-reasoning removed 2026-06-11: <300 chars output, incapable.
    # CC-01-starcoder2 removed 2026-06-11: consistently WARN — code-completion base model
    # lacks chat/instruction following needed for full game generation.
    {
        "id": "CC-01-devstral-small-2",
        "name": "CC-01 Asteroids · Devstral-Small-2",
        "section": "challenge",
        "model_slug": "bench-devstral-small-2",
        "timeout": 900,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-mistral-small32",
        "name": "CC-01 Asteroids · Mistral-Small-3.2-24B",
        "section": "challenge",
        "model_slug": "bench-mistral-small32",
        "timeout": 900,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-qwen36-35b-a3b-ud",
        "name": "CC-01 Asteroids · Qwen3.6-35B-A3B UD (Unsloth)",
        "section": "challenge",
        "model_slug": "bench-qwen36-35b-a3b-ud",
        "timeout": 600,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-qwen36-hauhaucs",
        "name": "CC-01 Asteroids · Qwen3.6-35B-A3B HauhauCS (uncensored)",
        "section": "challenge",
        "model_slug": "bench-qwen36-hauhaucs",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-r1-0528-qwen3-8b",
        "name": "CC-01 Asteroids · DeepSeek-R1-0528-Qwen3-8B",
        "section": "challenge",
        "model_slug": "bench-r1-0528-qwen3-8b",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        # P5-BENCH-001: reasoning/RL/base-style model — fenced HTML block not
        # guaranteed; has_code demoted via the _BENCH assertion variant.
        "assertions": _CC01_ASSERTIONS_BENCH,
    },
    # CC-01-harness1, CC-01-nex-n2-mini removed 2026-06-11: consistently WARN (5/10) —
    # both fail to deliver a fenced HTML block; incapable of full game generation.
    # ── V8 uncensored candidates (conditional — Phase 0 prunes if not pulled) ──
    {
        "id": "CC-01-r1-0528-abliterated",
        "name": "CC-01 Asteroids · R1-0528-Qwen3-8B abliterated (Josiefied)",
        "section": "challenge",
        "model_slug": "bench-r1-0528-abliterated",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        # P5-BENCH-001: abliterated reasoning chain — fenced block not guaranteed.
        "assertions": _CC01_ASSERTIONS_BENCH,
    },
    {
        "id": "CC-01-qwen3-coder-next-abliterated",
        "name": "CC-01 Asteroids · Qwen3-Coder-Next abliterated (huihui-ai)",
        "section": "challenge",
        "model_slug": "bench-qwen3-coder-next-abliterated",
        "timeout": 600,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    # ── V9 candidate CC-01 entries (TASK_V9_EVAL_EXTENDED) ──────────────────
    {
        "id": "CC-01-gemma4-12b-coder",
        "name": "CC-01 Asteroids · Gemma4-12B-Coder Fable5 (yuxinlu1)",
        "section": "challenge",
        "model_slug": "bench-gemma4-12b-coder",
        "timeout": 900,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _CC01_PROMPT,
        # CoT-trained Gemma4 coder — SFT on verifiable Python; should deliver
        # HTML code blocks. Full _CC01_ASSERTIONS (not _BENCH variant).
        "assertions": _CC01_ASSERTIONS,
    },
    {
        "id": "CC-01-qwopus-coder-mtp",
        "name": "CC-01 Asteroids · Qwopus3.6-27B-Coder-MTP (Jackrong)",
        "section": "challenge",
        "model_slug": "bench-qwopus-coder-mtp",
        "timeout": 1800,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _CC01_PROMPT,
        # 27B dense, 6 t/s — extremely verbose CoT before code; 1800s timeout
        # matches worst-case: ~430 reasoning tokens + full Asteroids impl.
        # Full _CC01_ASSERTIONS — Qwopus is a coder SFT that produced clean
        # code blocks in V9 bench quality observations.
        "assertions": _CC01_ASSERTIONS,
    },
    # ── Domain challenges (restored, fleet trued-up) ────────────────────────
    # BT-01 — Foundation-Sec: domain challenge (CVE triage), not CC-01 (code
    # gen is not its scope). Model is now the Cisco Q8_0 GGUF via Ollama
    # (PARITY-001).
    {
        "id": "BT-01-foundation-sec",
        "name": "BT-01 SOC Triage · Foundation-Sec-8B-Reasoning (Cisco)",
        "section": "challenge",
        "model_slug": "bench-foundation-sec",
        "timeout": 300,
        "workspace_tier": "ollama",
        "prompt": (
            "CVE-2021-44228 (Log4Shell) was disclosed in December 2021. "
            "Provide: (1) the CWE classification, (2) the CVSS v3 base score and why, "
            "(3) the relevant MITRE ATT&CK technique, and (4) three concrete containment "
            "steps an incident responder should take in the first 30 minutes."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "CWE classification present",
                "keywords": [
                    "cwe",
                    "cwe-20",
                    "cwe-502",
                    "cwe-917",
                    "improper",
                    "injection",
                    "deserialization",
                ],
            },
            {
                "type": "any_of",
                "label": "CVSS score present",
                "keywords": ["cvss", "10.0", "9.8", "critical", "base score"],
            },
            {
                "type": "any_of",
                "label": "MITRE ATT&CK referenced",
                "keywords": ["mitre", "att&ck", "t1190", "t1059", "execution", "initial access"],
            },
            {
                "type": "any_of",
                "label": "Containment steps",
                "keywords": [
                    "patch",
                    "firewall",
                    "block",
                    "isolat",
                    "contain",
                    "waf",
                    "rule",
                    "update",
                ],
            },
            {"type": "min_length", "label": "Substantive response", "chars": 300},
        ],
    },
    # EX-01 — LFM extraction scope (per Liquid AI model card: extraction/creative,
    # NOT code). Re-targeted from retired bench-lfm2-moe (MLX) to bench-lfm25-8b.
    {
        "id": "EX-01-lfm25-8b",
        "name": "EX-01 Extraction · LFM2.5-8B-A1B (Liquid AI)",
        "section": "challenge",
        "model_slug": "bench-lfm25-8b",
        "timeout": 180,
        "workspace_tier": "ollama",
        "prompt": (
            "Extract all named entities (people, organizations, locations, dates) from this text "
            "and return them as a JSON object with keys: people, organizations, locations, dates.\n\n"
            "Text: 'On March 15, 2024, Dr. Sarah Chen from OpenAI presented findings at the "
            "Stanford AI Lab in Palo Alto, California. The research, co-authored with Professor "
            "James Liu of MIT, was funded by the National Science Foundation.'"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "JSON structure present",
                "keywords": ["{", "people", "organizations", "locations", "dates"],
            },
            {
                "type": "any_of",
                "label": "People extracted",
                "keywords": ["sarah chen", "james liu", "chen", "liu"],
            },
            {
                "type": "any_of",
                "label": "Organizations extracted",
                "keywords": ["openai", "mit", "stanford", "national science foundation", "nsf"],
            },
            {
                "type": "any_of",
                "label": "Date extracted",
                "keywords": ["march", "2024", "march 15"],
            },
        ],
    },
    # EX-01 variant — uncensored LFM2.5 (conditional — Phase 0 prunes if not pulled)
    {
        "id": "EX-01-lfm25-8b-uncensored",
        "name": "EX-01 Extraction · LFM2.5-8B-A1B Uncensored (gaston-parravicini)",
        "section": "challenge",
        "model_slug": "bench-lfm25-8b-uncensored",
        "timeout": 180,
        "workspace_tier": "ollama",
        "prompt": (
            "Extract all named entities (people, organizations, locations, dates) from this text "
            "and return them as a JSON object with keys: people, organizations, locations, dates.\n\n"
            "Text: 'On March 15, 2024, Dr. Sarah Chen from OpenAI presented findings at the "
            "Stanford AI Lab in Palo Alto, California. The research, co-authored with Professor "
            "James Liu of MIT, was funded by the National Science Foundation.'"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "JSON structure present",
                "keywords": ["{", "people", "organizations", "locations", "dates"],
            },
            {
                "type": "any_of",
                "label": "People extracted",
                "keywords": ["sarah chen", "james liu", "chen", "liu"],
            },
            {
                "type": "any_of",
                "label": "Organizations extracted",
                "keywords": ["openai", "mit", "stanford", "national science foundation", "nsf"],
            },
            {
                "type": "any_of",
                "label": "Date extracted",
                "keywords": ["march", "2024", "march 15"],
            },
        ],
    },
]
