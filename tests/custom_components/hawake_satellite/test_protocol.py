"""Tests for HAWake Satellite protocol helpers."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest


homeassistant = ModuleType("homeassistant")
config_entries = ModuleType("homeassistant.config_entries")
config_entries.ConfigEntry = object
core = ModuleType("homeassistant.core")
core.HomeAssistant = object
core.ServiceCall = object
sys.modules.setdefault("homeassistant", homeassistant)
sys.modules.setdefault("homeassistant.config_entries", config_entries)
sys.modules.setdefault("homeassistant.core", core)

from custom_components.hawake_satellite.const import SatelliteClientState
from custom_components.hawake_satellite.protocol import (
    AudioHeader,
    RegisterMessage,
    StateMessage,
    parse_audio_header,
    parse_register_message,
    parse_state_message,
)


def test_parse_register_message_keeps_capabilities() -> None:
    """Parse a registration payload without dropping capabilities."""
    msg = parse_register_message(
        {
            "device_id": "android-123",
            "name": "Bedroom Phone",
            "app_version": "0.2.0",
            "capabilities": {"wake_word": True, "mic_stream": True},
        }
    )

    assert msg == RegisterMessage(
        device_id="android-123",
        name="Bedroom Phone",
        app_version="0.2.0",
        capabilities={"wake_word": True, "mic_stream": True},
    )


def test_parse_register_message_rejects_empty_required_string() -> None:
    """Reject empty registration string fields."""
    with pytest.raises(ValueError, match="Missing required string field: device_id"):
        parse_register_message(
            {"device_id": "", "name": "Bedroom Phone", "app_version": "0.2.0"}
        )


def test_parse_register_message_rejects_missing_required_string() -> None:
    """Reject missing registration string fields with a protocol error."""
    with pytest.raises(ValueError, match="Missing required string field: device_id"):
        parse_register_message({"name": "Bedroom Phone", "app_version": "0.2.0"})


def test_parse_state_message_rejects_unknown_state() -> None:
    """Reject states that are not part of the satellite protocol."""
    with pytest.raises(ValueError, match="Unsupported satellite state"):
        parse_state_message({"device_id": "android-123", "state": "hovering"})


def test_parse_state_message_returns_state_message() -> None:
    """Parse a known client state."""
    msg = parse_state_message({"device_id": "android-123", "state": "listening"})

    assert msg == StateMessage(
        device_id="android-123",
        state=SatelliteClientState.LISTENING,
    )


def test_parse_audio_header_reads_uuid_and_payload() -> None:
    """Read the session UUID header and remaining PCM payload."""
    session_id = "01234567-89ab-cdef-0123-456789abcdef"
    frame = bytes.fromhex("0123456789abcdef0123456789abcdef") + b"\x01\x02"

    assert parse_audio_header(frame) == AudioHeader(session_id=session_id, pcm=b"\x01\x02")


def test_parse_audio_header_rejects_short_frame() -> None:
    """Reject frames that cannot contain the session UUID header."""
    with pytest.raises(
        ValueError, match="shorter than the 16-byte session id header"
    ):
        parse_audio_header(b"short")
