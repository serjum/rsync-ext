from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from rsync_ext.deps import ensure_binary
from rsync_ext.errors import TransferError, ValidationError
from rsync_ext.models import Connection
from rsync_ext.secrets import SecretStore


@dataclass(slots=True)
class TransferPlan:
    command: list[str]
    env: dict[str, str]
    remote_target: str


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def _validate_sources(sources: list[str]) -> list[Path]:
    if not sources:
        raise ValidationError("Select at least one local file or folder.")

    resolved: list[Path] = []
    for raw in sources:
        path = Path(raw).expanduser()
        if not path.exists():
            raise ValidationError(f"Local path does not exist: {path}")
        resolved.append(path.resolve())
    return resolved


def normalize_destination_path(dest_path: str) -> str:
    value = dest_path.strip()
    if not value:
        raise ValidationError("Destination path is required.")
    return value


def build_ssh_command(connection: Connection, *, accept_new_hostkey: bool) -> list[str]:
    ssh_path = ensure_binary("ssh", "SSH transport")
    command = [
        ssh_path,
        "-p",
        str(connection.port),
        "-o",
        f"StrictHostKeyChecking={'accept-new' if accept_new_hostkey else 'yes'}",
        "-o",
        "ConnectTimeout=15",
    ]

    if connection.auth_type == "ssh_key":
        command.extend(["-o", "BatchMode=yes"])
        command.extend(["-o", "PreferredAuthentications=publickey"])
        command.extend(["-o", "PasswordAuthentication=no"])
        command.extend(["-o", "KbdInteractiveAuthentication=no"])
        command.extend(["-o", "IdentitiesOnly=yes"])
        command.extend(["-i", str(Path(connection.private_key_path or "").expanduser())])
    else:
        command.extend(["-o", "PreferredAuthentications=password,keyboard-interactive"])
        command.extend(["-o", "PubkeyAuthentication=no"])
        command.extend(["-o", "KbdInteractiveAuthentication=yes"])
        command.extend(["-o", "NumberOfPasswordPrompts=1"])

    return command


def _apply_password_auth(
    connection: Connection,
    command: list[str],
    env: dict[str, str],
    *,
    secret_store: SecretStore | None,
    password_override: str | None = None,
    purpose: str,
) -> tuple[list[str], dict[str, str]]:
    if connection.auth_type != "password":
        return command, env

    sshpass_path = ensure_binary("sshpass", purpose)
    password = password_override
    if password is None:
        store = secret_store or SecretStore()
        password = store.get_password(connection.id)
    if not password:
        raise ValidationError(
            f"No password is stored in GNOME Keyring for '{connection.label}'."
        )
    env["SSHPASS"] = password
    return [sshpass_path, "-e"] + command, env


def build_transfer_plan(
    connection: Connection,
    sources: list[str],
    dest_path: str,
    *,
    accept_new_hostkey: bool = False,
    use_inplace: bool = False,
    preserve_unix_attrs: bool = False,
    secret_store: SecretStore | None = None,
) -> TransferPlan:
    connection.validate()
    resolved_sources = _validate_sources(sources)
    remote_path = normalize_destination_path(dest_path)

    rsync_path = ensure_binary("rsync", "file transfer")
    ssh_command = build_ssh_command(connection, accept_new_hostkey=accept_new_hostkey)
    command = [
        rsync_path,
        "-az",
        "--info=progress2",
        "--human-readable",
        "-e",
        " ".join(ssh_command),
    ]
    if use_inplace:
        command.append("--inplace")
    else:
        command.append("--partial")
    if not preserve_unix_attrs:
        command.extend(["--no-perms", "--no-owner", "--no-group"])
    command.extend(str(path) for path in resolved_sources)
    remote_target = f"{connection.username}@{connection.host}:{remote_path}"
    command.append(remote_target)

    env = os.environ.copy()

    command, env = _apply_password_auth(
        connection,
        command,
        env,
        secret_store=secret_store,
        purpose="password-based transfers",
    )

    return TransferPlan(
        command=command,
        env=env,
        remote_target=remote_target,
    )


def build_test_command(
    connection: Connection,
    *,
    accept_new_hostkey: bool = True,
    secret_store: SecretStore | None = None,
) -> tuple[list[str], dict[str, str]]:
    connection.validate()
    command = build_ssh_command(connection, accept_new_hostkey=accept_new_hostkey)
    command.append(f"{connection.username}@{connection.host}")
    command.append("printf ok")
    env = os.environ.copy()

    command, env = _apply_password_auth(
        connection,
        command,
        env,
        secret_store=secret_store,
        purpose="password-based connections",
    )

    return command, env


def build_browse_command(
    connection: Connection,
    dest_path: str,
    *,
    accept_new_hostkey: bool = True,
    secret_store: SecretStore | None = None,
    password_override: str | None = None,
) -> tuple[list[str], dict[str, str]]:
    connection.validate()
    remote_path = normalize_destination_path(dest_path)
    command = build_ssh_command(connection, accept_new_hostkey=accept_new_hostkey)
    command.append(f"{connection.username}@{connection.host}")
    command.append(_build_remote_browse_script(remote_path))
    env = os.environ.copy()
    command, env = _apply_password_auth(
        connection,
        command,
        env,
        secret_store=secret_store,
        password_override=password_override,
        purpose="password-based browsing",
    )
    return command, env


def browse_remote_directories(
    connection: Connection,
    dest_path: str,
    *,
    accept_new_hostkey: bool = True,
    secret_store: SecretStore | None = None,
    password_override: str | None = None,
) -> tuple[str, list[str]]:
    command, env = build_browse_command(
        connection,
        dest_path,
        accept_new_hostkey=accept_new_hostkey,
        secret_store=secret_store,
        password_override=password_override,
    )
    result = run_command(command, env)
    if result.returncode != 0:
        raise map_command_error(result)

    lines = result.stdout.splitlines()
    if not lines:
        raise TransferError(
            "The server did not return a directory listing.",
            details=result.stderr or result.stdout,
        )

    current_path = lines[0].strip()
    directories = [line.strip() for line in lines[1:] if line.strip()]
    return current_path, directories


def _build_remote_browse_script(dest_path: str) -> str:
    quoted_path = shlex.quote(dest_path)
    return (
        f"target={quoted_path}; "
        'case "$target" in '
        '"~") target="$HOME" ;; '
        '"~/"*) target="$HOME/${target#\\~/}" ;; '
        '"") target="$HOME" ;; '
        '/*) ;; '
        '*) target="$HOME/$target" ;; '
        "esac; "
        'probe="$target"; '
        'while [ ! -d "$probe" ] && [ "$probe" != "/" ] && [ "$probe" != "." ]; do '
        'case "$probe" in '
        '"") probe="." ;; '
        '/*) probe="${probe%/*}"; [ -n "$probe" ] || probe="/" ;; '
        '*/?*) probe="${probe%/*}" ;; '
        '*) probe="." ;; '
        "esac; "
        "done; "
        'if [ ! -d "$probe" ]; then probe="$HOME"; fi; '
        'target="$probe"; '
        'cd -- "$target" && '
        "pwd -P && "
        '{ for entry in ./* ./.??* ./.[!.]*; do '
        '[ -d "$entry" ] || continue; '
        'name="${entry#./}"; '
        'printf \'%s\\n\' "$name"; '
        'done; } | LC_ALL=C sort -u'
    )


def run_command(command: list[str], env: dict[str, str]) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise TransferError(f"Required command is missing: {exc.filename}") from exc

    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def test_connection(
    connection: Connection,
    *,
    accept_new_hostkey: bool = True,
    secret_store: SecretStore | None = None,
) -> CommandResult:
    command, env = build_test_command(
        connection,
        accept_new_hostkey=accept_new_hostkey,
        secret_store=secret_store,
    )
    result = run_command(command, env)
    if result.returncode != 0 or "ok" not in result.stdout:
        raise map_command_error(result)
    return result


def map_command_error(result: CommandResult) -> TransferError:
    details = (result.stderr or result.stdout).strip()
    message = "Transfer failed."

    if result.returncode == 127 or "not found" in details.lower():
        message = "A required command was not found."
    elif should_retry_with_inplace(result):
        message = (
            "The destination filesystem rejected rsync's temporary file creation. "
            "Retry with in-place writing or use a different destination path."
        )
    elif "permission denied" in details.lower():
        message = "Authentication failed. Check the stored password or SSH key."
    elif "host key verification failed" in details.lower():
        message = "The server host key changed. Review ~/.ssh/known_hosts before retrying."
    elif "no such file or directory" in details.lower():
        message = "The local or remote path does not exist."
    elif "could not resolve hostname" in details.lower() or "name or service not known" in details.lower():
        message = "The host name could not be resolved."
    elif "connection timed out" in details.lower() or "connection refused" in details.lower():
        message = "The server could not be reached."
    elif result.returncode == 5:
        message = "Rsync could not start because of an SSH or process error."
    elif result.returncode == 12:
        message = "Rsync failed during data transfer."
    elif result.returncode == 23:
        message = "Rsync completed with some files or attributes missing."
    elif result.returncode == 255:
        message = "SSH reported a connection or authentication failure."

    return TransferError(message, details=details)


def should_retry_with_inplace(result: CommandResult) -> bool:
    details = (result.stderr or result.stdout).lower()
    return (
        result.returncode == 23
        and "mkstemp" in details
        and "operation not permitted" in details
    )
