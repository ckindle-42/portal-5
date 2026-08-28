from tests.benchmarks.bench_cad_gauntlet import score_result


def test_watertight_correct_bbox_passes():
    assert (
        score_result({"called_target_tool": True, "watertight": True, "bbox_sane": True}) == "PASS"
    )


def test_watertight_wrong_bbox_is_wrongsize():
    assert (
        score_result({"called_target_tool": True, "watertight": True, "bbox_sane": False})
        == "WRONGSIZE"
    )


def test_non_watertight_fails():
    assert (
        score_result({"called_target_tool": True, "watertight": False, "bbox_sane": True}) == "FAIL"
    )


def test_no_expected_bbox_watertight_passes():
    assert (
        score_result({"called_target_tool": True, "watertight": True, "bbox_sane": None}) == "PASS"
    )
