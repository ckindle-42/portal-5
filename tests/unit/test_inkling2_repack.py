from scripts.inkling2_repack import (
    SafetensorsReader,
    SafetensorsStreamWriter,
    expert_format,
)


def test_expert_format_follows_base_layer_split() -> None:
    assert [expert_format(layer) for layer in (0, 19, 20, 23)] == [
        "nvfp4",
        "nvfp4",
        "mxfp8",
        "mxfp8",
    ]


def test_stream_writer_round_trips_tensor_bytes(tmp_path) -> None:
    writer = SafetensorsStreamWriter(tmp_path, max_shard_bytes=4)
    writer.add_bytes("bytes", "U8", (2,), b"\x11\x22")
    writer.add_bytes("scalar", "F32", (1,), b"\x00\x00\x80\x3f")
    writer.finish()

    assert len(writer.shard_names) == 2
    with SafetensorsReader(tmp_path / writer.shard_names[0]) as reader:
        assert reader.tensor_info("bytes").dtype == "U8"
        assert b"".join(reader.iter_tensor_bytes("bytes")) == b"\x11\x22"
    with SafetensorsReader(tmp_path / writer.shard_names[1]) as reader:
        assert reader.tensor_info("scalar").shape == (1,)
        assert b"".join(reader.iter_tensor_bytes("scalar")) == b"\x00\x00\x80\x3f"
