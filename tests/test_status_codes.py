from backend.api.status_codes import http_status_for_query


def test_success_and_chat_are_200():
    assert http_status_for_query({"status": "success"}) == 200
    assert http_status_for_query({"status": "ok"}) == 200


def test_clarify_is_400():
    assert http_status_for_query({"status": "clarify", "tool_results": [], "errors": []}) == 400


def test_validation_errors_are_400():
    assert http_status_for_query({
        "status": "error",
        "errors": ["bbox longitude must be between -180 and 180."],
        "tool_results": [],
    }) == 400


def test_respond_error_without_errors_list_is_400():
    assert http_status_for_query({
        "status": "error",
        "plan": {"action": "respond_error", "tool": None, "args": {}, "reason": "nope"},
        "errors": [],
        "tool_results": [],
    }) == 400


def test_tool_validation_error_is_400():
    assert http_status_for_query({
        "status": "error",
        "errors": [],
        "tool_results": [{
            "tool": "fetch_optical_imagery",
            "result": {
                "status": "error",
                "error": {"type": "validation_error", "message": "bbox required"},
            },
        }],
    }) == 400


def test_no_suitable_scene_is_404():
    assert http_status_for_query({
        "status": "error",
        "errors": [],
        "tool_results": [{
            "tool": "fetch_sar_imagery",
            "result": {
                "status": "error",
                "error": {
                    "type": "no_suitable_scene",
                    "message": "3 scene(s) exist but all are DESCENDING",
                },
            },
        }],
    }) == 404


def test_weather_no_data_is_404():
    assert http_status_for_query({
        "status": "error",
        "errors": [],
        "tool_results": [{
            "tool": "fetch_weather_environment",
            "result": {
                "status": "error",
                "error": {"type": "no_data", "message": "No meteorological data"},
            },
        }],
    }) == 404


def test_upstream_service_error_is_502():
    assert http_status_for_query({
        "status": "error",
        "errors": [],
        "tool_results": [{
            "tool": "fetch_optical_imagery",
            "result": {
                "status": "error",
                "error": {"type": "service_error", "message": "timeout"},
            },
        }],
    }) == 502


def test_import_and_unknown_tool_are_500():
    for err_type in ("import_error", "unknown_tool"):
        assert http_status_for_query({
            "status": "error",
            "errors": [],
            "tool_results": [{
                "tool": "fetch_optical_imagery",
                "result": {
                    "status": "error",
                    "error": {"type": err_type, "message": "boom"},
                },
            }],
        }) == 500


def test_empty_tool_output_without_errors_is_500():
    assert http_status_for_query({
        "status": "error",
        "final_answer": "No tool output was collected.",
        "errors": [],
        "tool_results": [],
        "plan": {"action": "call_tool", "tool": "fetch_optical_imagery", "args": {}, "reason": ""},
    }) == 500
