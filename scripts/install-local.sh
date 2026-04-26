#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
XDG_DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}"
SITE_BIN_DIR="${SITE_BIN_DIR:-${HOME}/.local/bin}"
INSTALL_ROOT="${INSTALL_ROOT:-${XDG_DATA_HOME}/rsync-ext}"
VENV_DIR="${VENV_DIR:-${INSTALL_ROOT}/venv}"
INSTALL_METADATA_DIR="${INSTALL_METADATA_DIR:-${XDG_CONFIG_HOME}/rsync-ext}"
INSTALL_METADATA_PATH="${INSTALL_METADATA_PATH:-${INSTALL_METADATA_DIR}/install.json}"
NAUTILUS_EXT_DIR="${NAUTILUS_EXT_DIR:-${XDG_DATA_HOME}/nautilus-python/extensions}"
APPS_DIR="${APPS_DIR:-${XDG_DATA_HOME}/applications}"
LAUNCHER_PATH="${LAUNCHER_PATH:-${SITE_BIN_DIR}/rsync-ext}"
DESKTOP_PATH="${DESKTOP_PATH:-${APPS_DIR}/io.github.rsyncext.desktop}"
NAUTILUS_EXT_PATH="${NAUTILUS_EXT_PATH:-${NAUTILUS_EXT_DIR}/rsync_send_extension.py}"
OLD_NAUTILUS_EXT_PATH="${OLD_NAUTILUS_EXT_PATH:-${NAUTILUS_EXT_DIR}/rsync_ext.py}"

mkdir -p \
  "${SITE_BIN_DIR}" \
  "${INSTALL_ROOT}" \
  "${INSTALL_METADATA_DIR}" \
  "${NAUTILUS_EXT_DIR}" \
  "${APPS_DIR}"

pkill -f 'rsync_ext\.cli' 2>/dev/null || true
pkill -f '/\.local/bin/rsync-ext' 2>/dev/null || true

if ! "${PYTHON_BIN}" -m venv --system-site-packages "${VENV_DIR}"; then
  echo "Failed to create a virtual environment at ${VENV_DIR}." >&2
  echo "Make sure the python venv module is installed, e.g. apt install python3-venv." >&2
  exit 1
fi

cat > "${LAUNCHER_PATH}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="${ROOT_DIR}/src\${PYTHONPATH:+:\${PYTHONPATH}}"
exec "${VENV_DIR}/bin/python" -m rsync_ext.cli "\$@"
EOF
chmod +x "${LAUNCHER_PATH}"

cat > "${INSTALL_METADATA_PATH}" <<EOF
{
  "source_root": "${ROOT_DIR}",
  "launcher": "${LAUNCHER_PATH}"
}
EOF

rm -f "${OLD_NAUTILUS_EXT_PATH}"
rm -f "${NAUTILUS_EXT_DIR}/__pycache__/rsync_ext."*
cp "${ROOT_DIR}/nautilus/rsync_send_extension.py" "${NAUTILUS_EXT_PATH}"

sed "s|^Exec=.*$|Exec=${LAUNCHER_PATH} app|" \
  "${ROOT_DIR}/data/io.github.rsyncext.desktop" > "${DESKTOP_PATH}"

echo "Installed rsync-ext locally."
echo "Virtual environment: ${VENV_DIR}"
echo "Launcher: ${LAUNCHER_PATH}"
nautilus -q 2>/dev/null || true
echo "Nautilus restart requested."
