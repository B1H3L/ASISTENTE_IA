import logging
import os
from logging.handlers import RotatingFileHandler

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_FMT = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


def _make_logger(name: str, filename: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fh = RotatingFileHandler(
        os.path.join(_LOG_DIR, filename),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(_FMT)
    ch = logging.StreamHandler()
    ch.setFormatter(_FMT)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


security_log = _make_logger("security", "security.log")
app_log = _make_logger("app", "app.log")
