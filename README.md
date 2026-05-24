# HAWake Satellite

Home Assistant custom integration for the HAWake Android voice satellite app.

## Install with HACS

1. In HACS, open **Custom repositories**.
2. Add `https://github.com/linzhonghong/hawake_satellite`.
3. Select category **Integration**.
4. Install **HAWake Satellite**.
5. Restart Home Assistant.
6. Add the integration from **Settings > Devices & services > Add integration**.

## First test settings

Use App playback for the first end-to-end test:

- `device_id`: Android device id shown/configured in the app.
- `device_name`: Friendly satellite name.
- `playback_mode`: `app`.

Then configure the Android app with the same `device_id`, Home Assistant URL, long-lived access token, and `Assist Satellite` connection mode.

## Automation playback

Automation mode exposes Assist pipeline stages as Home Assistant events so playback can be fully controlled by HA automations.

Listen for `hawake_satellite_pipeline_event` and filter `trigger.event.data.stage`:

- `intent-end`: Assist AI response text is available in `trigger.event.data.response_text`; no TTS media is required.
- `tts-start`: TTS input text is available in `trigger.event.data.response_text`.
- `tts-end`: TTS media is available in `trigger.event.data.media_url` and `trigger.event.data.mime_type`; `trigger.event.data.duration_seconds` is included when the duration can be inferred.

The event also includes `trigger.event.data.playback_mode`. Automations that perform playback should guard on `playback_mode == "automation"` so they do not also run while App or Media player mode owns playback.

For text-only speakers such as `xiaodu_mcp.speak`, prefer `intent-end`. After the automation finishes playback, call `hawake_satellite.playback_finished` with `session_id: "{{ trigger.event.data.session_id }}"`.

For safer continuous conversation timing, start the text speaker from `intent-end`, then optionally wait for the matching `tts-end` event. If `duration_seconds` is present, use it plus a buffer; otherwise fall back to a text-length estimate with configurable minimum and maximum wait seconds.

## Status

This repository contains an early Assist Satellite implementation for testing. App playback is the primary validation path; media player and automation playback are still experimental.
