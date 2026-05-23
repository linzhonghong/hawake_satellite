"""Best-effort audio duration probing for TTS media."""

from __future__ import annotations

import asyncio
import struct
from typing import Final

MAX_PROBE_BYTES: Final = 8 * 1024 * 1024
PROBE_TIMEOUT_SECONDS: Final = 10


async def async_probe_media_duration_seconds(
    hass,
    media_url: str,
    mime_type: str,
) -> float | None:
    """Fetch TTS media and return its duration when it can be inferred."""
    if not media_url:
        return None
    url = _resolve_media_url(hass, media_url)
    if not url:
        return None
    try:
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        session = async_get_clientsession(hass)
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            response = await session.get(url)
            async with response:
                if response.status >= 400:
                    return None
                audio = await response.content.read(MAX_PROBE_BYTES + 1)
    except Exception:
        return None
    if len(audio) > MAX_PROBE_BYTES:
        return None
    return probe_audio_duration_seconds(audio, mime_type)


def probe_audio_duration_seconds(audio: bytes, mime_type: str = "") -> float | None:
    """Return duration for common TTS audio containers."""
    if not audio:
        return None
    mime_type = (mime_type or "").lower()
    if "wav" in mime_type or audio.startswith(b"RIFF"):
        return _probe_wav_duration_seconds(audio)
    if "mpeg" in mime_type or "mp3" in mime_type or _looks_like_mp3(audio):
        return _probe_mp3_duration_seconds(audio)
    return None


def _resolve_media_url(hass, media_url: str) -> str | None:
    if media_url.startswith(("http://", "https://")):
        return media_url
    base_url = getattr(getattr(hass, "config", None), "api", None)
    base_url = getattr(base_url, "base_url", "") or ""
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/{media_url.lstrip('/')}"


def _probe_wav_duration_seconds(audio: bytes) -> float | None:
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return None

    offset = 12
    byte_rate = None
    data_size = None
    while offset + 8 <= len(audio):
        chunk_id = audio[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", audio, offset + 4)[0]
        chunk_start = offset + 8
        if chunk_id == b"fmt " and chunk_size >= 16:
            byte_rate = struct.unpack_from("<I", audio, chunk_start + 8)[0]
        elif chunk_id == b"data":
            data_size = chunk_size
        offset = chunk_start + chunk_size + (chunk_size % 2)

    if not byte_rate or data_size is None:
        return None
    return data_size / byte_rate


def _looks_like_mp3(audio: bytes) -> bool:
    offset = _skip_id3v2(audio)
    return _find_mp3_frame(audio, offset) is not None


def _probe_mp3_duration_seconds(audio: bytes) -> float | None:
    offset = _skip_id3v2(audio)
    duration = 0.0
    frames = 0
    while True:
        frame_offset = _find_mp3_frame(audio, offset)
        if frame_offset is None:
            break
        parsed = _parse_mp3_frame_header(audio, frame_offset)
        if parsed is None:
            offset = frame_offset + 1
            continue
        frame_size, sample_rate, samples_per_frame = parsed
        duration += samples_per_frame / sample_rate
        frames += 1
        offset = frame_offset + frame_size
        if offset >= len(audio):
            break
    if frames == 0:
        return None
    return duration


def _skip_id3v2(audio: bytes) -> int:
    if len(audio) < 10 or audio[:3] != b"ID3":
        return 0
    size = 0
    for byte in audio[6:10]:
        size = (size << 7) | (byte & 0x7F)
    return 10 + size


def _find_mp3_frame(audio: bytes, offset: int) -> int | None:
    for index in range(offset, max(len(audio) - 1, offset)):
        if audio[index] == 0xFF and audio[index + 1] & 0xE0 == 0xE0:
            return index
    return None


def _parse_mp3_frame_header(audio: bytes, offset: int) -> tuple[int, int, int] | None:
    if offset + 4 > len(audio):
        return None
    header = int.from_bytes(audio[offset : offset + 4], "big")
    version_bits = (header >> 19) & 0b11
    layer_bits = (header >> 17) & 0b11
    bitrate_index = (header >> 12) & 0b1111
    sample_rate_index = (header >> 10) & 0b11
    padding = (header >> 9) & 0b1

    if version_bits == 0b01 or layer_bits == 0 or bitrate_index in {0, 15}:
        return None
    if sample_rate_index == 0b11:
        return None

    version = {0b00: 2.5, 0b10: 2, 0b11: 1}[version_bits]
    layer = {0b01: 3, 0b10: 2, 0b11: 1}[layer_bits]
    bitrate = _mp3_bitrate(version, layer, bitrate_index)
    sample_rate = _mp3_sample_rate(version, sample_rate_index)
    if bitrate is None or sample_rate is None:
        return None

    samples_per_frame = _mp3_samples_per_frame(version, layer)
    if layer == 1:
        frame_size = int((12 * bitrate * 1000 / sample_rate + padding) * 4)
    else:
        coefficient = 72 if layer == 3 and version != 1 else 144
        frame_size = int(coefficient * bitrate * 1000 / sample_rate + padding)
    if frame_size <= 4:
        return None
    return frame_size, sample_rate, samples_per_frame


def _mp3_bitrate(version: float, layer: int, index: int) -> int | None:
    if version == 1:
        table = {
            1: [None, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
            2: [None, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
            3: [None, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
        }[layer]
    else:
        table = {
            1: [None, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256],
            2: [None, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
            3: [None, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
        }[layer]
    return table[index]


def _mp3_sample_rate(version: float, index: int) -> int | None:
    base = [44100, 48000, 32000][index]
    if version == 1:
        return base
    if version == 2:
        return base // 2
    if version == 2.5:
        return base // 4
    return None


def _mp3_samples_per_frame(version: float, layer: int) -> int:
    if layer == 1:
        return 384
    if layer == 2:
        return 1152
    return 1152 if version == 1 else 576
