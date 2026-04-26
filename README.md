# rsync-ext

`rsync-ext` is a small GTK application and Nautilus extension for sending
selected local files to saved SSH destinations through `rsync`.

## Features

- GNOME Files context menu for local files and folders
- Saved SSH destinations with passwords stored in GNOME Keyring
- Password or SSH key authentication
- Editable default destination path per connection
- Transfer progress window and desktop notifications

## Development

Run the settings app:

```bash
PYTHONPATH=src python3 -m rsync_ext.cli app
```

Open the send dialog:

```bash
PYTHONPATH=src python3 -m rsync_ext.cli send --connection demo /path/to/file
```

Run tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

## Logs

Application and Nautilus extension logs are written to:

```bash
~/.cache/rsync-ext/app.log
```

You can watch them live with:

```bash
tail -f ~/.cache/rsync-ext/app.log
```

## Local install

Use the helper script:

```bash
./scripts/install-local.sh
```

The installer creates a dedicated virtual environment under
`~/.local/share/rsync-ext/venv`, writes a launcher to `~/.local/bin/rsync-ext`,
and installs Nautilus metadata so this works on Ubuntu's externally managed
Python setup.

To remove the local install:

```bash
./scripts/uninstall-local.sh
```

To remove the local install and purge saved config, logs, and stored secrets:

```bash
./scripts/uninstall-local.sh --purge
```

## Debian Package

Build an installable `.deb` package with:

```bash
./scripts/build-deb.sh
```

That creates:

```bash
dist/rsync-ext_0.1.0_all.deb
```

You can open that `.deb` in Ubuntu App Center/App Manager to install or remove it
like a normal app package.

If you remove the package with purge semantics, the package will best-effort remove
per-user `~/.config/rsync-ext`, `~/.cache/rsync-ext`, and stored keyring items for
regular desktop users.
