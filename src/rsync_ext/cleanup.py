from __future__ import annotations

import shutil
from pathlib import Path

from rsync_ext.constants import CACHE_DIR, CONFIG_DIR
from rsync_ext.logging_utils import setup_logging
from rsync_ext.secrets import SecretStore

LOGGER = setup_logging()


def purge_user_data(
    *,
    config_dir: Path | None = None,
    cache_dir: Path | None = None,
    secret_store: SecretStore | None = None,
) -> None:
    store = secret_store or SecretStore()
    config_path = config_dir or CONFIG_DIR
    cache_path = cache_dir or CACHE_DIR

    LOGGER.info("Purging user data config_dir=%s cache_dir=%s", config_path, cache_path)

    try:
        store.clear_all_passwords()
        LOGGER.info("Cleared stored secrets")
    except Exception:
        LOGGER.exception("Failed to clear stored secrets during purge")

    for path in [config_path, cache_path]:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            LOGGER.info("Removed path %s", path)
