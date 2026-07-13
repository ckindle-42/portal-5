"""UAT catalog group: auto-data (data workspace)."""

from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [  # -----------------------------------------------------------------------
    {
        "id": "WS-15",
        "name": "Data Analyst — SIEM Dataset Cleaning",
        "section": "auto-data",
        "model_slug": "auto-data",
        "timeout": 360,
        "workspace_tier": "ollama",
        "prompt": (
            "I imported a CSV from our SIEM: 50,000 rows, columns: timestamp, src_ip, dst_ip, "
            "bytes_out, duration_ms, protocol, action. Problems: timestamps have mixed formats "
            "(ISO 8601 and epoch), ~3% of src_ip are empty, bytes_out has some -1 values. "
            "Before running analysis, what data quality steps do I need to take, and in what order? "
            "Give me the pandas code for each step."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Timestamp normalization",
                "keywords": ["pd.to_datetime", "to_datetime", "timestamp"],
            },
            {
                "type": "any_of",
                "label": "Missing src_ip handling",
                "keywords": [
                    "fillna",
                    "dropna",
                    "isnull",
                    "isna",
                    "nan",
                    "NaN",
                    "null",
                    "missing",
                    "empty",
                ],
            },
            {
                "type": "any_of",
                "label": "bytes_out sentinel",
                "keywords": [
                    "bytes_out",
                    "sentinel",
                    "invalid",
                    "fillna",
                    "replace",
                    "nan",
                    "NaN",
                    "-1",
                ],
            },
            {
                "type": "any_of",
                "label": "Pandas code present or referenced",
                "keywords": ["```python", "```", "pd.", "df.", "import pandas", "pandas"],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-DA01",
        "name": "Data Analyst — Correlation vs Causation",
        "section": "auto-data",
        "model_slug": "dataanalyst",
        "timeout": 90,
        "workspace_tier": "ollama",
        "include_thinking_in_assertions": True,
        "prompt": (
            "Our data shows that users who enable dark mode have 23% higher retention rates. "
            "Should we force all users onto dark mode to improve retention?"
        ),
        "assertions": [
            {
                "type": "min_length",
                "label": "Substantive response (not empty after think-strip)",
                "chars": 80,
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Correlation/causation distinguished",
                "keywords": [
                    "correlation",
                    "causation",
                    "correlation does not",
                    "does not imply",
                    "association",
                    "doesn't mean",
                    "doesn't necessarily",
                    "causal relationship",
                    "confounding",
                    "selection bias",
                    "self-selection",
                    "selection effect",
                    "reverse causation",
                    # Synonyms models use in place of "correlation/causation"
                    "causes",
                    "causal",
                    "causal link",
                    "doesn't cause",
                    "does not cause",
                    "just because",
                    "lurking",
                    "confounder",
                    "confounded",
                    "third variable",
                    "hidden variable",
                    "third factor",
                    "cannot conclude",
                    "can't conclude",
                    "observational",
                    "not evidence",
                    "does not prove",
                    "doesn't prove",
                    "relationship between",
                    "implies causation",
                ],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "A/B test recommended",
                "keywords": [
                    "a/b test",
                    "experiment",
                    "randomized",
                    "causal",
                    "alternative approach",
                    "instead",
                    "other strategy",
                    "alternative",
                    "better to",
                    "should test",
                    "controlled",
                    # Structured-output models express uncertainty rather than explicit test rec
                    "validate",
                    "medium confidence",
                    "p-value",
                    "statistical significance",
                    "statistical",
                    "confidence",
                    "not conclusive",
                    "further testing",
                    "more data",
                    "evaluate",
                ],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Does not recommend forcing",
                "keywords": [
                    "should not force",
                    "not recommend forcing",
                    "backfire",
                    "counterproductive",
                    "would not",
                    "better to offer",
                    "let users choose",
                    "choice",
                    "not necessarily",
                    "could backfire",
                    "might backfire",
                    "offering a choice",
                    "not everyone",
                    "not everyone prefers",
                    "not advisable",
                    "inadvisable",
                    "rather than forc",
                    "avoid forcing",
                    "don't force",
                    "do not force",
                    "opt-in",
                    "premature",
                    "instead",
                    "offer",
                    "option",
                    "test first",
                    "evaluate first",
                    # Structured-output phrasing for hedging on forced rollout
                    "may not",
                    "same results for all",
                    "not all users",
                    "limitation",
                ],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-DA02",
        "name": "Data Scientist — Imbalanced Class Problem",
        "section": "auto-data",
        "model_slug": "datascientist",
        "timeout": 240,
        "workspace_tier": "ollama",
        "prompt": (
            "I am building a fraud detection model. My dataset is 99.7% legitimate transactions "
            "and 0.3% fraud. I trained a random forest and got 99.6% accuracy. "
            "My manager is happy. Should they be?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Imbalanced class issue",
                "keywords": [
                    "imbalance",
                    "imbalanced",
                    "class imbalance",
                    "skewed",
                    "unbalanced",
                    "minority class",
                    "majority class",
                    "class distribution",
                    # Structured models describe the ratio rather than labelling it
                    "0.3%",
                    "99.7%",
                    "heavily skewed",
                ],
            },
            {
                "type": "any_of",
                "label": "Better metric suggested",
                "keywords": ["precision", "recall", "auc", "f1", "roc"],
            },
            {
                "type": "not_contains",
                "label": "Does not validate happiness",
                "keywords": ["yes, the manager", "your manager is right", "99.6% is excellent"],
                "critical": True,
            },
        ],
    },
    {
        "id": "P-DA03",
        "name": "ML Engineer — Benchmark vs Production",
        "section": "auto-data",
        "model_slug": "machinelearningengineer",
        "timeout": 240,
        "workspace_tier": "ollama",
        "prompt": (
            "I found a transformer model that gets 94% on the MMLU benchmark. "
            "I want to deploy it for customer support ticket routing in production. "
            "Should I just use it?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Benchmark gap addressed",
                "keywords": [
                    "benchmark",
                    "production gap",
                    "domain shift",
                    "different distribution",
                ],
            },
            {
                "type": "any_of",
                "label": "Latency/throughput mentioned",
                "keywords": [
                    "latency",
                    "throughput",
                    "production",
                    "scale",
                    "evaluate",
                    "benchmark",
                    "domain",
                    "ticket",
                    "further",
                    "not yet",
                    "test",
                    "measure",
                    "assess",
                    "pilot",
                    "real-world",
                    "deployment",
                    "serving",
                ],
            },
            {
                "type": "not_contains",
                "label": "Does not say 'just use it'",
                "keywords": ["yes, just use", "94% sounds great", "you should use it"],
                "critical": True,
            },
        ],
    },
    {
        "id": "P-DA04",
        "name": "Statistician — Check Assumptions Before t-test",
        "section": "auto-data",
        "model_slug": "statistician",
        "timeout": 240,
        "workspace_tier": "ollama",
        "prompt": (
            "I have two groups of 30 measurements each (response times in milliseconds). "
            "I want to know if they are significantly different. Run a t-test."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Normality check mentioned",
                "keywords": [
                    "normality",
                    "shapiro",
                    "normal distribution",
                    "assumption",
                    "gaussian",
                    "qq plot",
                    "qqplot",
                    "check assumption",
                    "verify assumption",
                    "first check",
                    "before running",
                    "normally distributed",
                    "normal dist",
                    "data distribution",
                    "check the distribution",
                    "parametric",
                    "distribution check",
                    "central limit",
                    "skew",
                    "kurtosis",
                ],
            },
            {
                "type": "any_of",
                "label": "Variance check mentioned",
                "keywords": [
                    "variance",
                    "levene",
                    "equal variance",
                    "welch",
                    "homogeneity",
                    "bartlett",
                    "equal spread",
                    "standard deviation",
                    "similar variance",
                    "spread is",
                    "similar spread",
                    "homoscedastic",
                    "f-test",
                    "f test",
                    "variance check",
                    "equal standard",
                ],
            },
            {
                "type": "not_contains",
                "label": "Does not jump straight to t-test",
                "keywords": ["the t-statistic is", "p-value =", "t(58) ="],
                "critical": False,
            },
        ],
    },
    {
        "id": "P-DA05",
        "name": "STEM Analyst — Binomial Derivation",
        "section": "auto-data",
        "model_slug": "phi4stemanalyst",
        "timeout": 180,
        # ROUTING NOTE: phi4stemanalyst → auto-daily (formerly the auto-phi4
        # alias, retired BUILD_PROGRAM_ALIAS_RETIRE_V1.md Phase 3) → model_hint: phi4-reasoning:plus
        # When :plus is missing from Ollama, falls back to bare phi4-reasoning (slow, ~1352s/attempt)
        # or dolphin-llama3:8b (fast but fails content assertions). Run `ollama pull phi4-reasoning:plus`
        # to stabilize. Until then expect 3x retry loops hitting 4068s+ elapsed.
        "max_wait_no_progress": 1500,  # allow phi4-reasoning full think budget before fail
        "workspace_tier": "ollama",
        # phi4-reasoning:plus emits chain-of-thought in <think> block; include it so
        # keyword assertions can find mathematical content like "binomial", "E[X]=5"
        "include_thinking_in_assertions": True,
        "prompt": (
            "A network packet filter runs as an independent Bernoulli trial on each packet. "
            "P(packet blocked) = 0.001. In a stream of 5,000 packets, what is the probability "
            "that more than 10 packets are blocked? Show the full derivation. "
            "Also flag if this problem has multiple valid interpretations."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Binomial stated",
                "keywords": [
                    "binomial",
                    "bernoulli",
                    "b(5000",
                    "b(n",
                    "5,000",
                    "5000",
                    "0.001",
                ],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Expected value = 5",
                "critical": False,
                "keywords": [
                    "e[x] = 5",
                    "e(x) = 5",
                    "e[x]=5",
                    "e(x)=5",
                    "expected value",
                    "expected number",
                    "expected count",
                    "5 successes",
                    "5 blocked",
                    "5 packet",
                    "mean = 5",
                    "mean=5",
                    "mean of 5",
                    "average of 5",
                    "average = 5",
                    "μ = 5",
                    "μ=5",
                    "μ≈5",
                    "λ = 5",
                    "λ=5",
                    "λ≈5",
                    "lambda = 5",
                    "lambda=5",
                    "np = 5",
                    "np=5",
                    "np ≈ 5",
                    "n*p = 5",
                    "n*p=5",
                    "n × p = 5",
                    "n·p = 5",
                    "= 5.0",
                    "=5.0",
                    "equals 5",
                    # Phrased without "expected value" label but still states the result
                    " = 5 ",
                    " = 5,",
                    " = 5.",
                    "is 5,",
                    "is 5.",
                    "is 5\n",
                    "equals 5.",
                    "the mean is 5",
                    "mean is 5",
                    "5000 × 0.001",
                    "5000*0.001",
                    "5,000 × 0.001",
                    "n * p = 5",
                    # Approximation forms the model may use
                    "approximately 5",
                    "≈ 5",
                    "about 5",
                    "roughly 5",
                    # Bare "is 5" without punctuation constraint
                    "is 5",
                    "value of 5",
                    "result is 5",
                    # Lowercase-x multiplication (model may not use × symbol)
                    "5000 x 0.001",
                ],
            },
            {
                "type": "any_of",
                "label": "Approximation or exact method noted",
                "keywords": [
                    "poisson",
                    "approximation",
                    "lambda",
                    "normal approximation",
                    "gaussian",
                    "central limit",
                    "exact binomial",
                    "complement",
                    "cdf",
                ],
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Multiple interpretations",
                "critical": False,
                "keywords": [
                    "interpretation",
                    "approach",
                    "alternatively",
                    "note that",
                    "strictly",
                    "strictly greater",
                    "ambiguity",
                    "or more",
                    "at least",
                    "clarif",
                    "≥",
                    ">10",
                    "greater than 10",
                    "more than 10",
                    "unclear",
                    "depend",
                ],
            },
        ],
    },
    # ── D1 pandas equivalent (moved from capability probe; keyword-graded) ──
    {
        "id": "P-DA07",
        "name": "Pandas — Top Spenders Aggregation",
        "section": "auto-data",
        "model_slug": "auto-data",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Using pandas, write a function `top_spenders(rows)` where rows is a list "
            "of dicts with keys 'user' and 'amount'. Return a list of (user, total_amount) "
            "tuples for the top 2 users by total amount, descending. "
            "Include the import. One code block, module scope."
        ),
        "assertions": [
            {"type": "has_code", "label": "Code block present"},
            {
                "type": "any_of",
                "label": "pandas imported",
                "keywords": ["import pandas", "import pd", "from pandas"],
            },
            {
                "type": "any_of",
                "label": "groupby or aggregation used",
                "keywords": ["groupby", "group_by", "agg(", "sum()", ".sum(", "pivot"],
            },
            {
                "type": "any_of",
                "label": "Sort descending",
                "keywords": ["sort_values", "nlargest", "ascending=false", "descending"],
            },
            {
                "type": "any_of",
                "label": "Returns tuples or list",
                "keywords": ["tuple", "tolist", "itertuples", "iterrows", "zip(", "return ["],
            },
        ],
    },
]
