"""Per-category quality signal definitions.

Used by both bench_tps and the UAT driver to score response quality
beyond raw TPS or keyword presence. A response gets quality_score in
[0.0, 1.0] = (signals_found / signals_expected).

Signals are tuned to the prompt library in tests/benchmarks/bench_tps.py
PROMPTS dict. If you change a category's prompt, update its signals here.
"""

QUALITY_SIGNALS: dict[str, list[str]] = {
    "general": [
        # Prompt asks for OSI 7 layers with protocol examples
        "physical",
        "data link",
        "network",
        "transport",
        "session",
        "presentation",
        "application",
    ],
    "coding": [
        # Prompt asks for merge_intervals function
        "def merge_intervals",
        "list",
        "tuple",
        "intervals.sort",
        "merged",
        "overlap",
    ],
    "security": [
        # Prompt asks for SSH brute-force MITRE ATT&CK analysis
        "T1110",
        "MITRE",
        "ATT&CK",
        "containment",
        "detection",
        "block",
    ],
    "reasoning": [
        # Prompt asks for ER bottleneck analysis
        "bottleneck",
        "doctor",
        "nurse",
        "bed",
        "wait",
        "minute",
    ],
    "creative": [
        # Prompt asks for noir detective opening, memory-as-currency
        "memory",
        "detective",
        "city",
        "rain",
    ],
    "vision": [
        # Prompt is meta — describe the analysis framework
        "objects",
        "text",
        "scene",
        "anomalies",
        "confidence",
    ],
}


def quality_score(category: str, response_text: str) -> float:
    """Return a quality score in [0.0, 1.0] for the given category and response.

    Signals match case-insensitively. Score is signals-found / signals-expected.
    Categories without defined signals return 1.0 (don't penalize).
    """
    signals = QUALITY_SIGNALS.get(category, [])
    if not signals:
        return 1.0
    response_lower = response_text.lower()
    found = sum(1 for s in signals if s.lower() in response_lower)
    return found / len(signals)
