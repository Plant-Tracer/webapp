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

SRC_DIR          = dirname(abspath(__file__))
logging.debug("SRC_DIR=%s",SRC_DIR)

ROOT_DIR         = SRC_DIR

STATIC_DIR       = join(ROOT_DIR, 'static')
logging.debug("STATIC_DIR=%s",STATIC_DIR)

ETC_DIR          = join(ROOT_DIR, 'etc')
TEMPLATE_DIR     = join(ROOT_DIR, 'templates')
TEST_DIR         = join(ROOT_DIR, 'tests')
TEST_DATA_DIR    = join(ROOT_DIR, 'tests', 'data')
SCHEMA_FILE      = join(ROOT_DIR, 'etc', 'schema.sql')
SCHEMA_TEMPLATE  = join(ROOT_DIR, 'etc', 'schema_{schema}.sql')
SCHEMA0_FILE     = SCHEMA_TEMPLATE.format(schema=0)
SCHEMA1_FILE     = SCHEMA_TEMPLATE.format(schema=1)

AWS_LAMBDA_LINUX_STATIC_FFMPEG       = join(ETC_DIR, 'ffmpeg-6.1-amd64-static')

def running_in_aws_lambda():
    return C.AWS_LAMBDA_ENVIRON in os.environ

def ffmpeg_path():
    if running_in_aws_lambda():
        return AWS_LAMBDA_LINUX_STATIC_FFMPEG
    else:
        return shutil.which('ffmpeg')
