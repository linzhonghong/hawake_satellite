"""Tests for HAWake Satellite coordinator."""

from __future__ import annotations

from asyncio import run
import sys
from types import ModuleType


homeassistant = ModuleType("homeassistant")
config_entries = ModuleType("homeassistant.config_entries")
config_entries.ConfigEntry = object
core = ModuleType("homeassistant.core")
core.HomeAssistant = object
core.ServiceCall = object
sys.modules.setdefault("homeassistant", homeassistant)
sys.modules.setdefault("homeassistant.config_entries", config_entries)
sys.modules.setdefault("homeassistant.core", core)

from custom_components.hawake_satellite.const import SatelliteClientState
from custom_components.hawake_satellite.coordinator import (
    SatelliteCoordinator,
    normalize_session_id,
)
from custom_components.hawake_satellite.protocol import RegisterMessage


class FakeEntity:
    """Entity test double that records HA state refresh requests."""

    def __init__(self) -> None:
        self.hass = object()
        self.write_state_calls = 0

    def async_write_ha_state(self) -> None:
        self.write_state_calls += 1


class PendingEntity:
    """Entity test double that has not been added to Home Assistant yet."""

    hass = None

    def async_write_ha_state(self) -> None:
        raise RuntimeError("State should not be written before hass is set")


def test_register_client_marks_device_idle() -> None:
    coordinator = SatelliteCoordinator()

    coordinator.register_client(
        RegisterMessage(
            device_id="android-123",
            name="Bedroom Phone",
            app_version="0.2.0",
            capabilities={"wake_word": True},
        ),
        connection_id="conn-1",
    )

    assert coordinator.client_state("android-123") == SatelliteClientState.IDLE
    assert coordinator.connection_for("android-123") == "conn-1"


def test_register_client_refreshes_registered_entity_state() -> None:
    coordinator = SatelliteCoordinator()
    entity = FakeEntity()
    coordinator.register_entity("android-123", entity)

    coordinator.register_client(
        RegisterMessage("android-123", "Bedroom Phone", "0.2.0", {}),
        connection_id="conn-1",
    )

    assert entity.write_state_calls == 1


def test_register_entity_defers_refresh_until_entity_is_added_to_hass() -> None:
    coordinator = SatelliteCoordinator()
    coordinator.register_client(
        RegisterMessage("android-123", "Bedroom Phone", "0.2.0", {}),
        connection_id="conn-1",
    )

    coordinator.register_entity("android-123", PendingEntity())

    assert coordinator.entity_for_device("android-123") is not None


def test_disconnect_marks_device_offline() -> None:
    coordinator = SatelliteCoordinator()
    coordinator.register_client(
        RegisterMessage("android-123", "Bedroom Phone", "0.2.0", {}),
        connection_id="conn-1",
    )

    coordinator.disconnect("conn-1")

    assert coordinator.client_state("android-123") == SatelliteClientState.OFFLINE


def test_disconnect_refreshes_registered_entity_state() -> None:
    coordinator = SatelliteCoordinator()
    entity = FakeEntity()
    coordinator.register_entity("android-123", entity)
    coordinator.register_client(
        RegisterMessage("android-123", "Bedroom Phone", "0.2.0", {}),
        connection_id="conn-1",
    )

    coordinator.disconnect("conn-1")

    assert entity.write_state_calls == 2


def test_update_state_refreshes_registered_entity_state() -> None:
    coordinator = SatelliteCoordinator()
    entity = FakeEntity()
    coordinator.register_entity("android-123", entity)
    coordinator.register_client(
        RegisterMessage("android-123", "Bedroom Phone", "0.2.0", {}),
        connection_id="conn-1",
    )

    coordinator.update_state("android-123", SatelliteClientState.LISTENING)

    assert entity.write_state_calls == 2


def test_disconnect_old_connection_does_not_mark_reconnected_device_offline() -> None:
    coordinator = SatelliteCoordinator()
    registration = RegisterMessage("android-123", "Bedroom Phone", "0.2.0", {})
    coordinator.register_client(registration, connection_id="conn-1")
    coordinator.register_client(registration, connection_id="conn-2")

    coordinator.disconnect("conn-1")

    assert coordinator.client_state("android-123") == SatelliteClientState.IDLE
    assert coordinator.connection_for("android-123") == "conn-2"


def test_queues_downlink_for_subscribed_device() -> None:
    coordinator = SatelliteCoordinator()
    coordinator.register_client(
        RegisterMessage("android-123", "Bedroom Phone", "0.2.0", {}),
        connection_id="conn-1",
    )

    coordinator.queue_downlink(
        "android-123",
        {"command": "start_audio_capture", "session_id": "s1"},
    )

    assert coordinator.pop_downlinks("android-123") == [
        {"command": "start_audio_capture", "session_id": "s1"}
    ]


def test_tracks_active_session_owner() -> None:
    coordinator = SatelliteCoordinator()

    coordinator.start_session("session-1", "android-123")

    assert coordinator.device_for_session("session-1") == "android-123"
    coordinator.finish_session("session-1")
    assert coordinator.device_for_session("session-1") is None


def test_normalizes_hyphenated_uuid_session_ids() -> None:
    assert normalize_session_id("5c3eac07-0d19-4f68-b9d4-6ac8863529ea") == (
        "5c3eac070d194f68b9d46ac8863529ea"
    )


def test_audio_accepts_hyphenated_session_id_for_compact_session() -> None:
    coordinator = SatelliteCoordinator()
    coordinator.start_session("5c3eac070d194f68b9d46ac8863529ea", "android-123")

    assert run(
        coordinator.push_audio("5c3eac07-0d19-4f68-b9d4-6ac8863529ea", b"pcm")
    )
    assert run(
        coordinator.audio_queues_by_session[
            "5c3eac070d194f68b9d46ac8863529ea"
        ].get()
    ) == b"pcm"


def test_audio_ignores_unknown_session_without_raising() -> None:
    coordinator = SatelliteCoordinator()

    assert run(coordinator.push_audio("missing-session", b"pcm")) is False
    assert run(coordinator.finish_audio("missing-session")) is False
