import logging
import os

from settings import LOG_FILE


def get_logger(
    name: str,
    level: str = logging.INFO,
):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        )

        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(formatter)

        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        fh = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(formatter)
        logger.addHandler(ch)
        logger.addHandler(fh)

    return logger
