"""The finish repair quotes the tools the Pipeline ran server-side, so the model resubmits the checked artifact."""

from portal.modules.orchestration import worker


def test_bite_requests_ask_for_the_execution_audit() -> None:
    assert worker._request_body.__code__.co_consts  # function exists
    import inspect

    assert '"exec_audit": True' in inspect.getsource(worker._request_body)


def test_lab_rows_match_the_backends_nested_fields() -> None:
    from portal.modules.orchestration.disciplines.detection_engineering import checkers

    nested = {"_time": 1.0, "raw": "{}", "fields": {"ServiceName": "svc_backup", "count": "70"}}
    assert checkers._row_matches({"ServiceName": "svc_backup"}, nested)
    assert checkers._row_matches({"ServiceName": "svc_backup"}, {"ServiceName": "svc_backup"})
    assert not checkers._row_matches({"ServiceName": "svc_sql"}, nested)
