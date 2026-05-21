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

## Status

This repository contains an early Assist Satellite implementation for testing. App playback is the primary validation path; media player and automation playback are still experimental.
