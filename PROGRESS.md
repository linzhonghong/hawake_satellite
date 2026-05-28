# HAWake Satellite Progress

## 2026-05-29

- Fixed Android wake pipeline session correlation for `0.2.18`.
- Root cause: HACS used HA pipeline `run_id` as the Android downlink `session_id`, and generated a fresh UUID when `run_id` was absent. On this HA build, related pipeline events can report different or missing `run_id` values, so Android saw different session ids for `start_audio_capture`, `conversation_message`, and `play_media`.
- Android wake runs now pin pipeline events to the original Android session id created by `hawake_satellite/wake_detected`.
- Response text caching, conversation dedupe, pipeline stage events, App playback, and playback callbacks now use that same Android session id during a wake-triggered conversation.
- Added regression coverage for mixed/missing HA `run_id` values during one Android wake conversation.
- Verification: `python -m pytest -q` passed with 64 tests.

## 2026-05-23

- Added 0.2.17 conversation downlink dedupe so `intent-end` and `tts-start` do not send duplicate assistant `conversation_message` payloads.
- Bumped HACS integration manifest version to `0.2.17`.
- Added 0.2.16 live conversation downlink support for Android.
- Extracts Assist `stt-end` text and sends recognized user speech as `conversation_message`.
- Sends Assist response text from `intent-end` / `tts-start` as assistant `conversation_message`.
- Includes `response_text` in App playback `play_media` downlinks.
- Verification: `python -m pytest tests/test_pipeline_events.py tests/custom_components/hawake_satellite/test_playback.py tests/custom_components/hawake_satellite/test_assist_satellite.py` passed with 24 tests.
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
