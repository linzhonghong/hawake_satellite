"""Pure protocol helpers for HAWake Satellite messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .const import SatelliteClientState


@dataclass(frozen=True)
class RegisterMessage:
    """Registration message sent by a satellite client."""

    device_id: str
    name: str
    app_version: str
    capabilities: dict[str, Any]


@dataclass(frozen=True)
class StateMessage:
    """State update sent by a satellite client."""

    device_id: str
    state: SatelliteClientState


@dataclass(frozen=True)
class AudioHeader:
    """Decoded audio frame header and PCM payload."""

    session_id: str
    pcm: bytes


def _required_str(msg: dict[str, Any], key: str) -> str:
    """Return a required string field from a protocol message."""
    value = msg.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Missing required string field: {key}")
    return value


def parse_register_message(msg: dict[str, Any]) -> RegisterMessage:
    """Parse a satellite registration message."""
    return RegisterMessage(
        device_id=_required_str(msg, "device_id"),
        name=_required_str(msg, "name"),
        app_version=_required_str(msg, "app_version"),
        capabilities=dict(msg.get("capabilities", {})),
    )


def parse_state_message(msg: dict[str, Any]) -> StateMessage:
    """Parse a satellite state update message."""
    raw_state = _required_str(msg, "state")
    try:
        state = SatelliteClientState(raw_state)
    except ValueError as err:
        raise ValueError(f"Unsupported satellite state: {raw_state}") from err

    return StateMessage(device_id=_required_str(msg, "device_id"), state=state)


def parse_audio_header(frame: bytes) -> AudioHeader:
    """Parse a binary audio frame with a 16-byte UUID session header."""
    if len(frame) < 16:
        raise ValueError("Audio frame is shorter than the 16-byte session id header")

    return AudioHeader(session_id=str(UUID(bytes=frame[:16])), pcm=frame[16:])
