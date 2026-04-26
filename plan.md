# Rsync Files Extension for Ubuntu GNOME

## Summary
Build a GNOME Files (`Nautilus`) extension plus a small GTK/Libadwaita settings app that lets the user right-click local files/folders and send them to saved SSH destinations via `rsync`, in a GSConnect-like flow.

v1 behavior is intentionally scoped to **local-to-remote** transfers:
- User selects one or more local files/folders in Files.
- Context menu shows `Send to Server` with saved connections.
- Choosing a connection opens a confirmation dialog with that connection preselected and the destination path editable.
- Transfer runs via `rsync` over SSH and reports progress/success/failure in-app.

## Public Interfaces
- Config file: `~/.config/rsync-ext/connections.json`
  - Stores only non-secret connection metadata.
  - Connection shape includes: `id`, `label`, `host`, `port`, `username`, `auth_type` (`password` or `ssh_key`), optional `private_key_path`, `default_destination_path`, `enabled`.
- Secret storage: GNOME Keyring via libsecret
  - Password connections store the password by `connection_id`.
  - SSH key passphrases are **not** stored/managed by the app; key unlocking uses system `ssh-agent` / GNOME Keyring.
- Reusable local CLI/library contract
  - Thin shared core under `src/rsync_ext/` exposes command-building and transfer execution.
  - Add a local CLI entry such as `rsync-ext transfer --connection <id> --dest-path <path> <sources...>` so Nautilus is only a launcher and future file-manager frontends can reuse the same core.

## Implementation Changes
- Core transfer layer
  - Validate selected local paths and destination connection before launch.
  - Build `rsync` command with SSH transport, preserving recursive copy for folders and multi-select files.
  - Password auth uses `sshpass` with a keyring-fetched secret; SSH key auth uses `ssh -i <key>` and `IdentitiesOnly=yes`.
  - Add a `Test Connection` flow in settings that verifies auth and host reachability; use `StrictHostKeyChecking=accept-new` for first-time host trust, but fail on changed host keys.
  - Capture stdout/stderr and map common failures into user-readable errors: missing `rsync`, missing `sshpass`, auth failure, unknown path, host key mismatch, network failure.

- Nautilus extension
  - Implement a `MenuProvider` extension in `nautilus/rsync_send_extension.py`.
  - Show `Send to Server` only for local file selections, not trash/search/virtual items.
  - Submenu lists enabled saved connections plus `Manage Connections…`.
  - Clicking a connection opens the send dialog with selected sources, destination server, and editable destination path prefilled from that connection’s default path.

- Settings app
  - GTK4 + Libadwaita app for add/edit/delete/test connection.
  - Fields: label, host/IP, port, username, auth type, password or private key path, default destination path.
  - Persist metadata to `connections.json`; write/remove secrets via libsecret only.
  - Include dependency/status checks for `rsync`, `ssh`, and `sshpass` so password-based connections fail fast with a clear message.
  - After transfer start, show a progress window/dialog with live output summary and desktop notification on completion.

- Packaging/install shape
  - Structure the project so it can be installed per-user first: Nautilus extension into the user XDG data dir and the settings app as a normal desktop entry.
  - Keep the Python package layout compatible with later `.deb` packaging, but do not require a system package build in v1.

## Test Plan
- Unit tests
  - Config load/save round-trip without secrets.
  - Rsync/SSH command assembly for password auth and SSH key auth.
  - Destination path override vs saved default path.
  - Error mapping for missing binaries and common rsync exit cases.

- Integration/manual tests
  - Right-click single local file and send successfully to a password-based connection.
  - Right-click multiple files and a folder and send successfully to an SSH-key connection.
  - Edit destination path in the send dialog and confirm the override is used only for that run.
  - `Manage Connections…` opens from Nautilus and reflects add/edit/delete immediately after Nautilus restart.
  - Disabled connections do not appear in the submenu.
  - Unknown host first connect succeeds through `Test Connection`; changed host key is blocked with a clear error.
  - Password connection with missing `sshpass` shows actionable setup guidance instead of failing silently.

## Assumptions And Defaults
- v1 supports **local-to-remote** transfers only; true remote-to-remote copy is explicitly deferred.
- GNOME Files/Nautilus is the first supported file manager; the shared core is added now so other frontends can be attached later.
- Connection metadata lives in a user-editable JSON file; secrets never do.
- Passwords are stored in GNOME Keyring; SSH private key passphrases are handled by the system SSH agent, not the app.
- Default destination path is stored per connection and may be overridden per transfer.
- The extension targets Ubuntu GNOME 26.04 first, but avoids Ubuntu-specific APIs so it remains usable on nearby GNOME/Linux releases.
