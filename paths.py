"""
Single handy place for paths.
"""

import os
from os.path import dirname, abspath, relpath, join
import functools

import bottle
from bottle import jinja2_view

HOME = os.getenv('HOME')
if HOME is None:
    HOME = ''
STATIC_DIR   = join(dirname(abspath(__file__)), 'static')
TEMPLATE_DIR = join(dirname(abspath(__file__)), 'templates')
TEST_DIR = join(dirname(abspath(__file__)), 'tests')
TEST_DATA_DIR = join(dirname(abspath(__file__)), 'tests','data')

PLANTTRACER_ENDPOINT = os.environ['PLANTTRACER_ENDPOINT']


# Add the relative template path (since jinja2 doesn't like absolute paths)
bottle.TEMPLATE_PATH.append( relpath(TEMPLATE_DIR))

DBREADER_BASH_FILE = join( HOME, 'plant_dev.bash')
if not os.path.exists(DBREADER_BASH_FILE):
    DBREADER_BASH_FILE = join( HOME, 'plant_app.bash')

DBWRITER_BASH_FILE = join( HOME, 'plant_dev.bash')
if not os.path.exists(DBWRITER_BASH_FILE):
    DBWRITER_BASH_FILE = join( HOME, 'plant_app.bash')

# Create the @view decorator to add template to the function output
view = functools.partial(jinja2_view)
