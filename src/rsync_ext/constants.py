from pathlib import Path

APP_ID = "io.github.rsyncext"
APP_NAME = "Rsync Ext"
CONFIG_DIR = Path.home() / ".config" / "rsync-ext"
CONFIG_PATH = CONFIG_DIR / "connections.json"
CACHE_DIR = Path.home() / ".cache" / "rsync-ext"
LOG_PATH = CACHE_DIR / "app.log"
SECRETS_SCHEMA_NAME = APP_ID
DEFAULT_SSH_PORT = 22
DEFAULT_DESTINATION_PATH = "~/"
