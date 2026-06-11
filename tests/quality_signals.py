"""Per-category quality signal definitions.

Used by both bench_tps and the UAT driver to score response quality
beyond raw TPS or keyword presence. A response gets quality_score in
[0.0, 1.0] = (signals_found / signals_expected).

Signals are tuned to the prompt library in tests/benchmarks/bench_tps.py
PROMPTS dict. If you change a category's prompt, update its signals here.

A signal may be a string (exact substring match) or a tuple of strings
(OR group: any one match counts as one signal hit).
"""

QUALITY_SIGNALS: dict[str, list] = {
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
        # Prompt asks for ER bottleneck analysis.
        # Tuple = OR group: any one term counts as one hit.
        # auto-compliance uses formal math notation ("capacity" instead of
        # "bottleneck", fractional hours instead of "minute").
        ("bottleneck", "capacity"),
        "doctor",
        "nurse",
        "bed",
        ("wait", "arrival"),
        ("minute", "hour"),
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
    "math": [
        # Prompt: train meeting (answer: 11:00 AM, 180 km from X),
        # combinatorics team (answer: 50), quadratic (answer: n=3, n=-6)
        "180",    # km from Station X — correct train meeting distance
        "11",     # 11:00 AM meeting time
        "50",     # correct combinatorics answer: C(5,2)*C(4,1) + C(5,3)*C(4,0) = 50
        "factor", # factoring the quadratic n²+3n-18
        "-6",     # correct root of quadratic
        "n = 3",  # other root (with space — avoids false match on "n=3" inside words)
    ],
}


def quality_score(category: str, response_text: str) -> float:
    """Return a quality score in [0.0, 1.0] for the given category and response.

    Signals match case-insensitively. Score is signals-found / signals-expected.
    A signal may be a string (single keyword) or a tuple (OR group: any one hit counts).
    Categories without defined signals return 1.0 (don't penalize).
    """
    signals = QUALITY_SIGNALS.get(category, [])
    if not signals:
        return 1.0
    response_lower = response_text.lower()
    found = 0
    for sig in signals:
        if isinstance(sig, tuple):
            found += any(s.lower() in response_lower for s in sig)
        else:
            found += sig.lower() in response_lower
    return found / len(signals)
