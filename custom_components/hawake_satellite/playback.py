"""Playback routing for HAWake Satellite responses."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .const import (
    CALLBACK_SERVICE_PLAYBACK_FINISHED,
    EVENT_PLAYBACK_REQUESTED,
    PlaybackMode,
)


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


@dataclass(frozen=True)
class PlaybackResult:
    """Result of a playback route that completes inside Home Assistant."""

    session_id: str
    status: str


class PlaybackRouter:
    """Route playback requests to Android, media_player, or automation."""

    def __init__(self, coordinator, hass=None) -> None:
        """Initialize router."""
        self._coordinator = coordinator
        self._hass = hass

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
            if self._hass is None:
                raise ValueError("hass is required for media_player playback")
            self._queue_external_playback_started(request)
            try:
                await self._hass.services.async_call(
                    "media_player",
                    "play_media",
                    {
                        "entity_id": request.media_player_entity_id,
                        "media_content_id": self._resolve_media_url(request.media_url),
                        "media_content_type": request.mime_type,
                    },
                    blocking=True,
                )
            except Exception:
                return PlaybackResult(session_id=request.session_id, status="error")
            status = await self._wait_for_media_player_completion(
                request.media_player_entity_id,
            )
            return PlaybackResult(session_id=request.session_id, status=status)

        if request.playback_mode is PlaybackMode.AUTOMATION:
            if self._hass is None:
                raise ValueError("hass is required for automation playback")
            self._queue_external_playback_started(request)
            self._hass.bus.async_fire(
                EVENT_PLAYBACK_REQUESTED,
                {
                    "device_id": request.device_id,
                    "session_id": request.session_id,
                    "media_url": request.media_url,
                    "mime_type": request.mime_type,
                    "response_text": request.response_text,
                    "callback_service": CALLBACK_SERVICE_PLAYBACK_FINISHED,
                },
            )
            return

    def _queue_external_playback_started(self, request: PlaybackRequest) -> None:
        """Tell Android an external route has accepted playback responsibility."""
        self._coordinator.queue_downlink(
            request.device_id,
            {
                "command": "external_playback_started",
                "session_id": request.session_id,
            },
        )

    async def _wait_for_media_player_completion(self, entity_id: str) -> str:
        """Wait for a media player to leave playing state after playback starts."""
        loop = asyncio.get_running_loop()
        finished = loop.create_future()
        seen_playing = False

        def _listener(event) -> None:
            nonlocal seen_playing
            if event.data.get("entity_id") != entity_id:
                return
            state = getattr(event.data.get("new_state"), "state", None)
            if state == "playing":
                seen_playing = True
                return
            if seen_playing and not finished.done():
                finished.set_result("success")

        unsubscribe = self._hass.bus.async_listen("state_changed", _listener)
        try:
            return await asyncio.wait_for(finished, MEDIA_PLAYER_COMPLETION_TIMEOUT_SECONDS)
        except TimeoutError:
            return "error"
        finally:
            unsubscribe()

    def _resolve_media_url(self, media_url: str) -> str:
        """Resolve Home Assistant relative media URLs for external players."""
        if media_url.startswith(("http://", "https://")):
            return media_url
        base_url = getattr(getattr(self._hass, "config", None), "api", None)
        base_url = getattr(base_url, "base_url", "") or ""
        if not base_url:
            return media_url
        return f"{base_url.rstrip('/')}/{media_url.lstrip('/')}"


MEDIA_PLAYER_COMPLETION_TIMEOUT_SECONDS = 15 * 60
