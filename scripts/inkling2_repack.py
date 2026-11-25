#!/usr/bin/env python3
"""Stream BF16 Inkling 2 experts into the base NVFP4/MXFP8 safetensors layout."""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import shutil
import struct
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

DEFAULT_SOURCE = Path("/Volumes/data01/hf-cache/orcarouter-inkling-2-mini-abliterated")
DEFAULT_OUTPUT = Path("/Volumes/data01/omlx-staging/inkling2-abl-packed")
NVFP4_LAYER_COUNT = 20
NVFP4_SCALE_DENOMINATOR = 2688.0
COPY_CHUNK_BYTES = 8 * 1024 * 1024
DEFAULT_SHARD_BYTES = 4 * 1024**3
DTYPE_BYTES = {
    "BOOL": 1,
    "U8": 1,
    "I8": 1,
    "F8_E4M3": 1,
    "F8_E5M2": 1,
    "F16": 2,
    "BF16": 2,
    "U16": 2,
    "I16": 2,
    "F32": 4,
    "U32": 4,
    "I32": 4,
    "F64": 8,
    "U64": 8,
    "I64": 8,
}
ROUND_TRIP_EXPERTS = (0, 1, 127)
ROUND_TRIP_PROJECTIONS = {(0, "w13"), (19, "w2"), (20, "w13"), (23, "w2")}
EXPERT_KEY = re.compile(
    r"model\.llm\.layers\.(?P<layer>\d+)\.mlp\.experts\.(?P<projection>w13|w2)_weight"
)


@dataclass(frozen=True)
class TensorInfo:
    """One tensor's header metadata and data-section offsets."""

    name: str
    dtype: str
    shape: tuple[int, ...]
    start: int
    end: int

    @property
    def nbytes(self) -> int:
        return self.end - self.start


class SafetensorsReader:
    """Read tensor headers and contiguous byte ranges without materializing a shard."""

    def __init__(self, path: Path):
        self.path = path
        self.handle: BinaryIO | None = None
        self.data_start = 0
        self.metadata: dict[str, str] = {}
        self.tensors: dict[str, TensorInfo] = {}

    def __enter__(self) -> SafetensorsReader:
        self.handle = self.path.open("rb")
        header_size_raw = self.handle.read(8)
        if len(header_size_raw) != 8:
            raise ValueError(f"invalid safetensors prefix: {self.path}")
        header_size = struct.unpack("<Q", header_size_raw)[0]
        header = json.loads(self.handle.read(header_size))
        self.data_start = 8 + header_size
        self.metadata = header.pop("__metadata__", {})
        for name, item in header.items():
            start, end = item["data_offsets"]
            self.tensors[name] = TensorInfo(
                name=name,
                dtype=item["dtype"],
                shape=tuple(item["shape"]),
                start=start,
                end=end,
            )
        return self

    def __exit__(self, *_: object) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None

    def tensor_info(self, name: str) -> TensorInfo:
        return self.tensors[name]

    def read_tensor_region(self, name: str, offset: int, nbytes: int) -> bytes:
        if self.handle is None:
            raise RuntimeError("safetensors reader is closed")
        info = self.tensor_info(name)
        if offset < 0 or nbytes < 0 or offset + nbytes > info.nbytes:
            raise ValueError(f"tensor byte range is outside {name}")
        self.handle.seek(self.data_start + info.start + offset)
        raw = self.handle.read(nbytes)
        if len(raw) != nbytes:
            raise ValueError(f"truncated tensor data in {self.path}: {name}")
        return raw

    def iter_tensor_bytes(self, name: str, chunk_bytes: int = COPY_CHUNK_BYTES) -> Iterator[bytes]:
        if self.handle is None:
            raise RuntimeError("safetensors reader is closed")
        info = self.tensor_info(name)
        self.handle.seek(self.data_start + info.start)
        remaining = info.nbytes
        while remaining:
            raw = self.handle.read(min(chunk_bytes, remaining))
            if not raw:
                raise ValueError(f"truncated tensor data in {self.path}: {name}")
            remaining -= len(raw)
            yield raw


class SafetensorsStreamWriter:
    """Write safetensors shards from one tensor's byte stream at a time."""

    def __init__(
        self,
        directory: Path,
        max_shard_bytes: int = DEFAULT_SHARD_BYTES,
        metadata: dict[str, str] | None = None,
    ):
        self.directory = directory
        self.max_shard_bytes = max_shard_bytes
        self.metadata = metadata or {"format": "pt"}
        self.weight_map: dict[str, str] = {}
        self.shard_names: list[str] = []
        self.total_size = 0
        self._current_file: BinaryIO | None = None
        self._current_path: Path | None = None
        self._current_name = ""
        self._current_size = 0
        self._current_tensors: dict[str, dict[str, object]] = {}
        self._start_shard()

    def _start_shard(self) -> None:
        number = len(self.shard_names) + 1
        self._current_name = f"model-{number:05d}.safetensors"
        self._current_path = self.directory / f".{self._current_name}.data"
        self._current_file = self._current_path.open("wb")
        self._current_size = 0
        self._current_tensors = {}

    def _roll_shard_if_needed(self, tensor_bytes: int) -> None:
        if self._current_tensors and self._current_size + tensor_bytes > self.max_shard_bytes:
            self._finish_shard()
            self._start_shard()

    def add_bytes(self, name: str, dtype: str, shape: tuple[int, ...], raw: bytes) -> None:
        self.add_chunks(name, dtype, shape, (raw,), len(raw))

    def add_file(
        self,
        name: str,
        dtype: str,
        shape: tuple[int, ...],
        path: Path,
        nbytes: int,
    ) -> None:
        def chunks() -> Iterator[bytes]:
            with path.open("rb") as handle:
                while raw := handle.read(COPY_CHUNK_BYTES):
                    yield raw

        self.add_chunks(name, dtype, shape, chunks(), nbytes)

    def add_chunks(
        self,
        name: str,
        dtype: str,
        shape: tuple[int, ...],
        chunks: Iterable[bytes],
        nbytes: int,
    ) -> None:
        if name in self.weight_map or name in self._current_tensors:
            raise ValueError(f"duplicate safetensors key: {name}")
        expected = tensor_size(dtype, shape)
        if expected != nbytes:
            raise ValueError(f"{name} has {nbytes} bytes but metadata requires {expected}")
        self._roll_shard_if_needed(nbytes)
        if self._current_file is None:
            raise RuntimeError("safetensors writer is closed")
        start = self._current_size
        written = 0
        for raw in chunks:
            self._current_file.write(raw)
            written += len(raw)
        if written != nbytes:
            raise ValueError(f"{name} stream wrote {written} bytes, expected {nbytes}")
        self._current_size += written
        self.total_size += written
        self._current_tensors[name] = {
            "dtype": dtype,
            "shape": list(shape),
            "data_offsets": [start, self._current_size],
        }
        self.weight_map[name] = self._current_name

    def _finish_shard(self) -> None:
        if not self._current_tensors:
            return
        if self._current_file is None or self._current_path is None:
            raise RuntimeError("safetensors writer is closed")
        self._current_file.flush()
        self._current_file.close()
        header = dict(self._current_tensors)
        header["__metadata__"] = self.metadata
        raw_header = json.dumps(header, separators=(",", ":")).encode("utf-8")
        raw_header += b" " * (-len(raw_header) % 8)
        final_path = self.directory / self._current_name
        temporary_path = final_path.with_suffix(".safetensors.tmp")
        with temporary_path.open("wb") as output, self._current_path.open("rb") as data:
            output.write(struct.pack("<Q", len(raw_header)))
            output.write(raw_header)
            shutil.copyfileobj(data, output, length=COPY_CHUNK_BYTES)
        os.replace(temporary_path, final_path)
        self._current_path.unlink()
        self.shard_names.append(self._current_name)
        self._current_file = None
        self._current_path = None
        self._current_tensors = {}

    def finish(self) -> None:
        self._finish_shard()


def tensor_size(dtype: str, shape: tuple[int, ...]) -> int:
    if dtype not in DTYPE_BYTES:
        raise ValueError(f"unsupported safetensors dtype: {dtype}")
    count = 1
    for size in shape:
        count *= size
    return count * DTYPE_BYTES[dtype]


def expert_format(layer: int) -> str:
    if 0 <= layer < NVFP4_LAYER_COUNT:
        return "nvfp4"
    if NVFP4_LAYER_COUNT <= layer < 24:
        return "mxfp8"
    raise ValueError(f"Inkling 2 layer is outside the 24-layer base layout: {layer}")


def _mx_bytes(array, mx) -> bytes:
    return array.view(mx.uint8).__array__().tobytes(order="C")


def _mx_scalar(array) -> float:
    return float(array)


def _quantize_one_expert(source, fmt: str, mx, with_round_trip: bool):
    source32 = source.astype(mx.float32)
    if fmt == "nvfp4":
        global_scale = mx.max(mx.abs(source32))
        qweight, scales = mx.quantize(
            source,
            group_size=16,
            bits=4,
            mode="nvfp4",
            global_scale=global_scale,
        )
        reconstructed = None
        if with_round_trip:
            reconstructed = mx.dequantize(
                qweight,
                scales,
                None,
                group_size=16,
                bits=4,
                mode="nvfp4",
                global_scale=global_scale,
                dtype=mx.float32,
            )
    else:
        global_scale = None
        qweight, scales = mx.quantize(source, group_size=32, bits=8, mode="mxfp8")
        reconstructed = None
        if with_round_trip:
            reconstructed = mx.dequantize(
                qweight,
                scales,
                None,
                group_size=32,
                bits=8,
                mode="mxfp8",
                dtype=mx.float32,
            )
    return source32, qweight, scales, global_scale, reconstructed


def _record_round_trip(
    metrics: list[dict[str, object]],
    key: str,
    expert: int,
    fmt: str,
    source32,
    reconstructed,
    mx,
) -> None:
    error = mx.abs(reconstructed - source32)
    mx.eval(error)
    metrics.append(
        {
            "key": key,
            "expert": expert,
            "format": fmt,
            "max_abs_error": _mx_scalar(mx.max(error)),
            "mean_abs_error": _mx_scalar(mx.mean(error)),
        }
    )


def _temporary_output(directory: Path, prefix: str) -> tuple[Path, BinaryIO]:
    descriptor, filename = tempfile.mkstemp(prefix=prefix, dir=directory)
    return Path(filename), os.fdopen(descriptor, "wb")


def _write_quantized_outputs(
    writer: SafetensorsStreamWriter,
    info: TensorInfo,
    fmt: str,
    experts: int,
    rows: int,
    columns: int,
    amax_values: list[float],
    q_path: Path,
    scale_path: Path,
) -> None:
    base = info.name[: -len("_weight")]
    if fmt == "nvfp4":
        q_dtype, q_shape = "U8", (experts, rows, columns // 2)
        scale_dtype = "F8_E4M3"
    else:
        q_dtype, q_shape = "F8_E4M3", info.shape
        scale_dtype = "U8"
    group_size = 16 if fmt == "nvfp4" else 32
    writer.add_file(info.name, q_dtype, q_shape, q_path, q_path.stat().st_size)
    writer.add_file(
        f"{base}_weight_scale",
        scale_dtype,
        (experts, rows, columns // group_size),
        scale_path,
        scale_path.stat().st_size,
    )
    if fmt == "nvfp4":
        writer.add_bytes(
            f"{base}_weight_amax",
            "F32",
            (experts,),
            struct.pack(f"<{experts}f", *amax_values),
        )
        writer.add_bytes(
            f"{base}_weight_outer_scale_denominator",
            "F32",
            (1,),
            struct.pack("<f", NVFP4_SCALE_DENOMINATOR),
        )


def _quantize_expert_tensor(
    reader: SafetensorsReader,
    info: TensorInfo,
    layer: int,
    projection: str,
    temporary_directory: Path,
    writer: SafetensorsStreamWriter,
    round_trip_metrics: list[dict[str, object]],
) -> None:
    import mlx.core as mx
    import numpy as np

    fmt = expert_format(layer)
    experts, rows, columns = info.shape
    expert_bytes = rows * columns * DTYPE_BYTES["BF16"]
    if info.dtype != "BF16":
        raise ValueError(f"expected BF16 source expert, found {info.dtype}: {info.name}")
    q_path, q_tmp = _temporary_output(temporary_directory, ".inkling2-q-")
    scale_path, scale_tmp = _temporary_output(temporary_directory, ".inkling2-scale-")
    amax_values: list[float] = []
    sample_experts = ROUND_TRIP_EXPERTS if (layer, projection) in ROUND_TRIP_PROJECTIONS else ()
    try:
        for expert in range(experts):
            raw = reader.read_tensor_region(info.name, expert * expert_bytes, expert_bytes)
            source = mx.array(np.frombuffer(raw, dtype="<u2").copy())
            source = source.view(mx.bfloat16).reshape((rows, columns))
            source32, qweight, scales, global_scale, reconstructed = _quantize_one_expert(
                source, fmt, mx, expert in sample_experts
            )
            mx.eval(qweight, scales)
            if fmt == "nvfp4":
                amax_values.append(_mx_scalar(global_scale))
            q_tmp.write(_mx_bytes(qweight, mx))
            scale_tmp.write(_mx_bytes(scales, mx))
            if expert in sample_experts:
                mx.eval(reconstructed)
                _record_round_trip(
                    round_trip_metrics,
                    info.name,
                    expert,
                    fmt,
                    source32,
                    reconstructed,
                    mx,
                )
            del raw, source, source32, qweight, scales, global_scale
            if expert % 16 == 15:
                mx.clear_cache()
                gc.collect()
        q_tmp.close()
        scale_tmp.close()
        _write_quantized_outputs(
            writer,
            info,
            fmt,
            experts,
            rows,
            columns,
            amax_values,
            q_path,
            scale_path,
        )
    finally:
        q_tmp.close()
        scale_tmp.close()
        q_path.unlink(missing_ok=True)
        scale_path.unlink(missing_ok=True)


def _copy_metadata_and_mtp(source: Path, destination: Path) -> None:
    for path in source.iterdir():
        if not path.is_file() or path.name == "model.safetensors.index.json":
            continue
        if path.name == "mtp.safetensors" or path.suffix != ".safetensors":
            shutil.copy2(path, destination / path.name)


def _open_model_readers(
    stack: ExitStack, source: Path, model_files: list[str], source_map: dict[str, str]
) -> tuple[dict[str, SafetensorsReader], dict[str, str]]:
    readers = {name: stack.enter_context(SafetensorsReader(source / name)) for name in model_files}
    source_metadata: dict[str, str] | None = None
    all_names: set[str] = set()
    for filename, reader in readers.items():
        if source_metadata is None:
            source_metadata = reader.metadata
        elif source_metadata != reader.metadata:
            raise ValueError("model shard metadata does not match across source files")
        for name in reader.tensors:
            if source_map.get(name) != filename:
                raise ValueError(f"source index maps {name} to the wrong shard")
            all_names.add(name)
    if all_names != set(source_map):
        raise ValueError("source model index does not match its safetensors headers")
    return readers, source_metadata or {"format": "pt"}


def _stream_model_files(
    model_files: list[str],
    readers: dict[str, SafetensorsReader],
    partial: Path,
    writer: SafetensorsStreamWriter,
    round_trip_metrics: list[dict[str, object]],
) -> None:
    for filename in model_files:
        reader = readers[filename]
        infos = sorted(reader.tensors.values(), key=lambda item: item.start)
        for info in infos:
            expert = EXPERT_KEY.fullmatch(info.name)
            if expert is None:
                writer.add_chunks(
                    info.name,
                    info.dtype,
                    info.shape,
                    reader.iter_tensor_bytes(info.name),
                    info.nbytes,
                )
                continue
            _quantize_expert_tensor(
                reader,
                info,
                int(expert.group("layer")),
                expert.group("projection"),
                partial,
                writer,
                round_trip_metrics,
            )


def _write_model_index(partial: Path, writer: SafetensorsStreamWriter) -> None:
    index = {
        "metadata": {"total_size": writer.total_size},
        "weight_map": writer.weight_map,
    }
    (partial / "model.safetensors.index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n"
    )


def repack(source: Path, output: Path, max_shard_bytes: int) -> dict[str, object]:
    config = json.loads((source / "config.json").read_text())
    if config.get("model_type") != "inkling2_loop":
        raise ValueError(f"unexpected Inkling 2 model type: {config.get('model_type')}")
    if int(config.get("text_config", config).get("num_hidden_layers", 0)) != 24:
        raise ValueError("the supported Inkling 2 base layout has 24 hidden layers")
    partial = output.with_name(f"{output.name}.partial")
    if output.exists() or partial.exists():
        raise FileExistsError(f"output or partial path already exists: {output}")
    partial.mkdir(parents=True)
    _copy_metadata_and_mtp(source, partial)
    source_map = json.loads((source / "model.safetensors.index.json").read_text())["weight_map"]
    model_files = sorted(set(source_map.values()))
    round_trip_metrics: list[dict[str, object]] = []
    with ExitStack() as stack:
        readers, metadata = _open_model_readers(stack, source, model_files, source_map)
        writer = SafetensorsStreamWriter(partial, max_shard_bytes, metadata)
        _stream_model_files(model_files, readers, partial, writer, round_trip_metrics)
        writer.finish()
    _write_model_index(partial, writer)
    model_storage_bytes = sum((partial / name).stat().st_size for name in writer.shard_names)
    partial.rename(output)
    return {
        "model_tensor_keys": len(writer.weight_map),
        "output_shards": writer.shard_names,
        "model_storage_bytes": model_storage_bytes,
        "calibration_footprint_estimate_bytes": model_storage_bytes,
        "round_trip_samples": round_trip_metrics,
        "output": str(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-shard-gib", type=float, default=4.0)
    args = parser.parse_args()
    if args.max_shard_gib <= 0:
        parser.error("--max-shard-gib must be positive")
    result = repack(args.source, args.output, int(args.max_shard_gib * 1024**3))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
