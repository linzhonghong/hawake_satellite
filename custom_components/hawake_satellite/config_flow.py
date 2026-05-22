"""Config flow for HAWake Satellite."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_MEDIA_PLAYER_ENTITY_ID,
    CONF_PIPELINE_ID,
    CONF_PLAYBACK_MODE,
    CONF_PLAYBACK_SCRIPT_ENTITY_ID,
    DOMAIN,
    PlaybackMode,
)


class HAWakeSatelliteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HAWake Satellite."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            playback_mode = PlaybackMode(user_input[CONF_PLAYBACK_MODE])
            if (
                playback_mode is PlaybackMode.MEDIA_PLAYER
                and not user_input.get(CONF_MEDIA_PLAYER_ENTITY_ID)
            ):
                errors[CONF_MEDIA_PLAYER_ENTITY_ID] = "missing_media_player"
            if not errors:
                await self.async_set_unique_id(user_input[CONF_DEVICE_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_DEVICE_NAME],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): str,
                    vol.Required(CONF_DEVICE_NAME): str,
                    vol.Required(CONF_PLAYBACK_MODE, default=PlaybackMode.APP): vol.In(
                        [mode.value for mode in PlaybackMode]
                    ),
                    vol.Optional(CONF_MEDIA_PLAYER_ENTITY_ID): str,
                    vol.Optional(CONF_PLAYBACK_SCRIPT_ENTITY_ID): str,
                    vol.Optional(CONF_PIPELINE_ID): str,
                }
            ),
            errors=errors,
        )
