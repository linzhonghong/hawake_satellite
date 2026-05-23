"""Tests for HAWake AssistSatelliteEntity."""

from __future__ import annotations

import asyncio
from asyncio import run
from dataclasses import dataclass

from custom_components.hawake_satellite.assist_satellite import (
    HAWakeAssistSatelliteEntity,
    async_setup_entry,
)
from custom_components.hawake_satellite.const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_MEDIA_PLAYER_ENTITY_ID,
    CONF_PLAYBACK_MODE,
    DOMAIN,
    PlaybackMode,
)
from custom_components.hawake_satellite.coordinator import SatelliteCoordinator
from custom_components.hawake_satellite.protocol import RegisterMessage


@dataclass(frozen=True)
class EventType:
    """Small stand-in for HA pipeline event enum values."""

    value: str


@dataclass(frozen=True)
class PipelineEvent:
    """Small stand-in for HA pipeline events."""

    type: EventType
    data: dict
    run_id: str = "run-1"


class RunningHass:
    """Fake hass that executes scheduled coroutines in sync tests."""

    def __init__(self) -> None:
        self.bus = FakeBus()

    def async_create_task(self, coro):
        return run(coro)


class FakeBus:
    """Small Home Assistant event bus test double."""

    def __init__(self) -> None:
        self.events = []

    def async_fire(self, event_type: str, event_data: dict) -> None:
        self.events.append((event_type, event_data))


def test_entity_available_when_client_registered() -> None:
    coordinator = SatelliteCoordinator()
    coordinator.register_client(
        RegisterMessage("android-123", "Bedroom Phone", "0.2.0", {}),
        connection_id="conn-1",
    )
    entity = HAWakeAssistSatelliteEntity(
        coordinator=coordinator,
        device_id="android-123",
        name="Bedroom Phone",
    )

    assert entity.available is True


def test_entity_unavailable_when_client_offline() -> None:
    coordinator = SatelliteCoordinator()
    entity = HAWakeAssistSatelliteEntity(
        coordinator=coordinator,
        device_id="android-123",
        name="Bedroom Phone",
    )

    assert entity.available is False


def test_start_audio_capture_queues_downlink() -> None:
    coordinator = SatelliteCoordinator()
    coordinator.register_client(
        RegisterMessage("android-123", "Bedroom Phone", "0.2.0", {}),
        connection_id="conn-1",
    )
    entity = HAWakeAssistSatelliteEntity(
        coordinator=coordinator,
        device_id="android-123",
        name="Bedroom Phone",
    )

    run(entity.async_start_audio_capture("session-1"))

    assert coordinator.pop_downlinks("android-123") == [
        {"command": "start_audio_capture", "session_id": "session-1"}
    ]


def test_pipeline_tts_event_routes_playback_to_app() -> None:
    coordinator = SatelliteCoordinator()
    entity = HAWakeAssistSatelliteEntity(
        coordinator=coordinator,
        device_id="android-123",
        name="Bedroom Phone",
        data={CONF_PLAYBACK_MODE: PlaybackMode.APP},
    )
    entity.hass = RunningHass()

    entity.on_pipeline_event(
        PipelineEvent(
            type=EventType("tts-end"),
            data={
                "text": "现在是凌晨一点",
                "tts_output": {
                    "url": "/api/tts_proxy/abc.mp3",
                    "mime_type": "audio/mpeg",
                },
            },
            run_id="run-tts-1",
        )
    )

    assert coordinator.pop_downlinks("android-123") == [
        {
            "command": "play_media",
            "session_id": "run-tts-1",
            "media_url": "/api/tts_proxy/abc.mp3",
            "mime_type": "audio/mpeg",
        }
    ]


def test_pipeline_text_event_routes_automation_without_tts_media() -> None:
    coordinator = SatelliteCoordinator()
    entity = HAWakeAssistSatelliteEntity(
        coordinator=coordinator,
        device_id="android-123",
        name="Bedroom Phone",
        data={CONF_PLAYBACK_MODE: PlaybackMode.AUTOMATION},
    )
    entity.hass = RunningHass()

    entity.on_pipeline_event(
        PipelineEvent(
            type=EventType("intent-end"),
            data={
                "intent_output": {
                    "response": {
                        "speech": {"plain": {"speech": "It is 9 PM."}},
                    },
                },
            },
            run_id="run-tts-1",
        )
    )

    assert coordinator.pop_downlinks("android-123") == [
        {"command": "external_playback_started", "session_id": "run-tts-1"}
    ]
    assert entity.hass.bus.events == [
        (
            "hawake_satellite_pipeline_event",
            {
                "device_id": "android-123",
                "session_id": "run-tts-1",
                "stage": "intent-end",
                "media_url": "",
                "mime_type": "",
                "response_text": "It is 9 PM.",
                "callback_service": "hawake_satellite.playback_finished",
            },
        ),
        (
            "hawake_satellite_playback_requested",
            {
                "device_id": "android-123",
                "session_id": "run-tts-1",
                "media_url": "",
                "mime_type": "",
                "response_text": "It is 9 PM.",
                "callback_service": "hawake_satellite.playback_finished",
            },
        )
    ]


def test_pipeline_stage_event_is_fired_for_ha_automation() -> None:
    coordinator = SatelliteCoordinator()
    entity = HAWakeAssistSatelliteEntity(
        coordinator=coordinator,
        device_id="android-123",
        name="Bedroom Phone",
        data={CONF_PLAYBACK_MODE: PlaybackMode.APP},
    )
    entity.hass = RunningHass()

    entity.on_pipeline_event(
        PipelineEvent(
            type=EventType("intent-end"),
            data={
                "intent_output": {
                    "response": {
                        "speech": {"plain": {"speech": "It is 9 PM."}},
                    },
                },
            },
            run_id="run-tts-1",
        )
    )

    assert entity.hass.bus.events == [
        (
            "hawake_satellite_pipeline_event",
            {
                "device_id": "android-123",
                "session_id": "run-tts-1",
                "stage": "intent-end",
                "media_url": "",
                "mime_type": "",
                "response_text": "It is 9 PM.",
                "callback_service": "hawake_satellite.playback_finished",
            },
        )
    ]


def test_pipeline_stage_tts_end_event_includes_cached_response_text() -> None:
    coordinator = SatelliteCoordinator()
    entity = HAWakeAssistSatelliteEntity(
        coordinator=coordinator,
        device_id="android-123",
        name="Bedroom Phone",
        data={CONF_PLAYBACK_MODE: PlaybackMode.APP},
    )
    entity.hass = RunningHass()

    entity.on_pipeline_event(
        PipelineEvent(
            type=EventType("tts-start"),
            data={"tts_input": "It is 9 PM."},
            run_id="run-tts-1",
        )
    )
    entity.hass.bus.events.clear()
    entity.on_pipeline_event(
        PipelineEvent(
            type=EventType("tts-end"),
            data={
                "tts_output": {
                    "url": "/api/tts_proxy/abc.mp3",
                    "mime_type": "audio/mpeg",
                },
            },
            run_id="run-tts-1",
        )
    )

    assert entity.hass.bus.events == [
        (
            "hawake_satellite_pipeline_event",
            {
                "device_id": "android-123",
                "session_id": "run-tts-1",
                "stage": "tts-end",
                "media_url": "/api/tts_proxy/abc.mp3",
                "mime_type": "audio/mpeg",
                "response_text": "It is 9 PM.",
                "callback_service": "hawake_satellite.playback_finished",
            },
        )
    ]


def test_pipeline_tts_end_does_not_duplicate_automation_text_playback() -> None:
    coordinator = SatelliteCoordinator()
    entity = HAWakeAssistSatelliteEntity(
        coordinator=coordinator,
        device_id="android-123",
        name="Bedroom Phone",
        data={CONF_PLAYBACK_MODE: PlaybackMode.AUTOMATION},
    )
    entity.hass = RunningHass()

    entity.on_pipeline_event(
        PipelineEvent(
            type=EventType("tts-start"),
            data={"tts_input": "It is 9 PM."},
            run_id="run-tts-1",
        )
    )
    coordinator.pop_downlinks("android-123")

    entity.on_pipeline_event(
        PipelineEvent(
            type=EventType("tts-end"),
            data={
                "tts_output": {
                    "url": "/api/tts_proxy/abc.mp3",
                    "mime_type": "audio/mpeg",
                },
            },
            run_id="run-tts-1",
        )
    )

    assert coordinator.pop_downlinks("android-123") == []
    playback_events = [
        event
        for event in entity.hass.bus.events
        if event[0] == "hawake_satellite_playback_requested"
    ]
    pipeline_events = [
        event
        for event in entity.hass.bus.events
        if event[0] == "hawake_satellite_pipeline_event"
    ]
    assert len(playback_events) == 1
    assert [event[1]["stage"] for event in pipeline_events] == ["tts-start", "tts-end"]


def test_async_setup_entry_adds_entity_from_config_entry() -> None:
    coordinator = SatelliteCoordinator()
    hass = type(
        "FakeHass",
        (),
        {"data": {DOMAIN: {"entry-1": {"coordinator": coordinator}}}},
    )()
    entry = type(
        "FakeEntry",
        (),
        {
            "entry_id": "entry-1",
            "data": {
                CONF_DEVICE_ID: "android-123",
                CONF_DEVICE_NAME: "Bedroom Phone",
            },
        },
    )()
    added_entities = []

    run(async_setup_entry(hass, entry, added_entities.extend))

    assert len(added_entities) == 1
    assert added_entities[0]._attr_unique_id == "android-123"


def test_async_setup_entry_applies_options_over_config_entry_data() -> None:
    coordinator = SatelliteCoordinator()
    hass = type(
        "FakeHass",
        (),
        {"data": {DOMAIN: {"entry-1": {"coordinator": coordinator}}}},
    )()
    entry = type(
        "FakeEntry",
        (),
        {
            "entry_id": "entry-1",
            "data": {
                CONF_DEVICE_ID: "android-123",
                CONF_DEVICE_NAME: "Bedroom Phone",
                CONF_PLAYBACK_MODE: PlaybackMode.APP,
            },
            "options": {CONF_PLAYBACK_MODE: PlaybackMode.AUTOMATION},
        },
    )()
    added_entities = []

    run(async_setup_entry(hass, entry, added_entities.extend))

    assert added_entities[0]._data[CONF_PLAYBACK_MODE] == PlaybackMode.AUTOMATION


def test_media_player_completion_notifies_android() -> None:
    class FakeBus:
        def __init__(self) -> None:
            self.listeners = {}

        def async_listen(self, event_type: str, listener):
            self.listeners.setdefault(event_type, []).append(listener)

            def unsubscribe() -> None:
                self.listeners[event_type].remove(listener)

            return unsubscribe

        def fire_state_changed(self, entity_id: str, state: str) -> None:
            event = type(
                "StateChangedEvent",
                (),
                {
                    "data": {
                        "entity_id": entity_id,
                        "new_state": type("State", (), {"state": state})(),
                    }
                },
            )()
            for listener in list(self.listeners.get("state_changed", [])):
                listener(event)

    class FakeServices:
        async def async_call(self, *args, **kwargs) -> None:
            return None

    async def scenario():
        coordinator = SatelliteCoordinator()
        entity = HAWakeAssistSatelliteEntity(
            coordinator=coordinator,
            device_id="android-123",
            name="Bedroom Phone",
            data={
                CONF_PLAYBACK_MODE: PlaybackMode.MEDIA_PLAYER,
                CONF_MEDIA_PLAYER_ENTITY_ID: "media_player.living_room",
            },
        )
        hass = type("FakeHass", (), {"bus": FakeBus(), "services": FakeServices()})()
        entity.hass = hass
        tts_finished = []
        entity.tts_response_finished = lambda: tts_finished.append(True)

        task = asyncio.create_task(
            entity._play_media(
                session_id="s1",
                media_url="https://ha.local/media/s1.mp3",
                mime_type="audio/mpeg",
                response_text="OK",
            )
        )
        await asyncio.sleep(0)
        hass.bus.fire_state_changed("media_player.living_room", "playing")
        hass.bus.fire_state_changed("media_player.living_room", "idle")
        await task
        return tts_finished, coordinator

    tts_finished, coordinator = run(scenario())

    assert len(tts_finished) == 1
    assert coordinator.pop_downlinks("android-123") == [
        {"command": "external_playback_started", "session_id": "s1"},
        {
            "command": "playback_callback_recorded",
            "session_id": "s1",
            "status": "success",
        }
    ]
    assert coordinator.device_for_session("s1") is None
