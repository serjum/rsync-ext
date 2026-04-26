from __future__ import annotations

import gi

gi.require_version("Secret", "1")
from gi.repository import Secret

from rsync_ext.constants import APP_NAME, SECRETS_SCHEMA_NAME


def _build_schema(name: str) -> Secret.Schema:
    return Secret.Schema.new(
        name,
        Secret.SchemaFlags.NONE,
        {
            "connection_id": Secret.SchemaAttributeType.STRING,
        },
    )


_SCHEMA = _build_schema(SECRETS_SCHEMA_NAME)


class SecretStore:
    def get_password(self, connection_id: str) -> str | None:
        return Secret.password_lookup_sync(
            _SCHEMA,
            {"connection_id": connection_id},
            None,
        )

    def set_password(self, connection_id: str, password: str) -> None:
        Secret.password_store_sync(
            _SCHEMA,
            {"connection_id": connection_id},
            Secret.COLLECTION_DEFAULT,
            f"{APP_NAME} {connection_id}",
            password,
            None,
        )

    def clear_password(self, connection_id: str) -> None:
        Secret.password_clear_sync(
            _SCHEMA,
            {"connection_id": connection_id},
            None,
        )

    def clear_all_passwords(self) -> None:
        items = Secret.password_search_sync(
            _SCHEMA,
            {},
            Secret.SearchFlags.ALL,
            None,
        )
        for item in items or []:
            attributes = item.get_attributes() or {}
            connection_id = attributes.get("connection_id")
            if connection_id:
                Secret.password_clear_sync(
                    _SCHEMA,
                    {"connection_id": connection_id},
                    None,
                )
