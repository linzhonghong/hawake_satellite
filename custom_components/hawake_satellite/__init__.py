"""HAWake Satellite custom integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, PLATFORMS, SERVICE_PLAYBACK_FINISHED
from .coordinator import SatelliteCoordinator
from .websocket_api import async_register_websocket_api


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HAWake Satellite from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    coordinator = hass.data[DOMAIN].setdefault("coordinator", SatelliteCoordinator())
    hass.data[DOMAIN][entry.entry_id] = {"entry": entry, "coordinator": coordinator}
    async_register_websocket_api(hass, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a HAWake Satellite config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_PLAYBACK_FINISHED):
        return

    async def _handle_playback_finished(call: ServiceCall) -> None:
        """Handle automation playback completion callback."""
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator is None:
            return
        handle_playback_finished_callback(coordinator, call.data)

    hass.services.async_register(DOMAIN, SERVICE_PLAYBACK_FINISHED, _handle_playback_finished)


def handle_playback_finished_callback(
    coordinator,
    data: dict[str, Any],
    entity_lookup=None,
) -> None:
    """Record automation playback completion and finish the owning session."""
    return _handle_playback_finished_callback(
        coordinator,
        data,
        entity_lookup=entity_lookup or coordinator.entity_for_device,
    )


def _handle_playback_finished_callback(
    coordinator,
    data: dict[str, Any],
    entity_lookup,
) -> None:
    """Record playback completion and notify the owning entity."""
    session_id = data["session_id"]
    status = data.get("status", "success")
    device_id = coordinator.device_for_session(session_id)
    if device_id is None:
        return
    entity = entity_lookup(device_id)
    if entity is not None:
        entity.tts_response_finished()
    coordinator.queue_downlink(
        device_id=device_id,
        payload={
            "command": "playback_callback_recorded",
            "session_id": session_id,
            "status": status,
        },
    )
    coordinator.finish_session(session_id)
