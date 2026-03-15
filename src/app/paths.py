"""
Should this be moved to constants?
"""

import os
import platform
import shutil
from os.path import dirname, abspath, join

from .constants import C

HOME = os.getenv('HOME')
if HOME is None:
    HOME = ''

APP_DIR         = dirname(abspath(__file__))
DEPLOY_DIR      = dirname(APP_DIR)
ROOT_DIR        = dirname(DEPLOY_DIR)

ETC_DIR         = join(DEPLOY_DIR, 'etc')
STATIC_DIR      = join(APP_DIR, 'static')
TEMPLATE_DIR    = join(APP_DIR, 'templates')

TEST_DIR        = join(ROOT_DIR, 'tests')
TEST_DATA_DIR   = join(ROOT_DIR, 'tests', 'data')

STANDALONE_PATH = join(ROOT_DIR, 'standalone.py')
TEST_MOVIE_FILENAME = join(TEST_DATA_DIR,'2019-07-31 plantmovie-rotated.mov')

# LEGACY: Static ffmpeg binaries. Production uses cv2+Pillow only; ffmpeg is only for legacy
# tracker helpers (cleanup_mp4, rotate_movie, render_tracked_movie). Use the one matching host arch.
AWS_LAMBDA_LINUX_STATIC_FFMPEG_AMD64 = join(ETC_DIR, 'ffmpeg-6.1-amd64-static')
AWS_LAMBDA_LINUX_STATIC_FFMPEG_ARM64 = join(ETC_DIR, 'ffmpeg-6.1-arm64-static')

# System paths to try when PATH is minimal (e.g. systemd only has venv/bin).
_SYSTEM_FFMPEG_CANDIDATES = ('/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg')


def _static_ffmpeg_for_machine():
    """Path to static ffmpeg for current machine, or None if not present."""
    machine = platform.machine().lower()
    if machine in ('x86_64', 'amd64'):
        path = AWS_LAMBDA_LINUX_STATIC_FFMPEG_AMD64
    elif machine in ('aarch64', 'arm64'):
        path = AWS_LAMBDA_LINUX_STATIC_FFMPEG_ARM64
    else:
        return None
    return path if os.path.exists(path) else None


def ffmpeg_path():
    """LEGACY: Path to ffmpeg binary. Raises if not found. Production paths use cv2 only."""
    if C.FFMPEG_PATH in os.environ:
        pth = os.environ[C.FFMPEG_PATH]
        if os.path.exists(pth):
            return pth
    pth = shutil.which('ffmpeg')
    if pth:
        return pth
    for pth in _SYSTEM_FFMPEG_CANDIDATES:
        if os.path.exists(pth):
            return pth
    pth = _static_ffmpeg_for_machine()
    if pth:
        return pth
    raise FileNotFoundError("ffmpeg")
