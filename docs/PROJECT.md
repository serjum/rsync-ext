# Project Documentation

## Overview

`rsync-ext` is a small GNOME-focused desktop utility made of two pieces:

- a Nautilus extension that adds a `Send to Server` submenu for local files and folders
- a GTK4/Libadwaita application for managing saved SSH destinations and running transfers

The current scope is local-to-remote transfers over SSH using `rsync`.

## Main Components

- [src/rsync_ext/app.py](/home/sergiu/projects/rsync-ext/src/rsync_ext/app.py:1)
  The GTK application, connection editor, send dialog, and transfer progress UI.
- [src/rsync_ext/transfer.py](/home/sergiu/projects/rsync-ext/src/rsync_ext/transfer.py:1)
  Transfer planning, SSH command assembly, command execution, error mapping, and retry logic.
- [src/rsync_ext/config.py](/home/sergiu/projects/rsync-ext/src/rsync_ext/config.py:1)
  JSON-backed connection metadata storage.
- [src/rsync_ext/secrets.py](/home/sergiu/projects/rsync-ext/src/rsync_ext/secrets.py:1)
  Password storage in GNOME Keyring through libsecret.
- [src/rsync_ext/cli.py](/home/sergiu/projects/rsync-ext/src/rsync_ext/cli.py:1)
  Local CLI entry points used by the app, scripts, and future integrations.
- [nautilus/rsync_send_extension.py](/home/sergiu/projects/rsync-ext/nautilus/rsync_send_extension.py:1)
  Nautilus menu integration.

## Runtime Data

- Connection metadata: `~/.config/rsync-ext/connections.json`
- Logs: `~/.cache/rsync-ext/app.log`
- Password secrets: GNOME Keyring schema `io.github.rsyncext`

Passwords are never written into `connections.json`.

## Install Modes

- Local install:
  `./scripts/install-local.sh`
  Installs a user-level launcher, Nautilus extension, and a dedicated venv under `~/.local/share/rsync-ext/venv`.
- Debian package:
  `./scripts/build-deb.sh`
  Produces `dist/rsync-ext_<version>_all.deb` for App Center / `apt`.

These install modes are separate. Re-running the local installer does not update an already installed `.deb`.

## Transfer Flow

1. The user selects one or more local files or folders.
2. The app validates that each selected path exists.
3. The destination connection is loaded from `connections.json`.
4. Password-based connections fetch the password from GNOME Keyring.
5. An SSH transport command is built for the selected auth mode.
6. An `rsync` command is built and executed.
7. If the destination filesystem rejects rsync temporary files with `mkstemp ... Operation not permitted`, the transfer is retried once with `--inplace`.

## Transfer Flags

The transfer layer builds commands in [src/rsync_ext/transfer.py](/home/sergiu/projects/rsync-ext/src/rsync_ext/transfer.py:48).

### Default rsync flags

Every transfer currently starts with:

```bash
rsync -az --info=progress2 --human-readable
```

Meaning:

- `-a`
  Archive mode. Preserves recursion, symlinks, timestamps, devices, special files, owner, group, and permissions unless those parts are explicitly disabled later.
- `-z`
  Compresses data in transit.
- `--info=progress2`
  Emits overall progress output suitable for the progress window.
- `--human-readable`
  Uses human-readable sizes in progress output.

### Default attribute behavior

By default, the app disables Unix ownership and permission preservation by appending:

```bash
--no-perms --no-owner --no-group
```

This is intentional because many consumer NAS boxes, removable media mounts, and non-native Linux filesystems reject owner/group/permission changes.

Current behavior:

- GUI default:
  `Disable Unix perms/owner/group` is enabled
- CLI default:
  Unix attributes are not preserved
- To preserve them in CLI:
  pass `--preserve-unix-attrs`

### Partial and in-place behavior

The app uses one of these two rsync modes:

- normal path:
  `--partial`
- retry path:
  `--inplace`

Normal transfers use `--partial` so interrupted copies can keep partial data without writing directly into the final file.

If rsync fails with:

```text
mkstemp ... Operation not permitted
```

and exits with code `23`, the app retries once with:

```bash
--inplace
```

This helps on filesystems that reject rsync's temporary dot-files, such as some mounted removable devices or special NAS shares.

Tradeoff:

- `--partial` is safer and more atomic
- `--inplace` is more compatible with restrictive destination filesystems

## SSH Transport Flags

Every transfer uses SSH through rsync's `-e` option and includes:

```bash
-p <port>
-o StrictHostKeyChecking=<value>
-o ConnectTimeout=15
```

Meaning:

- `-p <port>`
  Uses the configured SSH port from the saved connection.
- `StrictHostKeyChecking=yes`
  Default for transfer planning.
- `StrictHostKeyChecking=accept-new`
  Used for connection tests and for GUI-launched transfers so first-time hosts can be accepted automatically.
- `ConnectTimeout=15`
  Fails reasonably quickly on unreachable hosts.

### SSH key authentication flags

For `auth_type = ssh_key`, the app adds:

```bash
-o BatchMode=yes
-o PreferredAuthentications=publickey
-o PasswordAuthentication=no
-o KbdInteractiveAuthentication=no
-o IdentitiesOnly=yes
-i <private-key-path>
```

Purpose:

- disables password prompts
- forces public key auth only
- uses the exact configured private key

Important:

- the configured path must be the private key, not the `.pub` file
- if the key is passphrase-protected, it must already be unlocked in `ssh-agent` or GNOME Keyring

### Password authentication flags

For `auth_type = password`, the app adds:

```bash
-o PreferredAuthentications=password,keyboard-interactive
-o PubkeyAuthentication=no
-o KbdInteractiveAuthentication=yes
-o NumberOfPasswordPrompts=1
```

The password is provided through:

```bash
sshpass -e
```

with the password placed in the `SSHPASS` environment variable for the child process.

## CLI Commands

Main entry point:

```bash
rsync-ext <command>
```

Supported commands:

- `app`
  Opens the connections manager.
- `send --connection <id> [--dest-path <path>] <sources...>`
  Opens the send dialog.
- `transfer --connection <id> --dest-path <path> [--accept-new-hostkey] [--preserve-unix-attrs] <sources...>`
  Runs a transfer directly from the CLI.
- `test-connection --connection <id>`
  Tests a saved connection.
- `purge-user-data`
  Removes saved config, logs, and stored secrets for the current user.

## Error Handling

Transfer and test failures are mapped into user-facing messages in [src/rsync_ext/transfer.py](/home/sergiu/projects/rsync-ext/src/rsync_ext/transfer.py:156).

Handled cases include:

- missing commands
- authentication failure
- changed host keys
- missing local or remote paths
- DNS resolution failure
- connection timeout or refusal
- rsync process and transfer failures
- partial transfer with missing files or attributes

## Notes For Contributors

- Use `rg` for fast code search.
- Use `apply_patch` for manual file edits.
- Keep passwords in GNOME Keyring only.
- When changing transfer behavior, update this document and [README.md](/home/sergiu/projects/rsync-ext/README.md:1) together.
