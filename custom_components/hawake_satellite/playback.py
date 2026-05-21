"""Playback routing for HAWake Satellite responses."""

from __future__ import annotations

from dataclasses import dataclass

from .const import PlaybackMode


@dataclass(frozen=True)
class PlaybackRequest:
    """Request to play a TTS response or announcement."""

    playback_mode: PlaybackMode
    device_id: str
    session_id: str
    media_url: str
    mime_type: str
    response_text: str
    media_player_entity_id: str | None = None
    playback_script_entity_id: str | None = None


class PlaybackRouter:
    """Route playback requests to Android, media_player, or automation."""

    def __init__(self, coordinator) -> None:
        """Initialize router."""
        self._coordinator = coordinator

    async def play(self, request: PlaybackRequest) -> None:
        """Start playback for a request."""
        if request.playback_mode is PlaybackMode.APP:
            self._coordinator.queue_downlink(
                request.device_id,
                {
                    "command": "play_media",
                    "session_id": request.session_id,
                    "media_url": request.media_url,
                    "mime_type": request.mime_type,
                },
            )
            return

        if request.playback_mode is PlaybackMode.MEDIA_PLAYER:
            if not request.media_player_entity_id:
                raise ValueError(
                    "media_player_entity_id is required for media_player playback"
                )
            return

        if request.playback_mode is PlaybackMode.AUTOMATION:
            if not request.playback_script_entity_id:
                raise ValueError(
                    "playback_script_entity_id is required for automation playback"
                )
            return
