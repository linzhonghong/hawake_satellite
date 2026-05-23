"""Custom WebSocket API for HAWake Satellite Android clients."""

from __future__ import annotations

import base64
from uuid import uuid4
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, SatelliteClientState
from .coordinator import SatelliteCoordinator
from .protocol import parse_register_message, parse_state_message


def handle_register_payload(
    coordinator: SatelliteCoordinator,
    payload: dict[str, Any],
    connection_id: str,
) -> dict[str, Any]:
    """Register an Android satellite client and return HA metadata."""
    registration = parse_register_message(payload)
    coordinator.register_client(registration, connection_id)
    entity = coordinator.entity_for_device(registration.device_id)
    playback_mode = getattr(entity, "playback_mode", None)
    playback_mode = getattr(playback_mode, "value", playback_mode) or "app"
    return {
        "satellite_entity_id": f"assist_satellite.{registration.name.lower().replace(' ', '_')}",
        "playback_mode": playback_mode,
        "pipeline_id": "preferred",
    }


def handle_state_payload(coordinator: SatelliteCoordinator, payload: dict[str, Any]) -> None:
    """Apply a state update from Android."""
    state = parse_state_message(payload)
    coordinator.update_state(state.device_id, state.state)


def handle_subscribe_payload(
    coordinator: SatelliteCoordinator,
    payload: dict[str, Any],
    send_event,
) -> Any:
    """Subscribe an Android client to queued downlink commands."""
    device_id = payload.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("Missing required string field: device_id")
    return coordinator.subscribe_downlinks(device_id.strip(), send_event)


def unknown_device_message(coordinator: SatelliteCoordinator, device_id: str) -> str:
    """Build a diagnostic unknown-device message for Android."""
    registered_clients = ",".join(sorted(coordinator.clients_by_device_id)) or "<none>"
    configured_entities = ",".join(sorted(coordinator.entities_by_device_id)) or "<none>"
    return (
        f"Unknown satellite device: {device_id}; "
        f"registered_clients={registered_clients}; "
        f"configured_entities={configured_entities}"
    )


def _connection_id(connection: websocket_api.ActiveConnection) -> str:
    """Return a stable id for this WebSocket connection."""
    return str(getattr(connection, "id", None) or id(connection))


@callback
def async_register_websocket_api(
    hass: HomeAssistant,
    coordinator: SatelliteCoordinator,
) -> None:
    """Register HAWake Satellite WebSocket commands."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data["coordinator"] = coordinator
    if domain_data.get("websocket_api_registered"):
        return
    websocket_api.async_register_command(hass, ws_register)
    websocket_api.async_register_command(hass, ws_state)
    websocket_api.async_register_command(hass, ws_subscribe)
    websocket_api.async_register_command(hass, ws_wake_detected)
    websocket_api.async_register_command(hass, ws_audio)
    websocket_api.async_register_command(hass, ws_playback_finished)
    domain_data["websocket_api_registered"] = True


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hawake_satellite/register",
        vol.Required("device_id"): str,
        vol.Required("name"): str,
        vol.Required("app_version"): str,
        vol.Optional("capabilities", default={}): dict,
    }
)
@callback
def ws_register(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle Android client registration."""
    coordinator: SatelliteCoordinator = hass.data[DOMAIN]["coordinator"]
    result = handle_register_payload(coordinator, msg, _connection_id(connection))
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hawake_satellite/state",
        vol.Required("device_id"): str,
        vol.Required("state"): vol.In([state.value for state in SatelliteClientState]),
    }
)
@callback
def ws_state(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle Android state updates."""
    coordinator: SatelliteCoordinator = hass.data[DOMAIN]["coordinator"]
    handle_state_payload(coordinator, msg)
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hawake_satellite/subscribe",
        vol.Required("device_id"): str,
    }
)
@callback
def ws_subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Subscribe Android client to HA downlink commands."""
    coordinator: SatelliteCoordinator = hass.data[DOMAIN]["coordinator"]
    subscription_id = msg["id"]
    connection_id = _connection_id(connection)

    def _send_event(payload: dict[str, Any]) -> None:
        connection.send_message({"id": subscription_id, "type": "event", "event": payload})

    unsubscribe = handle_subscribe_payload(coordinator, msg, _send_event)
    if hasattr(connection, "subscriptions"):
        connection.subscriptions[subscription_id] = lambda: (
            unsubscribe(),
            coordinator.disconnect(connection_id),
        )
    connection.send_result(subscription_id)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hawake_satellite/wake_detected",
        vol.Required("device_id"): str,
        vol.Required("wake_phrase"): str,
    }
)
@callback
def ws_wake_detected(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Start a satellite Assist run from Android wake-word detection."""
    coordinator: SatelliteCoordinator = hass.data[DOMAIN]["coordinator"]
    device_id = msg["device_id"]
    entity = coordinator.entity_for_device(device_id)
    if entity is None:
        connection.send_error(msg["id"], "unknown_device", unknown_device_message(coordinator, device_id))
        return
    session_id = uuid4().hex
    coordinator.start_session(session_id, device_id)
    hass.async_create_task(
        entity.async_accept_android_wake(
            session_id=session_id,
            wake_phrase=msg["wake_phrase"],
        )
    )
    connection.send_result(msg["id"], {"session_id": session_id})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hawake_satellite/audio",
        vol.Required("session_id"): str,
        vol.Optional("pcm"): str,
        vol.Optional("end", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_audio(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Receive base64 PCM audio from Android."""
    coordinator: SatelliteCoordinator = hass.data[DOMAIN]["coordinator"]
    session_id = msg["session_id"]
    if msg.get("end"):
        await coordinator.finish_audio(session_id)
    else:
        await coordinator.push_audio(session_id, base64.b64decode(msg["pcm"]))
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hawake_satellite/playback_finished",
        vol.Required("session_id"): str,
        vol.Optional("status", default="success"): str,
    }
)
@callback
def ws_playback_finished(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle app playback completion from Android."""
    coordinator: SatelliteCoordinator = hass.data[DOMAIN]["coordinator"]
    device_id = coordinator.device_for_session(msg["session_id"])
    if device_id is not None:
        entity = coordinator.entity_for_device(device_id)
        if entity is not None:
            entity.tts_response_finished()
        coordinator.finish_session(msg["session_id"])
    connection.send_result(msg["id"])
