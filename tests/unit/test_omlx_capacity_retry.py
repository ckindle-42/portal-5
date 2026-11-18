"""oMLX capacity refusals (the 400 prefill guard, the 507 load ceiling) free idle Ollama once and
retry oMLX, on every path; a free never takes a busy or protected Ollama model; a refusal that
survives still falls back to the next candidate, and only an exhausted chain reports capacity."""

from __future__ import annotations

from portal.platform.inference.router.non_streaming import (
    is_omlx_capacity_refusal,
    is_omlx_prefill_refusal,
)

LOAD_CEILING = (
    b'{"error":{"message":"Model \'unsloth--Qwen3.6-35B-A3B-UD-MLX-4bit\' (21.16GB) does not fit '
    b'under the dynamic memory ceiling (8.12GB). Close other apps to free RAM"}}'
)

PREFILL_GUARD = b'{"error":{"message":"prefill memory guard: would exceed the memory ceiling"}}'


def test_the_predicate_matches_both_omlx_refusals_and_nothing_else() -> None:
    assert is_omlx_capacity_refusal(507, LOAD_CEILING)
    assert is_omlx_capacity_refusal(400, PREFILL_GUARD)
    assert is_omlx_prefill_refusal(400, PREFILL_GUARD)
    assert not is_omlx_prefill_refusal(507, LOAD_CEILING)
    assert not is_omlx_prefill_refusal(400, b'{"error":"invalid parameter temperature"}')
    assert not is_omlx_capacity_refusal(400, b'{"error":"invalid parameter temperature"}')
    assert not is_omlx_capacity_refusal(500, LOAD_CEILING)
