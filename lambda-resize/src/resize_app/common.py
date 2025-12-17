"""
Main entry point for AWS Lambda Dashboard

Generate the https://camera.planttracer.org/ home page.
Runs the camera.
"""

# at top of home_app/home.py (module import time)
from os.path import dirname
import functools
import logging
import os

MY_DIR = dirname(__file__)

__version__ = "0.1.0"

################################################################
### Logger
@functools.cache  # singleton
def _configure_root_once():
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # Configure a dedicated app logger; avoid touching the root logger.
    app_logger = logging.getLogger("resize")
    app_logger.setLevel(level)

    if not app_logger.handlers:
        handler = logging.StreamHandler()
        fmt = "%(asctime)s %(levelname)s [%(name)s %(filename)s:%(lineno)d %(funcName)s] %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        app_logger.addHandler(handler)

    # Prevent bubbling to root (stops double logs)
    app_logger.propagate = False

    # If this code is used as a library elsewhere, avoid “No handler” warnings:
    logging.getLogger(__name__).addHandler(logging.NullHandler())


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger under the 'resize' namespace (e.g., resize)."""
    _configure_root_once()
    return logging.getLogger("resize" + ("" if not name else f".{name}"))


LOGGER = get_logger("grader")
