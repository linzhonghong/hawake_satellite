"""Tests for HAWake Satellite config flow."""

from __future__ import annotations

import sys
from asyncio import run
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


homeassistant = ModuleType("homeassistant")
config_entries = ModuleType("homeassistant.config_entries")
config_entries.ConfigEntry = object
config_entries.ConfigFlow = FakeConfigFlow
core = ModuleType("homeassistant.core")
core.HomeAssistant = object
core.ServiceCall = object
core.callback = lambda func: func
voluptuous = ModuleType("voluptuous")
voluptuous.Schema = FakeSchema
voluptuous.Required = lambda key, **kwargs: key
voluptuous.Optional = lambda key, **kwargs: key
voluptuous.In = lambda values: values

sys.modules["homeassistant"] = homeassistant
sys.modules["homeassistant.config_entries"] = config_entries
sys.modules["homeassistant.core"] = core
sys.modules["voluptuous"] = voluptuous

from custom_components.hawake_satellite.config_flow import HAWakeSatelliteConfigFlow
from custom_components.hawake_satellite.const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_MEDIA_PLAYER_ENTITY_ID,
    CONF_PLAYBACK_MODE,
    CONF_PLAYBACK_SCRIPT_ENTITY_ID,
    PlaybackMode,
)


def test_user_flow_creates_app_playback_entry() -> None:
    flow = HAWakeSatelliteConfigFlow()

    result = run(
        flow.async_step_user(
            {
                CONF_DEVICE_ID: "android-123",
                CONF_DEVICE_NAME: "Bedroom Phone",
                CONF_PLAYBACK_MODE: PlaybackMode.APP,
            }
        )
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "Bedroom Phone"
    assert result["data"][CONF_DEVICE_ID] == "android-123"
    assert result["data"][CONF_PLAYBACK_MODE] == PlaybackMode.APP


def test_media_player_mode_requires_entity() -> None:
    flow = HAWakeSatelliteConfigFlow()

    result = run(
        flow.async_step_user(
            {
                CONF_DEVICE_ID: "android-123",
                CONF_DEVICE_NAME: "Bedroom Phone",
                CONF_PLAYBACK_MODE: PlaybackMode.MEDIA_PLAYER,
            }
        )
    )

    assert result["type"] == "form"
    assert result["errors"][CONF_MEDIA_PLAYER_ENTITY_ID] == "missing_media_player"


def test_automation_mode_does_not_require_script() -> None:
    flow = HAWakeSatelliteConfigFlow()

    result = run(
        flow.async_step_user(
            {
                CONF_DEVICE_ID: "android-123",
                CONF_DEVICE_NAME: "Bedroom Phone",
                CONF_PLAYBACK_MODE: PlaybackMode.AUTOMATION,
            }
        )
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_PLAYBACK_MODE] == PlaybackMode.AUTOMATION
