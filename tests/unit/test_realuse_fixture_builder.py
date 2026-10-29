from tests.wfe.suites.build_realuse_v1 import build, self_check


def test_realuse_fixture_builder_is_idempotent_and_self_checking(tmp_path):
    artifact_dir = tmp_path / "realuse_v1"
    output_path = tmp_path / "realuse_v1.jsonl"
    built = build(artifact_dir, output_path)
    first = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert build(artifact_dir, output_path) == built
    second = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert first == second
    assert self_check(artifact_dir, output_path) == built
