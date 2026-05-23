"""Helpers for Assist pipeline event payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PipelineTtsOutput:
    """TTS media extracted from an Assist pipeline event."""

    media_url: str
    mime_type: str
    response_text: str = ""


def extract_tts_output(event: Any) -> PipelineTtsOutput | None:
    """Extract playable TTS output from a HA Assist pipeline event."""
    if _event_type_value(getattr(event, "type", None)) != "tts-end":
        return None

    data = getattr(event, "data", None)
    tts_output = _field(data, "tts_output")
    media_url = _field(tts_output, "url") or _field(tts_output, "media_id")
    if not media_url:
        return None

    return PipelineTtsOutput(
        media_url=media_url,
        mime_type=_field(tts_output, "mime_type")
        or _field(tts_output, "media_type")
        or "audio/mpeg",
        response_text=_field(data, "text") or "",
    )


def extract_response_text(event: Any) -> str:
    """Extract spoken response text from Assist pipeline events."""
    event_type = _event_type_value(getattr(event, "type", None))
    data = getattr(event, "data", None)

    if event_type == "tts-start":
        return _field(data, "tts_input") or _field(data, "text") or ""

    if event_type == "intent-end":
        intent_output = _field(data, "intent_output")
        response = _field(intent_output, "response")
        speech = _field(response, "speech")
        plain = _field(speech, "plain")
        return _field(plain, "speech") or ""

    return ""


def _event_type_value(event_type: Any) -> str | None:
    if event_type is None:
        return None
    return getattr(event_type, "value", event_type)


def _field(value: Any, field_name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(field_name)
    return getattr(value, field_name, None)
