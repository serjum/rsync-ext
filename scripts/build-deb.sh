#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${DIST_DIR:-${ROOT_DIR}/dist}"
BUILD_ROOT="${BUILD_ROOT:-${DIST_DIR}/build-deb}"
PACKAGE_NAME="rsync-ext"

VERSION="$(
  python3 - <<'PY'
import tomllib
from pathlib import Path
data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
print(data["project"]["version"])
PY
)"

PACKAGE_DIR="${BUILD_ROOT}/${PACKAGE_NAME}_${VERSION}_all"
DEBIAN_DIR="${PACKAGE_DIR}/DEBIAN"
USR_BIN_DIR="${PACKAGE_DIR}/usr/bin"
APP_DIR="${PACKAGE_DIR}/usr/share/applications"
NAUTILUS_DIR="${PACKAGE_DIR}/usr/share/nautilus-python/extensions"
LIB_DIR="${PACKAGE_DIR}/usr/lib/rsync-ext"
SRC_DIR="${LIB_DIR}/src"

rm -rf "${PACKAGE_DIR}"
mkdir -p \
  "${DEBIAN_DIR}" \
  "${USR_BIN_DIR}" \
  "${APP_DIR}" \
  "${NAUTILUS_DIR}" \
  "${SRC_DIR}"

cp -R "${ROOT_DIR}/src/rsync_ext" "${SRC_DIR}/rsync_ext"
cp "${ROOT_DIR}/nautilus/rsync_send_extension.py" "${NAUTILUS_DIR}/rsync_send_extension.py"
cp "${ROOT_DIR}/data/io.github.rsyncext.desktop" "${APP_DIR}/io.github.rsyncext.desktop"

cat > "${USR_BIN_DIR}/rsync-ext" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="/usr/lib/rsync-ext/src\${PYTHONPATH:+:\${PYTHONPATH}}"
exec /usr/bin/python3 -m rsync_ext.cli "\$@"
EOF
chmod 0755 "${USR_BIN_DIR}/rsync-ext"

python3 - <<'PY' > "${DEBIAN_DIR}/control"
import tomllib
from pathlib import Path

data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
version = data["project"]["version"]
description = data["project"]["description"]
print(
    f"""Package: rsync-ext
Version: {version}
Section: utils
Priority: optional
Architecture: all
Maintainer: OpenAI Codex <support@openai.com>
Depends: python3, python3-gi, python3-nautilus, nautilus, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-secret-1, rsync, openssh-client, sshpass
Description: {description}
 Rsync Ext adds a GNOME Files context menu for sending local files
 to saved SSH destinations using rsync, plus a GTK settings app
 for managing saved connections.
"""
)
PY

cat > "${DEBIAN_DIR}/postinst" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
nautilus -q 2>/dev/null || true
update-desktop-database /usr/share/applications 2>/dev/null || true
exit 0
EOF
chmod 0755 "${DEBIAN_DIR}/postinst"

cat > "${DEBIAN_DIR}/postrm" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "purge" ]; then
  getent passwd | while IFS=: read -r user _ uid _ _ home shell; do
    if [ "${uid}" -lt 1000 ] || [ ! -d "${home}" ]; then
      continue
    fi

    rm -rf "${home}/.config/rsync-ext" "${home}/.cache/rsync-ext" 2>/dev/null || true

    runuser -u "${user}" -- env HOME="${home}" XDG_CONFIG_HOME="${home}/.config" XDG_CACHE_HOME="${home}/.cache" python3 - <<'PY' || true
try:
    import gi

    gi.require_version("Secret", "1")
    from gi.repository import Secret

    schema = Secret.Schema.new(
        "io.github.rsyncext",
        Secret.SchemaFlags.NONE,
        {"connection_id": Secret.SchemaAttributeType.STRING},
    )

    items = Secret.password_search_sync(schema, {}, Secret.SearchFlags.ALL, None)
    for item in items or []:
        attributes = item.get_attributes() or {}
        connection_id = attributes.get("connection_id")
        if connection_id:
            Secret.password_clear_sync(schema, {"connection_id": connection_id}, None)
except Exception:
    pass
PY
  done
fi

nautilus -q 2>/dev/null || true
update-desktop-database /usr/share/applications 2>/dev/null || true
exit 0
EOF
chmod 0755 "${DEBIAN_DIR}/postrm"

dpkg-deb --root-owner-group --build "${PACKAGE_DIR}" "${DIST_DIR}/${PACKAGE_NAME}_${VERSION}_all.deb"

echo "Built package:"
echo "${DIST_DIR}/${PACKAGE_NAME}_${VERSION}_all.deb"
