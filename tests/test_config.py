from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rsync_ext.config import ConnectionStore
from rsync_ext.models import Connection


class ConnectionStoreTests(unittest.TestCase):
    def test_round_trip_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "connections.json"
            store = ConnectionStore(path)
            connection = Connection(
                id="demo",
                label="Demo",
                host="example.com",
                port=2222,
                username="sergiu",
                auth_type="password",
                default_destination_path="/srv/dropbox",
                enabled=True,
            )
            store.save([connection])

            loaded = store.load()

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "demo")
        self.assertNotIn("password", loaded[0].to_dict())

    def test_upsert_replaces_existing_connection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "connections.json"
            store = ConnectionStore(path)
            original = Connection(
                id="demo",
                label="One",
                host="one.example",
                username="u",
                default_destination_path="~/",
            )
            updated = Connection(
                id="demo",
                label="Two",
                host="two.example",
                username="u",
                default_destination_path="/tmp",
            )

            store.upsert(original)
            store.upsert(updated)

            loaded = store.load()

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].label, "Two")

    def test_ssh_key_validation_rejects_public_key_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            key = Path(tmpdir) / "id_ed25519.pub"
            key.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest user@test\n", encoding="utf-8")
            connection = Connection(
                id="demo",
                label="Demo",
                host="example.com",
                username="u",
                auth_type="ssh_key",
                private_key_path=str(key),
                default_destination_path="~/",
            )

            with self.assertRaisesRegex(ValueError, "public key"):
                connection.validate()


if __name__ == "__main__":
    unittest.main()
