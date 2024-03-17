"""
Single handy place for paths.
"""

import os
from os.path import dirname, abspath, relpath, join
import functools
import shutil

import bottle
from bottle import jinja2_view

HOME = os.getenv('HOME')
if HOME is None:
    HOME = ''

ROOT_DIR         = dirname(abspath(__file__))
STATIC_DIR       = join(ROOT_DIR, 'static')
ETC_DIR          = join(ROOT_DIR, 'etc')
TEMPLATE_DIR     = join(ROOT_DIR, 'templates')
TEST_DIR         = join(ROOT_DIR, 'tests')
TEST_DATA_DIR    = join(ROOT_DIR, 'tests', 'data')
SCHEMA_FILE      = join(ROOT_DIR, 'etc', 'schema.sql')
SCHEMA_TEMPLATE  = join(ROOT_DIR, 'etc', 'schema_{schema}.sql')
SCHEMA0_FILE     = SCHEMA_TEMPLATE.format(schema=0)
SCHEMA1_FILE     = SCHEMA_TEMPLATE.format(schema=1)
CREDENTIALS_FILE = join(ROOT_DIR, 'etc', 'credentials.ini')
AWS_CREDENTIALS_FILE = join(ROOT_DIR, 'etc', 'credentials-aws.ini')

LOCALMAIL_CONFIG_FNAME  = join( ROOT_DIR, 'tests', "localmail_config.ini")
PRODUCTION_CONFIG_FNAME = join( ROOT_DIR, 'etc', 'credentials.ini')
AWS_LAMBDA_LINUX_STATIC_FFMPEG       = join(ETC_DIR, 'ffmpeg-6.1-amd64-static')
AWS_LAMBDA_ENVIRON = 'AWS_LAMBDA'

# used by test program:
BOTTLE_APP_PATH = join(ROOT_DIR, 'bottle_app.py')

# Add the relative template path (since jinja2 doesn't like absolute paths)
bottle.TEMPLATE_PATH.append(relpath(TEMPLATE_DIR))

# Create the @view decorator to add template to the function output
view = functools.partial(jinja2_view)

def running_in_aws_lambda():
    return AWS_LAMBDA_ENVIRON in os.environ

def ffmpeg_path():
    if running_in_aws_lambda():
        return AWS_LAMBDA_LINUX_STATIC_FFMPEG
    else:
        return shutil.which('ffmpeg')
