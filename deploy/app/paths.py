"""
Should this be moved to constants?
"""

import os
from os.path import dirname, abspath, join
import shutil
import logging

from .constants import C

HOME = os.getenv('HOME')
if HOME is None:
    HOME = ''

logging.debug("__file__=%s",__file__)

APP_DIR         = dirname(abspath(__file__))
DEPLOY_DIR      = dirname(APP_DIR)
ROOT_DIR        = dirname(DEPLOY_DIR)

ETC_DIR         = join(DEPLOY_DIR, 'etc')
STATIC_DIR      = join(APP_DIR, 'static')
TEMPLATE_DIR    = join(APP_DIR, 'templates')
SCHEMA_FILE     = join(ETC_DIR, 'schema.sql')
SCHEMA_TEMPLATE = join(ETC_DIR, 'schema_{schema}.sql')

DEFAULT_CREDENTIALS_FILE = join(ETC_DIR, 'credentials.ini')
SCHEMA0_FILE     = SCHEMA_TEMPLATE.format(schema=0)
SCHEMA1_FILE     = SCHEMA_TEMPLATE.format(schema=1)

TEST_DIR        = join(ROOT_DIR, 'tests')
TEST_DATA_DIR   = join(ROOT_DIR, 'tests', 'data')

STANDALONE_PATH = join(ROOT_DIR, 'standalone.py')
TEST_MOVIE_FILENAME = join(TEST_DATA_DIR,'2019-07-31 plantmovie-rotated.mov')

AWS_LAMBDA_LINUX_STATIC_FFMPEG       = join(ETC_DIR, 'ffmpeg-6.1-amd64-static')

def ffmpeg_path():
    if C.FFMPEG_PATH in os.environ:
        pth = os.environ[C.FFMPEG_PATH]
        if os.path.exists(path):
            return pth
    pth = shutil.which('ffmpeg')
    if pth:
        return pth
    if os.path.exists(AWS_LAMBDA_LINUX_STATIC_FFMPEG):
        return AWS_LAMBDA_LINUX_STATIC_FFMPEG
    raise FileNotFoundError("ffmpeg")
