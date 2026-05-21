"""Assist satellite platform for HAWake Satellite."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from homeassistant.components.assist_satellite import (
    AssistSatelliteEntity,
    AssistSatelliteEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

try:
    from homeassistant.components.assist_satellite import (
        AssistSatelliteAnnouncement,
        AssistSatelliteConfiguration,
        AssistSatelliteWakeWord,
    )
except ImportError:
    @dataclass(frozen=True)
    class AssistSatelliteWakeWord:
        """Fallback wake-word config for local tests."""

        id: str
        wake_word: str
        trained_languages: list[str]

    @dataclass(frozen=True)
    class AssistSatelliteConfiguration:
        """Fallback satellite config for local tests."""

        active_wake_words: list[str]
        max_active_wake_words: int
        available_wake_words: list[AssistSatelliteWakeWord]

    @dataclass(frozen=True)
    class AssistSatelliteAnnouncement:
        """Fallback announcement object for local tests."""

        media_id: str
        media_type: str = "audio/mpeg"

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_MEDIA_PLAYER_ENTITY_ID,
    CONF_PLAYBACK_MODE,
    CONF_PLAYBACK_SCRIPT_ENTITY_ID,
    DOMAIN,
    PlaybackMode,
    SatelliteClientState,
)
from .coordinator import SatelliteCoordinator
from .pipeline_events import extract_tts_output
from .playback import PlaybackRequest, PlaybackRouter


class HAWakeAssistSatelliteEntity(AssistSatelliteEntity):
    """Home Assistant Assist Satellite backed by an Android app."""

    _attr_supported_features = (
        AssistSatelliteEntityFeature.ANNOUNCE
        | AssistSatelliteEntityFeature.START_CONVERSATION
    )

    def __init__(
        self,
        coordinator: SatelliteCoordinator,
        device_id: str,
        name: str,
        data: dict | None = None,
    ) -> None:
        """Initialize entity."""
        self._coordinator = coordinator
        self._device_id = device_id
        self._data = data or {}
        self._attr_name = name
        self._attr_unique_id = device_id
        self._coordinator.register_entity(device_id, self)

    @property
    def available(self) -> bool:
        """Return if the Android client is connected."""
        return self._coordinator.client_state(self._device_id) is not SatelliteClientState.OFFLINE

    async def async_start_audio_capture(self, session_id: str) -> None:
        """Ask Android to begin microphone capture for a session."""
        self._coordinator.queue_downlink(
            self._device_id,
            {"command": "start_audio_capture", "session_id": session_id},
        )

    def async_get_configuration(self) -> AssistSatelliteConfiguration:
        """Return the satellite wake-word configuration."""
        wake_word = AssistSatelliteWakeWord(
            id="android_local",
            wake_word="Android local",
            trained_languages=[],
        )
        return AssistSatelliteConfiguration(
            available_wake_words=[wake_word],
            active_wake_words=[wake_word.id],
            max_active_wake_words=1,
        )

    async def async_set_configuration(self, config: AssistSatelliteConfiguration) -> None:
        """Accept configuration updates from HA."""
        return None

    def on_pipeline_event(self, event) -> None:
        """Handle HA Assist pipeline state updates."""
        tts_output = extract_tts_output(event)
        if tts_output is None:
            return
        session_id = getattr(event, "run_id", None) or uuid4().hex
        self.hass.async_create_task(
            self._play_media(
                session_id=session_id,
                media_url=tts_output.media_url,
                mime_type=tts_output.mime_type,
                response_text=tts_output.response_text,
            )
        )

    async def async_accept_android_wake(self, session_id: str, wake_phrase: str) -> None:
        """Run HA Assist from Android wake-word audio."""
        await self.async_start_audio_capture(session_id)
        await self.async_accept_pipeline_from_satellite(
            self._coordinator.audio_stream(session_id),
            wake_word_phrase=wake_phrase,
        )

    async def async_announce(self, announcement: AssistSatelliteAnnouncement) -> None:
        """Play an announcement through the configured playback route."""
        await self._play_media(
            session_id=uuid4().hex,
            media_url=announcement.media_id,
            mime_type=getattr(announcement, "media_type", "audio/mpeg"),
            response_text="",
        )

    async def async_start_conversation(self, start_message: AssistSatelliteAnnouncement) -> None:
        """Play a prompt before HA starts a conversation."""
        await self.async_announce(start_message)

    async def _play_media(
        self,
        session_id: str,
        media_url: str,
        mime_type: str,
        response_text: str,
    ) -> None:
        """Route media playback through the configured playback mode."""
        playback_mode = PlaybackMode(self._data.get(CONF_PLAYBACK_MODE, PlaybackMode.APP))
        self._coordinator.start_session(session_id, self._device_id)
        await PlaybackRouter(self._coordinator).play(
            PlaybackRequest(
                playback_mode=playback_mode,
                device_id=self._device_id,
                session_id=session_id,
                media_url=media_url,
                mime_type=mime_type,
                response_text=response_text,
                media_player_entity_id=self._data.get(CONF_MEDIA_PLAYER_ENTITY_ID),
                playback_script_entity_id=self._data.get(CONF_PLAYBACK_SCRIPT_ENTITY_ID),
            )
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the HAWake Satellite assist satellite platform."""
    coordinator: SatelliteCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            HAWakeAssistSatelliteEntity(
                coordinator=coordinator,
                device_id=entry.data[CONF_DEVICE_ID],
                name=entry.data[CONF_DEVICE_NAME],
                data=entry.data,
            )
        ]
    )
