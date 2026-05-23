"""Tests for HAWake Satellite WebSocket commands."""

from __future__ import annotations

from asyncio import run
import sys
from types import ModuleType
from typing import Any


homeassistant = ModuleType("homeassistant")
components = ModuleType("homeassistant.components")
websocket_api_module = ModuleType("homeassistant.components.websocket_api")
config_entries = ModuleType("homeassistant.config_entries")
core = ModuleType("homeassistant.core")
voluptuous = ModuleType("voluptuous")


class FakeActiveConnection:
    """Small ActiveConnection stand-in for type imports."""

    id = "conn-1"


def websocket_command(schema: dict[Any, Any]):
    """Return a no-op websocket command decorator."""

    def decorator(func):
        return func

    return decorator


websocket_api_module.ActiveConnection = FakeActiveConnection
websocket_api_module.websocket_command = websocket_command
websocket_api_module.async_response = lambda func: func
websocket_api_module.async_register_command = lambda hass, command: None
config_entries.ConfigEntry = object
core.HomeAssistant = object
core.ServiceCall = object
core.callback = lambda func: func
voluptuous.Required = lambda key, **kwargs: key
voluptuous.Optional = lambda key, **kwargs: key
voluptuous.In = lambda values: values

sys.modules["homeassistant"] = homeassistant
sys.modules["homeassistant.components"] = components
sys.modules["homeassistant.components.websocket_api"] = websocket_api_module
sys.modules["homeassistant.config_entries"] = config_entries
sys.modules["homeassistant.core"] = core
sys.modules["voluptuous"] = voluptuous

from custom_components.hawake_satellite.const import SatelliteClientState
from custom_components.hawake_satellite.const import CONF_PLAYBACK_MODE, PlaybackMode
from custom_components.hawake_satellite.coordinator import SatelliteCoordinator
import custom_components.hawake_satellite.websocket_api as websocket_api
from custom_components.hawake_satellite.websocket_api import (
    async_register_websocket_api,
    handle_register_payload,
    handle_state_payload,
    handle_subscribe_payload,
    unknown_device_message,
)


def test_handle_register_payload_returns_entity_metadata() -> None:
    coordinator = SatelliteCoordinator()

    result = handle_register_payload(
        coordinator,
        {
            "device_id": "android-123",
            "name": "Bedroom Phone",
            "app_version": "0.2.0",
            "capabilities": {"wake_word": True},
        },
        connection_id="conn-1",
    )

    assert result["satellite_entity_id"] == "assist_satellite.bedroom_phone"
    assert result["playback_mode"] == "app"
    assert coordinator.client_state("android-123") == SatelliteClientState.IDLE


def test_handle_register_payload_returns_entity_playback_mode() -> None:
    coordinator = SatelliteCoordinator()
    entity = type("FakeEntity", (), {"playback_mode": PlaybackMode.AUTOMATION})()
    coordinator.register_entity("android-123", entity)

    result = handle_register_payload(
        coordinator,
        {
            "device_id": "android-123",
            "name": "Bedroom Phone",
            "app_version": "0.2.0",
            "capabilities": {"wake_word": True},
        },
        connection_id="conn-1",
    )

    assert result["playback_mode"] == "automation"


def test_ws_register_accepts_connections_without_id() -> None:
    coordinator = SatelliteCoordinator()
    hass = type("FakeHass", (), {"data": {websocket_api.DOMAIN: {"coordinator": coordinator}}})()
    results = []

    class ConnectionWithoutId:
        def send_result(self, msg_id, result=None):
            results.append((msg_id, result))

    websocket_api.ws_register(
        hass,
        ConnectionWithoutId(),
        {
            "id": 42,
            "type": "hawake_satellite/register",
            "device_id": "android-123",
            "name": "Bedroom Phone",
            "app_version": "0.2.0",
            "capabilities": {"wake_word": True},
        },
    )

    assert results == [
        (
            42,
            {
                "satellite_entity_id": "assist_satellite.bedroom_phone",
                "playback_mode": "app",
                "pipeline_id": "preferred",
            },
        )
    ]
    assert coordinator.client_state("android-123") == SatelliteClientState.IDLE


def test_handle_state_payload_updates_coordinator() -> None:
    coordinator = SatelliteCoordinator()
    handle_register_payload(
        coordinator,
        {
            "device_id": "android-123",
            "name": "Bedroom Phone",
            "app_version": "0.2.0",
            "capabilities": {},
        },
        connection_id="conn-1",
    )

    handle_state_payload(coordinator, {"device_id": "android-123", "state": "responding"})

    assert coordinator.client_state("android-123") == SatelliteClientState.RESPONDING


def test_unknown_device_message_includes_known_clients_and_entities() -> None:
    coordinator = SatelliteCoordinator()
    coordinator.register_client(
        websocket_api.parse_register_message(
            {
                "device_id": "android-123",
                "name": "Bedroom Phone",
                "app_version": "0.2.1",
                "capabilities": {},
            }
        ),
        connection_id="conn-1",
    )
    coordinator.register_entity("configured-456", object())

    assert unknown_device_message(coordinator, "android-999") == (
        "Unknown satellite device: android-999; "
        "registered_clients=android-123; configured_entities=configured-456"
    )


def test_handle_subscribe_payload_emits_queued_downlinks() -> None:
    coordinator = SatelliteCoordinator()
    coordinator.queue_downlink("android-123", {"command": "start_audio_capture", "session_id": "s1"})
    events = []

    handle_subscribe_payload(
        coordinator,
        {"device_id": "android-123"},
        send_event=events.append,
    )

    assert events == [{"command": "start_audio_capture", "session_id": "s1"}]


def test_subscribed_downlinks_emit_immediately() -> None:
    coordinator = SatelliteCoordinator()
    events = []

    handle_subscribe_payload(
        coordinator,
        {"device_id": "android-123"},
        send_event=events.append,
    )
    coordinator.queue_downlink("android-123", {"command": "play_media", "session_id": "s1"})

    assert events == [{"command": "play_media", "session_id": "s1"}]


def test_async_register_websocket_api_registers_commands_once(monkeypatch) -> None:
    calls = []
    hass = type("FakeHass", (), {"data": {}})()

    monkeypatch.setattr(
        websocket_api.websocket_api,
        "async_register_command",
        lambda hass, command: calls.append(command),
    )

    async_register_websocket_api(hass, SatelliteCoordinator())
    async_register_websocket_api(hass, SatelliteCoordinator())

    assert calls == [
        websocket_api.ws_register,
        websocket_api.ws_state,
        websocket_api.ws_subscribe,
        websocket_api.ws_wake_detected,
        websocket_api.ws_audio,
        websocket_api.ws_playback_finished,
    ]


def test_ws_audio_accepts_hyphenated_session_id() -> None:
    coordinator = SatelliteCoordinator()
    coordinator.start_session("5c3eac070d194f68b9d46ac8863529ea", "android-123")
    hass = type("FakeHass", (), {"data": {websocket_api.DOMAIN: {"coordinator": coordinator}}})()
    results = []

    class Connection:
        def send_result(self, msg_id, result=None):
            results.append((msg_id, result))

    run(
        websocket_api.ws_audio(
            hass,
            Connection(),
            {
                "id": 99,
                "type": "hawake_satellite/audio",
                "session_id": "5c3eac07-0d19-4f68-b9d4-6ac8863529ea",
                "pcm": "cGNt",
            },
        )
    )

    assert results == [(99, None)]
    assert run(
        coordinator.audio_queues_by_session[
            "5c3eac070d194f68b9d46ac8863529ea"
        ].get()
    ) == b"pcm"


def test_ws_audio_ignores_unknown_session_without_error() -> None:
    coordinator = SatelliteCoordinator()
    hass = type("FakeHass", (), {"data": {websocket_api.DOMAIN: {"coordinator": coordinator}}})()
    results = []

    class Connection:
        def send_result(self, msg_id, result=None):
            results.append((msg_id, result))

    run(
        websocket_api.ws_audio(
            hass,
            Connection(),
            {
                "id": 100,
                "type": "hawake_satellite/audio",
                "session_id": "missing-session",
                "pcm": "cGNt",
            },
        )
    )

    assert results == [(100, None)]
