"""
utils/logger.py
───────────────
Logging terpusat dengan format yang seragam.
"""

import logging
import os
from config.settings import LOG_LEVEL, LOG_DIR

os.makedirs(LOG_DIR, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # sudah dikonfigurasi

    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler ke console
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Handler ke file
    fh = logging.FileHandler(os.path.join(LOG_DIR, "etl.log"))
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
