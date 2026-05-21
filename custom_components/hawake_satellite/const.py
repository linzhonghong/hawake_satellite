"""Constants for HAWake Satellite."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

DOMAIN: Final = "hawake_satellite"
PLATFORMS: Final = ["assist_satellite"]

CONF_DEVICE_ID: Final = "device_id"
CONF_DEVICE_NAME: Final = "device_name"
CONF_PLAYBACK_MODE: Final = "playback_mode"
CONF_MEDIA_PLAYER_ENTITY_ID: Final = "media_player_entity_id"
CONF_PLAYBACK_SCRIPT_ENTITY_ID: Final = "playback_script_entity_id"
CONF_PIPELINE_ID: Final = "pipeline_id"

DEFAULT_CAPTURE_TIMEOUT_SECONDS: Final = 6
DEFAULT_PLAYBACK_TIMEOUT_SECONDS: Final = 45
DEFAULT_RECONNECT_GRACE_SECONDS: Final = 15

SERVICE_PLAYBACK_FINISHED: Final = "playback_finished"


class PlaybackMode(StrEnum):
    """Supported response playback modes."""

    APP = "app"
    MEDIA_PLAYER = "media_player"
    AUTOMATION = "automation"


class SatelliteClientState(StrEnum):
    """State values shared with the Android client."""

    OFFLINE = "offline"
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    RESPONDING = "responding"
    ERROR = "error"
