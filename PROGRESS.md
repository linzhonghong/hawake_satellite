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
