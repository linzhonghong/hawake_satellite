"""Runtime coordinator for connected Android satellite clients."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import UUID

from .const import SatelliteClientState
from .protocol import RegisterMessage


def normalize_session_id(session_id: str) -> str:
    """Normalize UUID-like session ids to compact hex."""
    try:
        return UUID(session_id).hex
    except ValueError:
        return session_id


@dataclass
class SatelliteClient:
    """Connected Android satellite client metadata."""

    registration: RegisterMessage
    connection_id: str
    state: SatelliteClientState = SatelliteClientState.IDLE


@dataclass
class SatelliteCoordinator:
    """Track satellite clients, state, sessions, and downlink commands."""

    clients_by_device_id: dict[str, SatelliteClient] = field(default_factory=dict)
    device_id_by_connection: dict[str, str] = field(default_factory=dict)
    device_id_by_session: dict[str, str] = field(default_factory=dict)
    entities_by_device_id: dict[str, Any] = field(default_factory=dict)
    audio_queues_by_session: dict[str, asyncio.Queue[bytes | None]] = field(
        default_factory=dict
    )
    downlinks_by_device_id: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    downlink_callbacks_by_device_id: dict[
        str, list[Callable[[dict[str, Any]], None]]
    ] = field(default_factory=lambda: defaultdict(list))

    def register_client(self, registration: RegisterMessage, connection_id: str) -> None:
        """Register or refresh an Android client connection."""
        existing_client = self.clients_by_device_id.get(registration.device_id)
        if existing_client is not None:
            self.device_id_by_connection.pop(existing_client.connection_id, None)
        self.clients_by_device_id[registration.device_id] = SatelliteClient(
            registration=registration,
            connection_id=connection_id,
        )
        self.device_id_by_connection[connection_id] = registration.device_id
        self._refresh_entity_state(registration.device_id)

    def disconnect(self, connection_id: str) -> None:
        """Mark the client behind a connection as offline."""
        device_id = self.device_id_by_connection.pop(connection_id, None)
        if device_id is None:
            return
        client = self.clients_by_device_id.get(device_id)
        if client is not None and client.connection_id == connection_id:
            client.state = SatelliteClientState.OFFLINE
            self._refresh_entity_state(device_id)

    def update_state(self, device_id: str, state: SatelliteClientState) -> None:
        """Update a connected client's state."""
        self.clients_by_device_id[device_id].state = state
        self._refresh_entity_state(device_id)

    def register_entity(self, device_id: str, entity: Any) -> None:
        """Register the HA entity that represents an Android device."""
        self.entities_by_device_id[device_id] = entity
        if device_id in self.clients_by_device_id:
            self._refresh_entity_state(device_id)

    def entity_for_device(self, device_id: str) -> Any | None:
        """Return the entity for an Android device."""
        return self.entities_by_device_id.get(device_id)

    def client_state(self, device_id: str) -> SatelliteClientState:
        """Return the latest known client state."""
        client = self.clients_by_device_id.get(device_id)
        return SatelliteClientState.OFFLINE if client is None else client.state

    def _refresh_entity_state(self, device_id: str) -> None:
        """Ask Home Assistant to re-read entity availability and state."""
        entity = self.entities_by_device_id.get(device_id)
        if entity is None:
            return
        write_state = getattr(entity, "async_write_ha_state", None)
        if write_state is not None:
            write_state()

    def connection_for(self, device_id: str) -> str | None:
        """Return the current HA WebSocket connection id for a device."""
        client = self.clients_by_device_id.get(device_id)
        return None if client is None else client.connection_id

    def queue_downlink(self, device_id: str, payload: dict[str, Any]) -> None:
        """Queue a command for Android."""
        callbacks = self.downlink_callbacks_by_device_id.get(device_id, [])
        if callbacks:
            for callback in list(callbacks):
                callback(payload)
            return
        self.downlinks_by_device_id[device_id].append(payload)

    def pop_downlinks(self, device_id: str) -> list[dict[str, Any]]:
        """Pop pending downlink commands for a device."""
        items = list(self.downlinks_by_device_id[device_id])
        self.downlinks_by_device_id[device_id].clear()
        return items

    def subscribe_downlinks(
        self,
        device_id: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> Callable[[], None]:
        """Subscribe to downlink commands for a connected Android client."""
        self.downlink_callbacks_by_device_id[device_id].append(callback)
        for payload in self.pop_downlinks(device_id):
            callback(payload)
        return lambda: self.unsubscribe_downlinks(device_id, callback)

    def unsubscribe_downlinks(
        self,
        device_id: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> None:
        """Remove a downlink subscription."""
        callbacks = self.downlink_callbacks_by_device_id.get(device_id)
        if callbacks is None:
            return
        if callback in callbacks:
            callbacks.remove(callback)
        if not callbacks:
            self.downlink_callbacks_by_device_id.pop(device_id, None)

    def start_session(self, session_id: str, device_id: str) -> None:
        """Record which Android device owns a session."""
        session_id = normalize_session_id(session_id)
        self.device_id_by_session[session_id] = device_id
        self.audio_queues_by_session[session_id] = asyncio.Queue()

    def finish_session(self, session_id: str) -> None:
        """Forget a completed or cancelled session."""
        session_id = normalize_session_id(session_id)
        self.device_id_by_session.pop(session_id, None)
        self.audio_queues_by_session.pop(session_id, None)

    def device_for_session(self, session_id: str) -> str | None:
        """Return the Android device id that owns a session."""
        return self.device_id_by_session.get(normalize_session_id(session_id))

    async def push_audio(self, session_id: str, pcm: bytes) -> bool:
        """Push a PCM chunk into a session's audio queue."""
        queue = self.audio_queues_by_session.get(normalize_session_id(session_id))
        if queue is None:
            return False
        await queue.put(pcm)
        return True

    async def finish_audio(self, session_id: str) -> bool:
        """Signal that a session's audio stream has ended."""
        queue = self.audio_queues_by_session.get(normalize_session_id(session_id))
        if queue is None:
            return False
        await queue.put(None)
        return True

    async def audio_stream(self, session_id: str):
        """Yield PCM chunks for a session until the stream ends."""
        queue = self.audio_queues_by_session[normalize_session_id(session_id)]
        while True:
            chunk = await queue.get()
            if chunk is None:
                return
            yield chunk
