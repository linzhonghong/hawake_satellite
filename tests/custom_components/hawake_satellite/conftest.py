"""Shared Home Assistant test doubles for local unit tests."""

from __future__ import annotations

import sys
from enum import IntFlag
from types import ModuleType
from typing import Any


class FakeConfigFlow:
    """Small Home Assistant ConfigFlow stand-in for unit tests."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__()

    async def async_set_unique_id(self, unique_id: str) -> None:
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self) -> None:
        return None

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: Any | None = None,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
        }


class FakeSchema:
    """Small voluptuous Schema stand-in for unit tests."""

    def __init__(self, schema: dict[Any, Any]) -> None:
        self.schema = schema


class FakeActiveConnection:
    """Small ActiveConnection stand-in for type imports."""

    id = "conn-1"


class FakeAssistSatelliteEntity:
    """Small AssistSatelliteEntity stand-in for unit tests."""

    def __init__(self) -> None:
        self.tts_finished = 0

    def tts_response_finished(self) -> None:
        self.tts_finished += 1


class FakeAssistSatelliteEntityFeature(IntFlag):
    """Small AssistSatelliteEntityFeature stand-in for unit tests."""

    ANNOUNCE = 1
    START_CONVERSATION = 2


def _websocket_command(schema: dict[Any, Any]):
    """Return a no-op websocket command decorator."""

    def decorator(func):
        return func

    return decorator


homeassistant = ModuleType("homeassistant")
components = ModuleType("homeassistant.components")
websocket_api = ModuleType("homeassistant.components.websocket_api")
assist_satellite = ModuleType("homeassistant.components.assist_satellite")
config_entries = ModuleType("homeassistant.config_entries")
core = ModuleType("homeassistant.core")
voluptuous = ModuleType("voluptuous")

websocket_api.ActiveConnection = FakeActiveConnection
websocket_api.websocket_command = _websocket_command
websocket_api.async_response = lambda func: func
websocket_api.async_register_command = lambda hass, command: None
assist_satellite.AssistSatelliteEntity = FakeAssistSatelliteEntity
assist_satellite.AssistSatelliteEntityFeature = FakeAssistSatelliteEntityFeature
config_entries.ConfigEntry = object
config_entries.ConfigFlow = FakeConfigFlow
core.HomeAssistant = object
core.ServiceCall = object
core.callback = lambda func: func
voluptuous.Schema = FakeSchema
voluptuous.Required = lambda key, **kwargs: key
voluptuous.Optional = lambda key, **kwargs: key
voluptuous.In = lambda values: values

sys.modules["homeassistant"] = homeassistant
sys.modules["homeassistant.components"] = components
sys.modules["homeassistant.components.websocket_api"] = websocket_api
sys.modules["homeassistant.components.assist_satellite"] = assist_satellite
sys.modules["homeassistant.config_entries"] = config_entries
sys.modules["homeassistant.core"] = core
sys.modules["voluptuous"] = voluptuous
