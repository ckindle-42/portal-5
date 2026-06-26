# Copyright © 2025 Apple Inc.
# Laguna (Poolside AI) model for mlx-lm.
# Architecture: 256-expert MoE, mixed full/sliding-window attention,
# per-layer head count, per-head gating, YaRN RoPE for full layers.

from dataclasses import dataclass, field
from typing import Any

import mlx.core as mx
import mlx.nn as nn

from .base import BaseModelArgs, create_attention_mask, scaled_dot_product_attention
from .cache import KVCache, RotatingKVCache
from .rope_utils import initialize_rope
from .switch_layers import SwitchGLU


@dataclass
class ModelArgs(BaseModelArgs):
    model_type: str = "laguna"
    vocab_size: int = 100352
    hidden_size: int = 2048
    num_hidden_layers: int = 40
    num_attention_heads: int = 64
    num_key_value_heads: int = 8
    intermediate_size: int = 8192
    moe_intermediate_size: int = 512
    shared_expert_intermediate_size: int = 512
    num_experts: int = 256
    num_experts_per_tok: int = 8
    max_position_embeddings: int = 131072
    rms_norm_eps: float = 1e-6
    sliding_window: int = 512
    gating: bool = True
    moe_routed_scaling_factor: float = 2.5
    moe_apply_router_weight_on_input: bool = False
    partial_rotary_factor: float = 0.5
    attention_bias: bool = False
    head_dim: int = 128
    tie_word_embeddings: bool = False
    layer_types: list[str] = field(default_factory=list)
    mlp_layer_types: list[str] = field(default_factory=list)
    num_attention_heads_per_layer: list[int] = field(default_factory=list)
    rope_parameters: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.layer_types:
            # Default: 1 full + 3 sliding per 4-layer block
            self.layer_types = [
                "full_attention" if i % 4 == 0 else "sliding_attention"
                for i in range(self.num_hidden_layers)
            ]
        if not self.mlp_layer_types:
            # Default: first layer dense, rest sparse MoE
            self.mlp_layer_types = ["dense"] + ["sparse"] * (
                self.num_hidden_layers - 1
            )
        if not self.num_attention_heads_per_layer:
            self.num_attention_heads_per_layer = [
                self.num_attention_heads
            ] * self.num_hidden_layers


class MoEGate(nn.Module):
    def __init__(self, hidden_size: int, n_experts: int):
        super().__init__()
        # mlx-community conversion stores as gate.proj (matching LagunaTopKRouter.proj)
        self.proj = nn.Linear(hidden_size, n_experts, bias=False)
        self.e_score_correction_bias = mx.zeros((n_experts,))

    def __call__(self, x: mx.array):
        scores = mx.sigmoid(self.proj(x).astype(mx.float32))
        # Bias shifts scores for top-k selection only (original scores used for weights)
        return scores, scores + self.e_score_correction_bias


class MLP(nn.Module):
    def __init__(self, hidden_size: int, intermediate_size: int):
        super().__init__()
        self.gate_proj = nn.Linear(hidden_size, intermediate_size, bias=False)
        self.up_proj = nn.Linear(hidden_size, intermediate_size, bias=False)
        self.down_proj = nn.Linear(intermediate_size, hidden_size, bias=False)

    def __call__(self, x: mx.array) -> mx.array:
        return self.down_proj(nn.silu(self.gate_proj(x)) * self.up_proj(x))


class LagunaSparseMoE(nn.Module):
    def __init__(self, args: ModelArgs):
        super().__init__()
        hidden = args.hidden_size
        n_experts = args.num_experts

        self.top_k = args.num_experts_per_tok
        self.routed_scaling_factor = args.moe_routed_scaling_factor

        self.gate = MoEGate(hidden, n_experts)
        self.switch_mlp = SwitchGLU(hidden, args.moe_intermediate_size, n_experts)
        self.shared_expert = MLP(hidden, args.shared_expert_intermediate_size)

    def __call__(self, x: mx.array) -> mx.array:
        scores, biased_scores = self.gate(x)

        k = self.top_k
        inds = mx.argpartition(-biased_scores, kth=k - 1, axis=-1)[..., :k]
        weights = mx.take_along_axis(scores, inds, axis=-1)
        # Normalize weights to sum=1 (matching LagunaTopKRouter behavior), then
        # apply routed_scaling_factor to the aggregated output (not per-weight).
        weights = weights / weights.sum(axis=-1, keepdims=True)
        weights = weights.astype(x.dtype)

        y = self.switch_mlp(x, inds)
        y = (y * weights[..., None]).sum(axis=-2)
        y = y * self.routed_scaling_factor
        y = y + self.shared_expert(x)
        return y.astype(x.dtype)


class Attention(nn.Module):
    def __init__(self, args: ModelArgs, layer_idx: int):
        super().__init__()

        hidden = args.hidden_size
        n_heads = args.num_attention_heads_per_layer[layer_idx]
        n_kv_heads = args.num_key_value_heads
        head_dim = args.head_dim

        self.n_heads = n_heads
        self.n_kv_heads = n_kv_heads
        self.head_dim = head_dim
        self.scale = head_dim**-0.5

        self.q_proj = nn.Linear(hidden, n_heads * head_dim, bias=args.attention_bias)
        self.k_proj = nn.Linear(
            hidden, n_kv_heads * head_dim, bias=args.attention_bias
        )
        self.v_proj = nn.Linear(
            hidden, n_kv_heads * head_dim, bias=args.attention_bias
        )
        self.o_proj = nn.Linear(n_heads * head_dim, hidden, bias=False)

        self.q_norm = nn.RMSNorm(head_dim, eps=args.rms_norm_eps)
        self.k_norm = nn.RMSNorm(head_dim, eps=args.rms_norm_eps)

        # Per-head output gating: gate = softplus(g_proj(x))
        if args.gating:
            self.g_proj = nn.Linear(hidden, n_heads, bias=False)

        # Per-layer RoPE: YaRN for full attention, default for sliding
        layer_type = args.layer_types[layer_idx]
        self.is_sliding = layer_type == "sliding_attention"

        rope_params = args.rope_parameters.get(layer_type, {})
        rope_theta = rope_params.get("rope_theta", 10000.0)
        rope_type = rope_params.get("rope_type", "default")
        partial_factor = rope_params.get("partial_rotary_factor", 1.0)
        rope_dims = int(head_dim * partial_factor)

        if rope_type == "yarn":
            factor = rope_params.get("factor", 32.0)
            scaling_config = {
                "rope_type": "yarn",
                "factor": factor,
                "original_max_position_embeddings": rope_params.get(
                    "original_max_position_embeddings",
                    int(args.max_position_embeddings / factor),
                ),
                "beta_fast": rope_params.get("beta_fast", 64.0),
                "beta_slow": rope_params.get("beta_slow", 1.0),
            }
            self.rope = initialize_rope(
                rope_dims,
                rope_theta,
                traditional=False,
                scaling_config=scaling_config,
                max_position_embeddings=args.max_position_embeddings,
            )
        else:
            self.rope = nn.RoPE(rope_dims, traditional=False, base=rope_theta)

    def __call__(
        self,
        x: mx.array,
        mask: mx.array | None = None,
        cache: Any | None = None,
    ) -> mx.array:
        B, L, _ = x.shape

        # QKV projections with per-head RMSNorm
        q = self.q_norm(
            self.q_proj(x).reshape(B, L, self.n_heads, self.head_dim)
        ).transpose(0, 2, 1, 3)
        k = self.k_norm(
            self.k_proj(x).reshape(B, L, self.n_kv_heads, self.head_dim)
        ).transpose(0, 2, 1, 3)
        v = self.v_proj(x).reshape(B, L, self.n_kv_heads, self.head_dim).transpose(
            0, 2, 1, 3
        )

        if cache is not None:
            q = self.rope(q, offset=cache.offset)
            k = self.rope(k, offset=cache.offset)
            k, v = cache.update_and_fetch(k, v)
        else:
            q = self.rope(q)
            k = self.rope(k)

        out = scaled_dot_product_attention(
            q, k, v, cache=cache, scale=self.scale, mask=mask
        )
        out = out.transpose(0, 2, 1, 3).reshape(B, L, -1)

        if hasattr(self, "g_proj"):
            gate = nn.softplus(self.g_proj(x)).reshape(B, L, self.n_heads, 1)
            out = (out.reshape(B, L, self.n_heads, self.head_dim) * gate).reshape(
                B, L, -1
            )

        return self.o_proj(out)


class DecoderLayer(nn.Module):
    def __init__(self, args: ModelArgs, layer_idx: int):
        super().__init__()
        self.self_attn = Attention(args, layer_idx)
        mlp_type = args.mlp_layer_types[layer_idx]
        self.mlp = (
            LagunaSparseMoE(args) if mlp_type == "sparse" else MLP(
                args.hidden_size, args.intermediate_size
            )
        )
        self.input_layernorm = nn.RMSNorm(args.hidden_size, eps=args.rms_norm_eps)
        self.post_attention_layernorm = nn.RMSNorm(
            args.hidden_size, eps=args.rms_norm_eps
        )

    def __call__(
        self,
        x: mx.array,
        mask: mx.array | None = None,
        cache: Any | None = None,
    ) -> mx.array:
        r = self.self_attn(self.input_layernorm(x), mask, cache)
        h = x + r
        r = self.mlp(self.post_attention_layernorm(h))
        return h + r


class LagunaModel(nn.Module):
    def __init__(self, args: ModelArgs):
        super().__init__()
        self.args = args
        self.embed_tokens = nn.Embedding(args.vocab_size, args.hidden_size)
        self.layers = [
            DecoderLayer(args, i) for i in range(args.num_hidden_layers)
        ]
        self.norm = nn.RMSNorm(args.hidden_size, eps=args.rms_norm_eps)

    def __call__(
        self,
        inputs: mx.array,
        cache: Any | None = None,
    ) -> mx.array:
        h = self.embed_tokens(inputs)

        if cache is None:
            cache = [None] * len(self.layers)

        # Build two masks: one full-context, one sliding-window
        full_mask = create_attention_mask(h, cache[0])
        has_sliding = any(
            l.self_attn.is_sliding for l in self.layers
        )
        if has_sliding:
            # Find the first sliding cache to generate the correct sliding mask
            sliding_cache = next(
                (c for c, l in zip(cache, self.layers) if l.self_attn.is_sliding),
                None,
            )
            sliding_mask = create_attention_mask(
                h,
                sliding_cache,
                window_size=self.args.sliding_window,
            )
        else:
            sliding_mask = full_mask

        for layer, c in zip(self.layers, cache):
            mask = sliding_mask if layer.self_attn.is_sliding else full_mask
            h = layer(h, mask, c)

        return self.norm(h)


class Model(nn.Module):
    def __init__(self, args: ModelArgs):
        super().__init__()
        self.args = args
        self.model_type = args.model_type
        self.model = LagunaModel(args)
        if not args.tie_word_embeddings:
            self.lm_head = nn.Linear(args.hidden_size, args.vocab_size, bias=False)

    def __call__(
        self,
        inputs: mx.array,
        cache: Any | None = None,
    ) -> mx.array:
        out = self.model(inputs, cache)
        if self.args.tie_word_embeddings:
            out = self.model.embed_tokens.as_linear(out)
        else:
            out = self.lm_head(out)
        return out

    def make_cache(self):
        caches = []
        for layer in self.model.layers:
            if layer.self_attn.is_sliding:
                caches.append(RotatingKVCache(max_size=self.args.sliding_window))
            else:
                caches.append(KVCache())
        return caches

    def sanitize(self, weights: dict) -> dict:
        # Remove lm_head if tied
        if self.args.tie_word_embeddings:
            weights.pop("lm_head.weight", None)

        # Remove RoPE buffers (computed at runtime in mlx-lm)
        weights = {
            k: v
            for k, v in weights.items()
            if "rotary_emb" not in k
        }

        result = {}
        for l in range(self.args.num_hidden_layers):
            pfx = f"model.layers.{l}"
            mlp_type = self.args.mlp_layer_types[l]
            n_experts = self.args.num_experts
            moe_size = self.args.moe_intermediate_size

            if mlp_type == "sparse":
                # Remap gate: LagunaTopKRouter.weight → MoEGate.weight
                # (names already match: mlp.gate.weight, mlp.gate.e_score_correction_bias)

                # Split experts.gate_up_proj → switch_mlp.gate_proj + switch_mlp.up_proj
                for suffix in ["weight", "scales", "biases"]:
                    src_key = f"{pfx}.mlp.experts.gate_up_proj.{suffix}"
                    if src_key in weights:
                        gate_up = weights.pop(src_key)
                        # gate_up shape: [n_experts, 2*moe_size, hidden] (or quantized variant)
                        # For quantized: gate_up is [n_experts, 2*moe_size // group, hidden] (scales/biases)
                        split_dim = gate_up.shape[1] // 2
                        result[f"{pfx}.mlp.switch_mlp.gate_proj.{suffix}"] = gate_up[
                            :, :split_dim, :
                        ]
                        result[f"{pfx}.mlp.switch_mlp.up_proj.{suffix}"] = gate_up[
                            :, split_dim:, :
                        ]
                    # Also handle per-expert naming (fallback)
                    src_gate = f"{pfx}.mlp.experts.gate_proj.{suffix}"
                    if src_gate in weights:
                        result[f"{pfx}.mlp.switch_mlp.gate_proj.{suffix}"] = weights.pop(src_gate)
                    src_up = f"{pfx}.mlp.experts.up_proj.{suffix}"
                    if src_up in weights:
                        result[f"{pfx}.mlp.switch_mlp.up_proj.{suffix}"] = weights.pop(src_up)

                # Remap experts.down_proj → switch_mlp.down_proj
                for suffix in ["weight", "scales", "biases"]:
                    src_down = f"{pfx}.mlp.experts.down_proj.{suffix}"
                    if src_down in weights:
                        result[f"{pfx}.mlp.switch_mlp.down_proj.{suffix}"] = weights.pop(src_down)

                # Handle per-expert stacking (if individual expert weights exist)
                for n in ["gate_proj", "up_proj", "down_proj"]:
                    e0_key = f"{pfx}.mlp.experts.0.{n}.weight"
                    if e0_key in weights:
                        stacked = mx.stack([
                            weights.pop(f"{pfx}.mlp.experts.{e}.{n}.weight")
                            for e in range(n_experts)
                        ])
                        result[f"{pfx}.mlp.switch_mlp.{n}.weight"] = stacked

        # Pass through any remaining weights unchanged
        for k, v in weights.items():
            if k not in result:
                result[k] = v

        return result

    @property
    def layers(self):
        return self.model.layers
