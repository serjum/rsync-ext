from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

from rsync_ext.constants import LOG_PATH


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("rsync_ext")
    if logger.handlers:
        return logger

    log_path = Path(LOG_PATH)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.FileHandler(log_path, encoding="utf-8")
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    def excepthook(exc_type, exc_value, exc_traceback) -> None:
        logger.exception(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = excepthook

    if hasattr(threading, "excepthook"):
        def thread_excepthook(args) -> None:
            logger.exception(
                "Unhandled thread exception",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )

        threading.excepthook = thread_excepthook

    logger.info("Logging initialized at %s", log_path)
    return logger
