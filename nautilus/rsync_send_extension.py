from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from gi.repository import GObject, Nautilus


def _install_metadata_path() -> Path:
    config_home = Path.home() / ".config"
    xdg_config_home = Path(os.environ.get("XDG_CONFIG_HOME", str(config_home)))
    return xdg_config_home / "rsync-ext" / "install.json"


def _bootstrap_source_path() -> dict:
    metadata_path = _install_metadata_path()
    packaged_src_path = Path("/usr/lib/rsync-ext/src")
    if packaged_src_path.exists():
        sys.path.insert(0, str(packaged_src_path))

    if not metadata_path.exists():
        return {}

    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    source_root = payload.get("source_root")
    if source_root:
        src_path = Path(source_root) / "src"
        if src_path.exists():
            sys.path.insert(0, str(src_path))

    return payload


INSTALL_METADATA = _bootstrap_source_path()

from rsync_ext.config import ConnectionStore
from rsync_ext.logging_utils import setup_logging

LOGGER = setup_logging()


class RsyncSendExtension(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self) -> None:
        super().__init__()
        self.store = ConnectionStore()
        LOGGER.info("Nautilus extension initialized")

    def get_file_items(self, files):  # type: ignore[override]
        LOGGER.info("Nautilus get_file_items count=%s", len(files))
        local_paths = self._local_paths(files)
        if not local_paths:
            LOGGER.info("No eligible local paths for menu")
            return []

        connections = [item for item in self.store.load() if item.enabled]
        top_item = Nautilus.MenuItem(
            name="RsyncSendExtension::SendToServer",
            label="Send to Server",
        )
        submenu = Nautilus.Menu()

        for connection in connections:
            item = Nautilus.MenuItem(
                name=f"RsyncSendExtension::{connection.id}",
                label=connection.label,
            )
            item.connect("activate", self._launch_send_dialog, connection.id, local_paths)
            submenu.append_item(item)

        if not connections:
            LOGGER.info("No enabled connections available for Nautilus menu")

        manage_item = Nautilus.MenuItem(
            name="RsyncSendExtension::ManageConnections",
            label="Manage Connections...",
        )
        manage_item.connect("activate", self._launch_manage)
        submenu.append_item(manage_item)
        top_item.set_submenu(submenu)
        return [top_item]

    def get_background_items(self, current_folder):  # type: ignore[override]
        return []

    def _local_paths(self, files) -> list[str]:
        paths: list[str] = []
        for item in files:
            if item.get_uri_scheme() != "file":
                return []
            location = item.get_location()
            if location is None:
                return []
            path = location.get_path()
            if not path or not Path(path).exists():
                return []
            paths.append(path)
        return paths

    def _launch_manage(self, _menu_item) -> None:
        LOGGER.info("Nautilus launch manage")
        subprocess.Popen(self._command_prefix() + ["app"], start_new_session=True)

    def _launch_send_dialog(self, _menu_item, connection_id: str, paths: list[str]) -> None:
        LOGGER.info("Nautilus launch send dialog connection_id=%s paths=%d", connection_id, len(paths))
        subprocess.Popen(
            self._command_prefix() + ["send", "--connection", connection_id, *paths],
            start_new_session=True,
        )

    def _command_prefix(self) -> list[str]:
        launcher = INSTALL_METADATA.get("launcher")
        if launcher and Path(launcher).exists():
            return [launcher]

        local_launcher = Path.home() / ".local" / "bin" / "rsync-ext"
        if local_launcher.exists():
            return [str(local_launcher)]

        binary = shutil.which("rsync-ext")
        if binary:
            return [binary]

        python = shutil.which("python3") or shutil.which("python")
        if python:
            return [python, "-m", "rsync_ext.cli"]

        return ["rsync-ext"]
