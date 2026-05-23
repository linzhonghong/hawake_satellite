"""Tests for audio duration probing."""

from __future__ import annotations

import struct
import sys
import wave
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "hawake_satellite"
    / "media_duration.py"
)

spec = spec_from_file_location("media_duration", MODULE_PATH)
assert spec is not None
media_duration = module_from_spec(spec)
assert spec.loader is not None
sys.modules["media_duration"] = media_duration
spec.loader.exec_module(media_duration)
probe_audio_duration_seconds = media_duration.probe_audio_duration_seconds


def test_probes_wav_duration() -> None:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 32000)

    assert probe_audio_duration_seconds(buffer.getvalue(), "audio/wav") == 2.0


def test_probes_mp3_duration_from_frames() -> None:
    frame = _mpeg1_layer3_frame()
    audio = frame * 3

    duration = probe_audio_duration_seconds(audio, "audio/mpeg")

    assert duration is not None
    assert round(duration, 4) == round(3 * 1152 / 44100, 4)


def _mpeg1_layer3_frame() -> bytes:
    header = b"\xff\xfb\x90\x00"
    frame_size = int(144 * 128000 / 44100)
    return header + (b"\0" * (frame_size - len(header)))
