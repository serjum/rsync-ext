#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
XDG_DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}"
SITE_BIN_DIR="${SITE_BIN_DIR:-${HOME}/.local/bin}"
INSTALL_ROOT="${INSTALL_ROOT:-${XDG_DATA_HOME}/rsync-ext}"
INSTALL_METADATA_DIR="${INSTALL_METADATA_DIR:-${XDG_CONFIG_HOME}/rsync-ext}"
INSTALL_METADATA_PATH="${INSTALL_METADATA_PATH:-${INSTALL_METADATA_DIR}/install.json}"
NAUTILUS_EXT_DIR="${NAUTILUS_EXT_DIR:-${XDG_DATA_HOME}/nautilus-python/extensions}"
APPS_DIR="${APPS_DIR:-${XDG_DATA_HOME}/applications}"
LAUNCHER_PATH="${LAUNCHER_PATH:-${SITE_BIN_DIR}/rsync-ext}"
DESKTOP_PATH="${DESKTOP_PATH:-${APPS_DIR}/io.github.rsyncext.desktop}"
NAUTILUS_EXT_PATH="${NAUTILUS_EXT_PATH:-${NAUTILUS_EXT_DIR}/rsync_send_extension.py}"
OLD_NAUTILUS_EXT_PATH="${OLD_NAUTILUS_EXT_PATH:-${NAUTILUS_EXT_DIR}/rsync_ext.py}"
PURGE_USER_DATA=0

if [ "${1:-}" = "--purge" ]; then
  PURGE_USER_DATA=1
fi

pkill -f 'rsync_ext\.cli' 2>/dev/null || true
pkill -f '/\.local/bin/rsync-ext' 2>/dev/null || true

if [ "${PURGE_USER_DATA}" -eq 1 ]; then
  PYTHONPATH="${ROOT_DIR}/src" python3 -m rsync_ext.cli purge-user-data || true
fi

rm -f "${LAUNCHER_PATH}"
rm -f "${DESKTOP_PATH}"
rm -f "${NAUTILUS_EXT_PATH}"
rm -f "${OLD_NAUTILUS_EXT_PATH}"
rm -f "${INSTALL_METADATA_PATH}"
rm -f "${NAUTILUS_EXT_DIR}/__pycache__/rsync_ext."*
rm -f "${NAUTILUS_EXT_DIR}/__pycache__/rsync_send_extension."*

if [ -d "${INSTALL_ROOT}" ]; then
  rm -rf "${INSTALL_ROOT}"
fi

rmdir "${INSTALL_METADATA_DIR}" 2>/dev/null || true

nautilus -q 2>/dev/null || true

echo "Uninstalled rsync-ext local integration."
echo "Nautilus restart requested."
