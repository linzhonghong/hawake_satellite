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
    CALLBACK_SERVICE_PLAYBACK_FINISHED,
    EVENT_PIPELINE_STAGE,
    PlaybackMode,
    SatelliteClientState,
)
from .coordinator import SatelliteCoordinator
from .media_duration import async_probe_media_duration_seconds
from .pipeline_events import extract_response_text, extract_stt_text, extract_tts_output
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
        self._response_text_by_run_id: dict[str, str] = {}
        self._automation_playback_run_ids: set[str] = set()
        self._coordinator.register_entity(device_id, self)

    @property
    def available(self) -> bool:
        """Return if the Android client is connected."""
        return self._coordinator.client_state(self._device_id) is not SatelliteClientState.OFFLINE

    @property
    def playback_mode(self) -> PlaybackMode:
        """Return the configured response playback mode."""
        return PlaybackMode(self._data.get(CONF_PLAYBACK_MODE, PlaybackMode.APP))

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
        run_id = getattr(event, "run_id", None)
        session_id = run_id or uuid4().hex
        stage = _event_type_value(getattr(event, "type", None))
        stt_text = extract_stt_text(event)
        if stt_text:
            self._queue_conversation_message(session_id, "user", stt_text)
        response_text = extract_response_text(event)
        if run_id and response_text:
            self._response_text_by_run_id[run_id] = response_text
        if response_text:
            self._queue_conversation_message(session_id, "assistant", response_text)
        tts_output = extract_tts_output(event)
        media_url = tts_output.media_url if tts_output is not None else ""
        mime_type = tts_output.mime_type if tts_output is not None else ""
        duration_seconds = (
            tts_output.duration_seconds if tts_output is not None else None
        )
        if tts_output is not None and not response_text:
            response_text = tts_output.response_text or self._response_text_by_run_id.get(
                session_id, ""
            )
        self._schedule_pipeline_stage_event(
            session_id=session_id,
            stage=stage,
            media_url=media_url,
            mime_type=mime_type,
            response_text=response_text,
            duration_seconds=duration_seconds,
        )

        if response_text and self.playback_mode is PlaybackMode.AUTOMATION:
            if session_id in self._automation_playback_run_ids:
                return
            self._automation_playback_run_ids.add(session_id)
            self.hass.async_create_task(
                self._play_media(
                    session_id=session_id,
                    media_url="",
                    mime_type="",
                    response_text=response_text,
                )
            )
            return

        if tts_output is None:
            return
        if self.playback_mode is PlaybackMode.AUTOMATION:
            self._automation_playback_run_ids.discard(session_id)
            self._response_text_by_run_id.pop(session_id, None)
            return
        response_text = tts_output.response_text or self._response_text_by_run_id.pop(
            session_id, ""
        )
        self.hass.async_create_task(
            self._play_media(
                session_id=session_id,
                media_url=tts_output.media_url,
                mime_type=tts_output.mime_type,
                response_text=response_text,
            )
        )

    def _schedule_pipeline_stage_event(
        self,
        session_id: str,
        stage: str | None,
        media_url: str,
        mime_type: str,
        response_text: str,
        duration_seconds: float | None,
    ) -> None:
        """Expose Assist pipeline stages to Home Assistant automations."""
        if stage not in {"intent-end", "tts-start", "tts-end"}:
            return
        if stage == "tts-end" and duration_seconds is None and media_url:
            self.hass.async_create_task(
                self._async_fire_tts_end_stage_event(
                    session_id=session_id,
                    stage=stage,
                    media_url=media_url,
                    mime_type=mime_type,
                    response_text=response_text,
                )
            )
            return
        self._fire_pipeline_stage_event(
            session_id=session_id,
            stage=stage,
            media_url=media_url,
            mime_type=mime_type,
            response_text=response_text,
            duration_seconds=duration_seconds,
        )

    async def _async_fire_tts_end_stage_event(
        self,
        session_id: str,
        stage: str,
        media_url: str,
        mime_type: str,
        response_text: str,
    ) -> None:
        """Probe TTS media duration before publishing the tts-end stage event."""
        duration_seconds = await async_probe_media_duration_seconds(
            self.hass, media_url, mime_type
        )
        self._fire_pipeline_stage_event(
            session_id=session_id,
            stage=stage,
            media_url=media_url,
            mime_type=mime_type,
            response_text=response_text,
            duration_seconds=duration_seconds,
        )

    def _fire_pipeline_stage_event(
        self,
        session_id: str,
        stage: str,
        media_url: str,
        mime_type: str,
        response_text: str,
        duration_seconds: float | None,
    ) -> None:
        """Fire a Home Assistant event for an Assist pipeline stage."""
        self.hass.bus.async_fire(
            EVENT_PIPELINE_STAGE,
            {
                "device_id": self._device_id,
                "session_id": session_id,
                "stage": stage,
                "playback_mode": self.playback_mode.value,
                "media_url": media_url,
                "mime_type": mime_type,
                "response_text": response_text,
                "duration_seconds": duration_seconds,
                "callback_service": CALLBACK_SERVICE_PLAYBACK_FINISHED,
            },
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
        self._coordinator.start_session(session_id, self._device_id)
        result = await PlaybackRouter(self._coordinator, self.hass).play(
            PlaybackRequest(
                playback_mode=self.playback_mode,
                device_id=self._device_id,
                session_id=session_id,
                media_url=media_url,
                mime_type=mime_type,
                response_text=response_text,
                media_player_entity_id=self._data.get(CONF_MEDIA_PLAYER_ENTITY_ID),
                playback_script_entity_id=self._data.get(CONF_PLAYBACK_SCRIPT_ENTITY_ID),
            )
        )
        if result is not None:
            self.tts_response_finished()
            self._coordinator.queue_downlink(
                self._device_id,
                {
                    "command": "playback_callback_recorded",
                    "session_id": result.session_id,
                    "status": result.status,
                },
            )
            self._coordinator.finish_session(result.session_id)

    def _queue_conversation_message(
        self,
        session_id: str,
        speaker: str,
        text: str,
    ) -> None:
        """Send live conversation text to the Android UI."""
        self._coordinator.queue_downlink(
            self._device_id,
            {
                "command": "conversation_message",
                "session_id": session_id,
                "speaker": speaker,
                "text": text,
            },
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the HAWake Satellite assist satellite platform."""
    coordinator: SatelliteCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    data = {**entry.data, **getattr(entry, "options", {})}
    async_add_entities(
        [
            HAWakeAssistSatelliteEntity(
                coordinator=coordinator,
                device_id=data[CONF_DEVICE_ID],
                name=data[CONF_DEVICE_NAME],
                data=data,
            )
        ]
    )


def _event_type_value(event_type) -> str | None:
    """Return a normalized Assist pipeline event type."""
    if event_type is None:
        return None
    return getattr(event_type, "value", event_type)
