"""Tests for Assist pipeline event parsing."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "hawake_satellite"
    / "pipeline_events.py"
)

spec = spec_from_file_location("pipeline_events", MODULE_PATH)
assert spec is not None
pipeline_events = module_from_spec(spec)
assert spec.loader is not None
sys.modules["pipeline_events"] = pipeline_events
spec.loader.exec_module(pipeline_events)
extract_tts_output = pipeline_events.extract_tts_output
extract_response_text = pipeline_events.extract_response_text
extract_stt_text = pipeline_events.extract_stt_text


@dataclass(frozen=True)
class EventType:
    """Small stand-in for HA pipeline event enum values."""

    value: str


@dataclass(frozen=True)
class PipelineEvent:
    """Small stand-in for HA pipeline events."""

    type: EventType
    data: dict


def test_extracts_tts_end_media_url() -> None:
    event = PipelineEvent(
        type=EventType("tts-end"),
        data={
            "text": "现在是凌晨一点",
            "tts_output": {
                "url": "/api/tts_proxy/abc.mp3",
                "mime_type": "audio/mpeg",
                "duration_seconds": 7.5,
            },
        },
    )

    output = extract_tts_output(event)

    assert output is not None
    assert output.media_url == "/api/tts_proxy/abc.mp3"
    assert output.mime_type == "audio/mpeg"
    assert output.duration_seconds == 7.5
    assert output.response_text == "现在是凌晨一点"


def test_ignores_non_tts_end_events() -> None:
    event = PipelineEvent(
        type=EventType("run-end"),
        data={"tts_output": {"url": "/api/tts_proxy/abc.mp3"}},
    )

    assert extract_tts_output(event) is None


def test_extracts_response_text_from_tts_start() -> None:
    event = PipelineEvent(
        type=EventType("tts-start"),
        data={"tts_input": "The living room light is on."},
    )

    assert extract_response_text(event) == "The living room light is on."


def test_extracts_response_text_from_intent_end() -> None:
    event = PipelineEvent(
        type=EventType("intent-end"),
        data={
            "intent_output": {
                "response": {
                    "speech": {
                        "plain": {
                            "speech": "It is 9 PM.",
                        },
                    },
                },
            },
        },
    )

    assert extract_response_text(event) == "It is 9 PM."


def test_extracts_stt_text_from_stt_end() -> None:
    event = PipelineEvent(
        type=EventType("stt-end"),
        data={"stt_output": {"text": "Turn on the light"}},
    )

    assert extract_stt_text(event) == "Turn on the light"
