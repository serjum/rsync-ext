from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rsync_ext.errors import TransferError, ValidationError
from rsync_ext.models import Connection
from rsync_ext.transfer import (
    CommandResult,
    build_test_command,
    build_transfer_plan,
    map_command_error,
    should_retry_with_inplace,
)


class FakeSecretStore:
    def __init__(self, password: str | None = "secret") -> None:
        self.password = password

    def get_password(self, _connection_id: str) -> str | None:
        return self.password


class TransferTests(unittest.TestCase):
    def test_password_transfer_command_uses_sshpass_and_dest_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "demo.txt"
            source.write_text("hello", encoding="utf-8")
            connection = Connection(
                id="demo",
                label="Demo",
                host="example.com",
                username="sergiu",
                auth_type="password",
                default_destination_path="/srv/default",
            )

            plan = build_transfer_plan(
                connection,
                [str(source)],
                "/srv/override",
                accept_new_hostkey=True,
                secret_store=FakeSecretStore(),
            )

        self.assertEqual(Path(plan.command[0]).name, "sshpass")
        self.assertIn("SSHPASS", plan.env)
        self.assertEqual(plan.remote_target, "sergiu@example.com:/srv/override")
        self.assertIn("StrictHostKeyChecking=accept-new", " ".join(plan.command))
        self.assertIn("--no-perms", plan.command)
        self.assertIn("--no-owner", plan.command)
        self.assertIn("--no-group", plan.command)

    def test_ssh_key_transfer_command_uses_identity_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "demo.txt"
            key = Path(tmpdir) / "id_ed25519"
            source.write_text("hello", encoding="utf-8")
            key.write_text("key", encoding="utf-8")
            connection = Connection(
                id="demo",
                label="Demo",
                host="example.com",
                username="sergiu",
                auth_type="ssh_key",
                private_key_path=str(key),
                default_destination_path="/srv/default",
            )

            plan = build_transfer_plan(
                connection,
                [str(source)],
                connection.default_destination_path,
            )

        joined = " ".join(plan.command)
        self.assertIn("-i", joined)
        self.assertIn(str(key), joined)
        self.assertIn("BatchMode=yes", joined)
        self.assertIn("PreferredAuthentications=publickey", joined)
        self.assertIn("PasswordAuthentication=no", joined)
        self.assertEqual(plan.remote_target, "sergiu@example.com:/srv/default")

    def test_password_transfer_command_allows_keyboard_interactive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "demo.txt"
            source.write_text("hello", encoding="utf-8")
            connection = Connection(
                id="demo",
                label="Demo",
                host="example.com",
                username="sergiu",
                auth_type="password",
                default_destination_path="/srv/default",
            )

            plan = build_transfer_plan(
                connection,
                [str(source)],
                connection.default_destination_path,
                secret_store=FakeSecretStore(),
            )

        joined = " ".join(plan.command)
        self.assertIn("PreferredAuthentications=password,keyboard-interactive", joined)
        self.assertIn("KbdInteractiveAuthentication=yes", joined)
        self.assertIn("NumberOfPasswordPrompts=1", joined)

    def test_preserve_unix_attrs_omits_no_preserve_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "demo.txt"
            source.write_text("hello", encoding="utf-8")
            connection = Connection(
                id="demo",
                label="Demo",
                host="example.com",
                username="sergiu",
                auth_type="password",
                default_destination_path="/srv/default",
            )

            plan = build_transfer_plan(
                connection,
                [str(source)],
                connection.default_destination_path,
                preserve_unix_attrs=True,
                secret_store=FakeSecretStore(),
            )

        self.assertNotIn("--no-perms", plan.command)
        self.assertNotIn("--no-owner", plan.command)
        self.assertNotIn("--no-group", plan.command)

    def test_inplace_transfer_plan_uses_inplace_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "demo.txt"
            source.write_text("hello", encoding="utf-8")
            connection = Connection(
                id="demo",
                label="Demo",
                host="example.com",
                username="sergiu",
                auth_type="password",
                default_destination_path="/srv/default",
            )

            plan = build_transfer_plan(
                connection,
                [str(source)],
                connection.default_destination_path,
                use_inplace=True,
                secret_store=FakeSecretStore(),
            )

        self.assertIn("--inplace", plan.command)
        self.assertNotIn("--partial", plan.command)

    def test_password_test_command_requires_secret(self) -> None:
        connection = Connection(
            id="demo",
            label="Demo",
            host="example.com",
            username="sergiu",
            auth_type="password",
            default_destination_path="/srv/default",
        )

        with self.assertRaises(ValidationError):
            build_test_command(connection, secret_store=FakeSecretStore(password=None))

    def test_map_command_error_recognizes_host_key_mismatch(self) -> None:
        error = map_command_error(
            CommandResult(
                returncode=255,
                stdout="",
                stderr="@@@@@@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! host key verification failed",
            )
        )

        self.assertIsInstance(error, TransferError)
        self.assertIn("host key changed", str(error).lower())

    def test_should_retry_with_inplace_for_mkstemp_not_permitted(self) -> None:
        result = CommandResult(
            returncode=23,
            stdout="",
            stderr='rsync: [receiver] mkstemp "/media/ssd/video/.movie.mkv.XYZ" failed: Operation not permitted (1)',
        )

        self.assertTrue(should_retry_with_inplace(result))


if __name__ == "__main__":
    unittest.main()
