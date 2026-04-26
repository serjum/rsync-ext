from __future__ import annotations

import json
import uuid
from pathlib import Path

from rsync_ext.constants import CONFIG_DIR, CONFIG_PATH
from rsync_ext.models import Connection


class ConnectionStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CONFIG_PATH

    def load(self) -> list[Connection]:
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        raw_connections = payload.get("connections", [])
        connections = [Connection.from_dict(item) for item in raw_connections]
        connections.sort(key=lambda item: item.label.lower())
        return connections

    def save(self, connections: list[Connection]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "connections": [connection.to_dict() for connection in connections],
        }
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")

    def get(self, connection_id: str) -> Connection:
        for connection in self.load():
            if connection.id == connection_id:
                return connection
        raise KeyError(f"Unknown connection: {connection_id}")

    def upsert(self, connection: Connection) -> None:
        connection.validate()
        connections = self.load()
        for index, current in enumerate(connections):
            if current.id == connection.id:
                connections[index] = connection
                self.save(connections)
                return
        connections.append(connection)
        self.save(connections)

    def delete(self, connection_id: str) -> None:
        remaining = [item for item in self.load() if item.id != connection_id]
        self.save(remaining)


def new_connection_id() -> str:
    return uuid.uuid4().hex
