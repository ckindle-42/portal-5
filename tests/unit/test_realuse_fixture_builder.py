from tests.wfe.suites.build_realuse_v1 import DRAFT, SUITE, build, self_check


def test_realuse_fixture_builder_is_deterministic_and_preserves_runnable_suite(tmp_path):
    suite_before = SUITE.read_bytes()
    first_hashes = build(tmp_path)
    first = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert build(tmp_path) == first_hashes
    second = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert first == second
    assert self_check(tmp_path) == first_hashes
    assert SUITE.read_bytes() == suite_before
    assert DRAFT.exists()
    assert len(first_hashes) == 60
    assert not (tmp_path / "tests/wfe/suites/realuse_v1.jsonl").exists()
