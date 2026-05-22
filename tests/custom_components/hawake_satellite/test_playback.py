"""Tests for HAWake Satellite playback strategies."""

from __future__ import annotations

import asyncio
from asyncio import run

from custom_components.hawake_satellite.const import PlaybackMode
from custom_components.hawake_satellite import handle_playback_finished_callback
from custom_components.hawake_satellite.playback import PlaybackRequest, PlaybackRouter


class FakeCoordinator:
    """Small coordinator test double."""

    def __init__(self) -> None:
        self.downlinks = []
        self.sessions = {}

    def queue_downlink(self, device_id: str, payload: dict) -> None:
        self.downlinks.append((device_id, payload))

    def start_session(self, session_id: str, device_id: str) -> None:
        self.sessions[session_id] = device_id

    def device_for_session(self, session_id: str) -> str | None:
        return self.sessions.get(session_id)

    def finish_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)


class FakeBus:
    """Small Home Assistant event bus test double."""

    def __init__(self) -> None:
        self.events = []
        self.listeners = {}

    def async_fire(self, event_type: str, event_data: dict) -> None:
        self.events.append((event_type, event_data))

    def async_listen(self, event_type: str, listener):
        self.listeners.setdefault(event_type, []).append(listener)

        def unsubscribe() -> None:
            self.listeners[event_type].remove(listener)

        return unsubscribe

    def fire_state_changed(self, entity_id: str, state: str) -> None:
        event = type(
            "StateChangedEvent",
            (),
            {
                "data": {
                    "entity_id": entity_id,
                    "new_state": type("State", (), {"state": state})(),
                }
            },
        )()
        for listener in list(self.listeners.get("state_changed", [])):
            listener(event)


class FakeServices:
    """Small Home Assistant service registry test double."""

    def __init__(self) -> None:
        self.calls = []
        self.should_fail = False

    async def async_call(
        self,
        domain: str,
        service: str,
        service_data: dict,
        blocking: bool = False,
    ) -> None:
        if self.should_fail:
            raise RuntimeError("service failed")
        self.calls.append((domain, service, service_data, blocking))


class FakeHass:
    """Small Home Assistant test double."""

    def __init__(self, base_url: str = "http://ha.local:8123") -> None:
        self.bus = FakeBus()
        self.services = FakeServices()
        self.config = type(
            "Config",
            (),
            {"api": type("ApiConfig", (), {"base_url": base_url})()},
        )()


class FakeEntity:
    """Assist satellite entity test double."""

    def __init__(self) -> None:
        self.tts_finished = 0

    def tts_response_finished(self) -> None:
        self.tts_finished += 1


def test_app_playback_queues_play_media() -> None:
    coordinator = FakeCoordinator()
    router = PlaybackRouter(coordinator=coordinator)

    run(
        router.play(
            PlaybackRequest(
                playback_mode=PlaybackMode.APP,
                device_id="android-123",
                session_id="s1",
                media_url="/api/hawake_satellite/tts/s1",
                mime_type="audio/mpeg",
                response_text="OK",
            )
        )
    )

    assert coordinator.downlinks == [
        (
            "android-123",
            {
                "command": "play_media",
                "session_id": "s1",
                "media_url": "/api/hawake_satellite/tts/s1",
                "mime_type": "audio/mpeg",
            },
        )
    ]


def test_media_player_playback_requires_entity_id() -> None:
    router = PlaybackRouter(coordinator=FakeCoordinator())

    try:
        run(
            router.play(
                PlaybackRequest(
                    playback_mode=PlaybackMode.MEDIA_PLAYER,
                    device_id="android-123",
                    session_id="s1",
                    media_url="/media/s1.mp3",
                    mime_type="audio/mpeg",
                    response_text="OK",
                )
            )
        )
    except ValueError as err:
        assert "media_player_entity_id" in str(err)
    else:
        raise AssertionError("Expected ValueError")


def test_media_player_playback_calls_service_and_waits_for_completion() -> None:
    async def scenario():
        coordinator = FakeCoordinator()
        hass = FakeHass()
        router = PlaybackRouter(coordinator=coordinator, hass=hass)

        task = asyncio.create_task(
            router.play(
                PlaybackRequest(
                    playback_mode=PlaybackMode.MEDIA_PLAYER,
                    device_id="android-123",
                    session_id="s1",
                    media_url="https://ha.local/media/s1.mp3",
                    mime_type="audio/mpeg",
                    response_text="OK",
                    media_player_entity_id="media_player.living_room",
                )
            )
        )
        await asyncio.sleep(0)

        assert hass.services.calls == [
            (
                "media_player",
                "play_media",
                {
                    "entity_id": "media_player.living_room",
                    "media_content_id": "https://ha.local/media/s1.mp3",
                    "media_content_type": "audio/mpeg",
                },
                True,
            )
        ]

        hass.bus.fire_state_changed("media_player.living_room", "playing")
        hass.bus.fire_state_changed("media_player.living_room", "idle")
        return await task

    result = run(scenario())

    assert result.status == "success"


def test_media_player_playback_resolves_relative_media_url() -> None:
    async def scenario():
        hass = FakeHass(base_url="http://ha.local:8123/")
        router = PlaybackRouter(coordinator=FakeCoordinator(), hass=hass)
        task = asyncio.create_task(
            router.play(
                PlaybackRequest(
                    playback_mode=PlaybackMode.MEDIA_PLAYER,
                    device_id="android-123",
                    session_id="s1",
                    media_url="/api/hawake_satellite/tts/s1",
                    mime_type="audio/mpeg",
                    response_text="OK",
                    media_player_entity_id="media_player.living_room",
                )
            )
        )
        await asyncio.sleep(0)
        hass.bus.fire_state_changed("media_player.living_room", "playing")
        hass.bus.fire_state_changed("media_player.living_room", "idle")
        await task
        return hass

    hass = run(scenario())

    assert hass.services.calls[0][2]["media_content_id"] == (
        "http://ha.local:8123/api/hawake_satellite/tts/s1"
    )


def test_media_player_playback_reports_error_when_service_call_fails() -> None:
    async def scenario():
        hass = FakeHass()
        hass.services.should_fail = True
        router = PlaybackRouter(coordinator=FakeCoordinator(), hass=hass)

        return await router.play(
            PlaybackRequest(
                playback_mode=PlaybackMode.MEDIA_PLAYER,
                device_id="android-123",
                session_id="s1",
                media_url="https://ha.local/media/s1.mp3",
                mime_type="audio/mpeg",
                response_text="OK",
                media_player_entity_id="media_player.living_room",
            )
        )

    result = run(scenario())

    assert result.status == "error"


def test_automation_playback_fires_event() -> None:
    coordinator = FakeCoordinator()
    hass = FakeHass()
    router = PlaybackRouter(coordinator=coordinator, hass=hass)

    run(
        router.play(
            PlaybackRequest(
                playback_mode=PlaybackMode.AUTOMATION,
                device_id="android-123",
                session_id="s1",
                media_url="/media/s1.mp3",
                mime_type="audio/mpeg",
                response_text="OK",
            )
        )
    )

    assert coordinator.downlinks == [
        (
            "android-123",
            {"command": "external_playback_started", "session_id": "s1"},
        )
    ]
    assert hass.bus.events == [
        (
            "hawake_satellite_playback_requested",
            {
                "device_id": "android-123",
                "session_id": "s1",
                "media_url": "/media/s1.mp3",
                "mime_type": "audio/mpeg",
                "response_text": "OK",
                "callback_service": "hawake_satellite.playback_finished",
            },
        )
    ]


def test_playback_finished_callback_uses_session_owner() -> None:
    coordinator = FakeCoordinator()
    coordinator.start_session("s1", "android-123")
    entity = FakeEntity()

    handle_playback_finished_callback(
        coordinator,
        {"session_id": "s1", "status": "success"},
        entity_lookup=lambda device_id: entity if device_id == "android-123" else None,
    )

    assert entity.tts_finished == 1
    assert coordinator.downlinks == [
        (
            "android-123",
            {
                "command": "playback_callback_recorded",
                "session_id": "s1",
                "status": "success",
            },
        )
    ]
    assert coordinator.device_for_session("s1") is None
