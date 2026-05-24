# HAWake Satellite Progress

## 2026-05-23

- Investigated no-speaker closed-loop validation failure.
- Found `assist_satellite.rong_yao` was a restored orphan entity because the platform failed during setup.
- Root cause: `SatelliteCoordinator.register_entity()` refreshed entity state before Home Assistant had attached `hass` to the entity.
- Fixed coordinator state refresh to defer writes until the entity has been added to Home Assistant.
- Added regression coverage for pending entities.
- Verification: `PYTHONPATH=. pytest -q` passed with 48 tests.
- Added HACS OptionsFlow for switching playback mode after setup.
- Entity setup now applies `entry.options` over `entry.data`, so App / Media player / Automation can be changed from Home Assistant without recreating the integration.
- Added tests for OptionsFlow updates, media player validation, and options overriding config entry data.
- Fixed OptionsFlow entry creation for real Home Assistant by returning option values through `data`, not an unsupported `options` keyword.
- Added HAWake Satellite brand icons derived from the Android app icon for Home Assistant and HACS display.
- Updated WebSocket registration metadata to report the HA entity playback mode instead of always returning `app`.
- Investigated Automation playback sending `text: ''` to `xiaodu_mcp.speak`.
- Root cause: real Assist `tts-end` events can contain only TTS media output; the spoken text is emitted earlier in `tts-start` / `intent-end`.
- Updated Automation mode to trigger playback requests directly from Assist response text events instead of waiting for TTS media output.
- Kept per-run response-text caching for App / Media player routes that still need `tts-end` media output.
- Added `hawake_satellite_pipeline_event` so HA automations can freely choose `intent-end`, `tts-start`, or `tts-end`.
- Added regression tests for response text extraction and Automation event payloads.
- Added best-effort TTS media duration probing for `tts-end` pipeline events.
- Planned Automation timing around `duration_seconds + buffer`, with text-length fallback when TTS is disabled, slow, or duration probing fails.
- Added `playback_mode` to `hawake_satellite_pipeline_event` so HA automations can ignore App / Media player playback modes.
