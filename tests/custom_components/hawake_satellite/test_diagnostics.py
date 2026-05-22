"""Tests for HAWake Satellite diagnostics."""

from custom_components.hawake_satellite.diagnostics import redact_diagnostics


def test_redacts_tokens() -> None:
    payload = {
        "token": "secret",
        "device_id": "android-123",
        "recent_events": [{"message": "registered"}],
    }

    assert redact_diagnostics(payload)["token"] == "REDACTED"


def test_redacts_common_nested_token_names() -> None:
    payload = {
        "connection": {
            "access_token": "secret",
            "long_lived_access_token": "also-secret",
        },
        "recent_events": [{"message": "ok"}],
    }

    redacted = redact_diagnostics(payload)

    assert redacted["connection"]["access_token"] == "REDACTED"
    assert redacted["connection"]["long_lived_access_token"] == "REDACTED"
