from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rsync_ext.cleanup import purge_user_data


class FakeSecretStore:
    def __init__(self) -> None:
        self.cleared = False

    def clear_all_passwords(self) -> None:
        self.cleared = True


class CleanupTests(unittest.TestCase):
    def test_purge_user_data_removes_config_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_dir = base / "config" / "rsync-ext"
            cache_dir = base / "cache" / "rsync-ext"
            config_dir.mkdir(parents=True)
            cache_dir.mkdir(parents=True)
            (config_dir / "connections.json").write_text("{}", encoding="utf-8")
            (cache_dir / "app.log").write_text("log", encoding="utf-8")

            secret_store = FakeSecretStore()
            purge_user_data(
                config_dir=config_dir,
                cache_dir=cache_dir,
                secret_store=secret_store,
            )

        self.assertTrue(secret_store.cleared)
        self.assertFalse(config_dir.exists())
        self.assertFalse(cache_dir.exists())


if __name__ == "__main__":
    unittest.main()
