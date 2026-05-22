"""Tests for HAWake AssistSatelliteEntity."""

from __future__ import annotations

import asyncio
from asyncio import run

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
