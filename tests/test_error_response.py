from backend.error_response import error_message, error_payload


def test_error_payload_keeps_legacy_and_canonical_fields():
    payload = error_payload(
        status_code=429,
        detail="Zu viele Anfragen.",
        request_id="req-123",
        retryable=True,
    )

    assert payload["ok"] is False
    assert payload["status"] == "error"
    assert payload["error"] == "Zu viele Anfragen."
    assert payload["message"] == "Zu viele Anfragen."
    assert payload["errorCode"] == "rate_limited"
    assert payload["httpStatus"] == 429
    assert payload["requestId"] == "req-123"
    assert payload["retryable"] is True
    assert payload["detail"] == "Zu viele Anfragen."


def test_error_message_formats_validation_detail_arrays():
    message = error_message([
        {"loc": ("body", "message"), "msg": "Field required"},
        {"loc": ("query", "max"), "msg": "Input should be an integer"},
    ])

    assert message == "message: Field required; query.max: Input should be an integer"


def test_error_payload_extracts_structured_detail_message():
    payload = error_payload(
        status_code=502,
        detail={"message": "Hermes unavailable", "debug": "hidden internals"},
        request_id="req-456",
    )

    assert payload["error"] == "Hermes unavailable"
    assert payload["errorCode"] == "upstream_error"
    assert payload["detail"]["debug"] == "hidden internals"
