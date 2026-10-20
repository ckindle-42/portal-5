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
  (PROMOTE_POLICY). Restored from the pre-06929b3 inline driver catalog
  (TASK_UAT_CHALLENGE_RESTORE_V2). Run the group alone with
  ``--section challenge``.
"""

from __future__ import annotations

from tests.uat_catalog._shared import (
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    _CC01_PROMPT,
    _GC01_ASSERTIONS,
    _GC01_PROMPT,
    _GC02_ASSERTIONS,
    _GC02_PROMPT,
    _GC03_ASSERTIONS,
    _GC03_PROMPT,
    _GC04_ASSERTIONS,
    _GC04_PROMPT,
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
    # Restored from the pre-06929b3 inline catalog; fleet trued-up to HEAD +
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
    # CC-01-olmo3-32b removed 2026-06-11: consistently WARN — cannot produce complete game.
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
        "id": "CC-01-gemma4-26b-q4",
        "name": "CC-01 Asteroids · Gemma4-26B-A4B Q4_K_M (via bench-gemma4-26b-optiq)",
        "section": "challenge",
        "model_slug": "bench-gemma4-26b-optiq",
        "timeout": 600,
        "workspace_tier": "ollama",
        "prompt": _CC01_PROMPT,
        "assertions": _CC01_ASSERTIONS,
    },
    # phi4-mini, phi4-mini-reasoning removed 2026-06-11: <300 chars output, incapable.
    # CC-01-starcoder2 removed 2026-06-11: consistently WARN — code-completion base model
    # lacks chat/instruction following needed for full game generation.
    # CC-01-harness1, CC-01-nex-n2-mini removed 2026-06-11: consistently WARN (5/10) —
    # both fail to deliver a fenced HTML block; incapable of full game generation.
    # ── V8 uncensored candidates (conditional — Phase 0 prunes if not pulled) ──
    # ── V9 candidate CC-01 entries (TASK_V9_EVAL_EXTENDED) ──────────────────
    # ── Game-challenge tier (TASK_CODING_GAMECHALLENGE_V1) ──────────────────
    # GC-01 Flappy Bird (Foundational) — 11 models, timeout 600, max_wait_no_progress 1200
    {
        "id": "GC-01-qwen3-coder-30b",
        "name": "GC-01 Flappy Bird · Qwen3-Coder-30B-A3B",
        "section": "game_challenge",
        "model_slug": "bench-qwen3-coder-30b",
        "timeout": 600,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1200,
        "prompt": _GC01_PROMPT,
        "assertions": _GC01_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-01-glm",
        "name": "GC-01 Flappy Bird · GLM-4.7-Flash",
        "section": "game_challenge",
        "model_slug": "bench-glm",
        "timeout": 600,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1200,
        "prompt": _GC01_PROMPT,
        "assertions": _GC01_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-01-omnicoder2",
        "name": "GC-01 Flappy Bird · OmniCoder-2-9B",
        "section": "game_challenge",
        "model_slug": "bench-omnicoder2",
        "timeout": 600,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1200,
        "prompt": _GC01_PROMPT,
        "assertions": _GC01_ASSERTIONS,
        "artifact_ext": "html",
    },
    # GC-02 Tetris (Intermediate) — 11 models, timeout 900, max_wait_no_progress 1800
    {
        "id": "GC-02-qwen3-coder-30b",
        "name": "GC-02 Tetris · Qwen3-Coder-30B-A3B",
        "section": "game_challenge",
        "model_slug": "bench-qwen3-coder-30b",
        "timeout": 900,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC02_PROMPT,
        "assertions": _GC02_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-02-glm",
        "name": "GC-02 Tetris · GLM-4.7-Flash",
        "section": "game_challenge",
        "model_slug": "bench-glm",
        "timeout": 900,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC02_PROMPT,
        "assertions": _GC02_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-02-omnicoder2",
        "name": "GC-02 Tetris · OmniCoder-2-9B",
        "section": "game_challenge",
        "model_slug": "bench-omnicoder2",
        "timeout": 900,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC02_PROMPT,
        "assertions": _GC02_ASSERTIONS,
        "artifact_ext": "html",
    },
    # GC-03 Platformer (Advanced) — 11 models, timeout 1200, max_wait_no_progress 1800
    {
        "id": "GC-03-qwen3-coder-30b",
        "name": "GC-03 Platformer · Qwen3-Coder-30B-A3B",
        "section": "game_challenge",
        "model_slug": "bench-qwen3-coder-30b",
        "timeout": 1200,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC03_PROMPT,
        "assertions": _GC03_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-03-glm",
        "name": "GC-03 Platformer · GLM-4.7-Flash",
        "section": "game_challenge",
        "model_slug": "bench-glm",
        "timeout": 1200,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC03_PROMPT,
        "assertions": _GC03_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-03-omnicoder2",
        "name": "GC-03 Platformer · OmniCoder-2-9B",
        "section": "game_challenge",
        "model_slug": "bench-omnicoder2",
        "timeout": 1200,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC03_PROMPT,
        "assertions": _GC03_ASSERTIONS,
        "artifact_ext": "html",
    },
    # LFM2.5-8B-A1B (Liquid AI) — non-transformer architecture, added post V1 sweep
    # ── Extended sweep — 10 additional models (operator request) ───────────
    # bench-gptoss (GPT-OSS-20B, OpenAI open-weight)
    # bench-nex-n2-mini (Nex-N2-mini, 35B MoE agentic coder, Terminal-Bench 60.7)
    {
        "id": "GC-01-nex-n2-mini",
        "name": "GC-01 Flappy Bird · Nex-N2-mini",
        "section": "game_challenge",
        "model_slug": "bench-nex-n2-mini",
        "timeout": 600,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1200,
        "prompt": _GC01_PROMPT,
        "assertions": _GC01_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-02-nex-n2-mini",
        "name": "GC-02 Tetris · Nex-N2-mini",
        "section": "game_challenge",
        "model_slug": "bench-nex-n2-mini",
        "timeout": 900,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC02_PROMPT,
        "assertions": _GC02_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-03-nex-n2-mini",
        "name": "GC-03 Platformer · Nex-N2-mini",
        "section": "game_challenge",
        "model_slug": "bench-nex-n2-mini",
        "timeout": 1200,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC03_PROMPT,
        "assertions": _GC03_ASSERTIONS,
        "artifact_ext": "html",
    },
    # ── GC-04 Burning Letter (Expert) — 10 models, timeout 1800 ────────────
    # fire particles + smoke + scorching + lighting — the ceiling test
    {
        "id": "GC-04-nex-n2-mini",
        "name": "GC-04 Burning Letter · Nex-N2-mini",
        "section": "game_challenge",
        "model_slug": "bench-nex-n2-mini",
        "timeout": 1800,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC04_PROMPT,
        "assertions": _GC04_ASSERTIONS,
        "artifact_ext": "html",
    },
    # ── GC-04 Burning Letter — original V1 models (missed in first pass) ────
    {
        "id": "GC-04-qwen3-coder-30b",
        "name": "GC-04 Burning Letter · Qwen3-Coder-30B",
        "section": "game_challenge",
        "model_slug": "bench-qwen3-coder-30b",
        "timeout": 1800,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC04_PROMPT,
        "assertions": _GC04_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-04-glm",
        "name": "GC-04 Burning Letter · GLM-4.7-Flash",
        "section": "game_challenge",
        "model_slug": "bench-glm",
        "timeout": 1800,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC04_PROMPT,
        "assertions": _GC04_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-04-omnicoder2",
        "name": "GC-04 Burning Letter · OmniCoder-2-9B",
        "section": "game_challenge",
        "model_slug": "bench-omnicoder2",
        "timeout": 1800,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC04_PROMPT,
        "assertions": _GC04_ASSERTIONS,
        "artifact_ext": "html",
    },
    # ── Domain challenges (restored, fleet trued-up) ────────────────────────
    # BT-01 — Foundation-Sec: domain challenge (CVE triage), not CC-01 (code
    # gen is not its scope). Model is now the Cisco Q8_0 GGUF via Ollama
    # (PARITY-001).
    # EX-01 — LFM extraction scope (per Liquid AI model card: extraction/creative,
    # NOT code). Re-targeted from retired bench-lfm2-moe (MLX) to bench-lfm25-8b.
    # EX-01 variant — uncensored LFM2.5 (conditional — Phase 0 prunes if not pulled)
    # ── Qwable-3.6 series (Mia-AiLab, Fable 5 SFT) — TASK_MODEL_EVAL_V9_CANDIDATES ──
    # Dense fine-tunes on Qwen3.6-27B / Qwen3.6-35B (full params active, no MoE).
    # Bench question: does Fable 5 SFT produce measurably better instruction quality
    # than base Qwen3.6, and does the dense 35B quality-per-token justify the TPS cost
    # vs our Qwen3.6-35B-A3B MoE fleet (3B active params, ~23 TPS)?
    # ── Qwen3.6-35B-A3B MoE fleet baseline (Alibaba) ──
    # ── Magistral-Small 24B Reasoning (Mistral) ──
    # ── Qwopus3.6-27B-v2-MTP (Jackrong) ──
    # ── Qwen3-Coder-Next Abliterated (huihui-ai/bartowski) ──
    # ── Dolphin3-R1-Mistral 24B (Cognitive Computations) ──
    # ── Apriel-Nemotron-15B Thinker (ServiceNow/NVIDIA) ──
    # ── WRN-8B-v2.0 (lazarevtill) ──
    # ── Huihui-Qwen3.6 abliterated series (uncensored variants) ──
    {
        "id": "GC-01-huihui-qwen36-27b",
        "name": "GC-01 Flappy Bird · Huihui-Qwen3.6-27B Abliterated",
        "section": "game_challenge",
        "model_slug": "bench-huihui-qwen36-27b",
        "timeout": 600,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1200,
        "prompt": _GC01_PROMPT,
        "assertions": _GC01_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-02-huihui-qwen36-27b",
        "name": "GC-02 Tetris · Huihui-Qwen3.6-27B Abliterated",
        "section": "game_challenge",
        "model_slug": "bench-huihui-qwen36-27b",
        "timeout": 900,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC02_PROMPT,
        "assertions": _GC02_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-03-huihui-qwen36-27b",
        "name": "GC-03 Platformer · Huihui-Qwen3.6-27B Abliterated",
        "section": "game_challenge",
        "model_slug": "bench-huihui-qwen36-27b",
        "timeout": 1200,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC03_PROMPT,
        "assertions": _GC03_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-04-huihui-qwen36-27b",
        "name": "GC-04 Burning Letter · Huihui-Qwen3.6-27B Abliterated",
        "section": "game_challenge",
        "model_slug": "bench-huihui-qwen36-27b",
        "timeout": 1800,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC04_PROMPT,
        "assertions": _GC04_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-01-huihui-qwen36-35b-a3b",
        "name": "GC-01 Flappy Bird · Huihui-Qwen3.6-35B-A3B Abliterated",
        "section": "game_challenge",
        "model_slug": "bench-huihui-qwen36-35b-a3b",
        "timeout": 600,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1200,
        "prompt": _GC01_PROMPT,
        "assertions": _GC01_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-02-huihui-qwen36-35b-a3b",
        "name": "GC-02 Tetris · Huihui-Qwen3.6-35B-A3B Abliterated",
        "section": "game_challenge",
        "model_slug": "bench-huihui-qwen36-35b-a3b",
        "timeout": 900,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC02_PROMPT,
        "assertions": _GC02_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-03-huihui-qwen36-35b-a3b",
        "name": "GC-03 Platformer · Huihui-Qwen3.6-35B-A3B Abliterated",
        "section": "game_challenge",
        "model_slug": "bench-huihui-qwen36-35b-a3b",
        "timeout": 1200,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC03_PROMPT,
        "assertions": _GC03_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-04-huihui-qwen36-35b-a3b",
        "name": "GC-04 Burning Letter · Huihui-Qwen3.6-35B-A3B Abliterated",
        "section": "game_challenge",
        "model_slug": "bench-huihui-qwen36-35b-a3b",
        "timeout": 1800,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC04_PROMPT,
        "assertions": _GC04_ASSERTIONS,
        "artifact_ext": "html",
    },
    # ── LFM series (Liquid AI) ──
    # ── Gemma 4 series (Google) ──
    {
        "id": "GC-01-gemma4-e4b-qat",
        "name": "GC-01 Flappy Bird · Gemma 4 E4B QAT",
        "section": "game_challenge",
        "model_slug": "bench-gemma4-e4b-qat",
        "timeout": 600,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1200,
        "prompt": _GC01_PROMPT,
        "assertions": _GC01_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-02-gemma4-e4b-qat",
        "name": "GC-02 Tetris · Gemma 4 E4B QAT",
        "section": "game_challenge",
        "model_slug": "bench-gemma4-e4b-qat",
        "timeout": 900,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC02_PROMPT,
        "assertions": _GC02_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-03-gemma4-e4b-qat",
        "name": "GC-03 Platformer · Gemma 4 E4B QAT",
        "section": "game_challenge",
        "model_slug": "bench-gemma4-e4b-qat",
        "timeout": 1200,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC03_PROMPT,
        "assertions": _GC03_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-04-gemma4-e4b-qat",
        "name": "GC-04 Burning Letter · Gemma 4 E4B QAT",
        "section": "game_challenge",
        "model_slug": "bench-gemma4-e4b-qat",
        "timeout": 1800,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC04_PROMPT,
        "assertions": _GC04_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-01-gemma4-26b-optiq",
        "name": "GC-01 Flappy Bird · Gemma 4 26B-A4B OptiQ",
        "section": "game_challenge",
        "model_slug": "bench-gemma4-26b-optiq",
        "timeout": 600,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1200,
        "prompt": _GC01_PROMPT,
        "assertions": _GC01_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-02-gemma4-26b-optiq",
        "name": "GC-02 Tetris · Gemma 4 26B-A4B OptiQ",
        "section": "game_challenge",
        "model_slug": "bench-gemma4-26b-optiq",
        "timeout": 900,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC02_PROMPT,
        "assertions": _GC02_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-03-gemma4-26b-optiq",
        "name": "GC-03 Platformer · Gemma 4 26B-A4B OptiQ",
        "section": "game_challenge",
        "model_slug": "bench-gemma4-26b-optiq",
        "timeout": 1200,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC03_PROMPT,
        "assertions": _GC03_ASSERTIONS,
        "artifact_ext": "html",
    },
    {
        "id": "GC-04-gemma4-26b-optiq",
        "name": "GC-04 Burning Letter · Gemma 4 26B-A4B OptiQ",
        "section": "game_challenge",
        "model_slug": "bench-gemma4-26b-optiq",
        "timeout": 1800,
        "workspace_tier": "ollama",
        "max_wait_no_progress": 1800,
        "prompt": _GC04_PROMPT,
        "assertions": _GC04_ASSERTIONS,
        "artifact_ext": "html",
    },
]
