"""
passenger_wsgi.py script to switch to python3 and use Bottle when running under passegers at Dreamhost.
Note: After March 31, 2024 Dreamhost no longer supports Passengers, so this script may not work anymore.

To reload:

$ touch tmp/restart.txt
(or)
$ make touch
"""

import sys
import os
import os.path
import logging

DESIRED_PYTHON = 'python3'
HOME = os.getenv('HOME')
DREAMHOST_PYTHON_BINDIR = os.path.join(HOME, 'opt/bin')
DUMP_VARS = False


def dump_vars(f):
    """Send the list of variables to output for debugging"""
    for (k, v) in os.environ.items():
        f.write(k + "=" + v + "\n")
        f.flush()


def redirect_stderr():
    """Make stderr go to a file"""
    # pylint: disable=unspecified-encoding
    with open(os.path.join(os.getenv('HOME'), 'error.log'), 'a') as errfile:
        os.close(sys.stderr.fileno())
        os.dup2(errfile.fileno(), sys.stderr.fileno())
        if DUMP_VARS:
            dump_vars(errfile)


def redirect_stdout():
    """Make stderr go to a file"""
    # pylint: disable=unspecified-encoding
    with open(os.path.join(os.getenv('HOME'), 'access.log.app'), 'a') as accfile:
        os.close(sys.stdout.fileno())
        os.dup2(accfile.fileno(), sys.stdout.fileno())


if 'IN_PASSENGER' in os.environ:
    # Send error to error.log, but not when running under pytest
    redirect_stderr()
    # redirect_stdout()

    # Use python of choice
    if DREAMHOST_PYTHON_BINDIR not in os.environ['PATH']:
        os.environ['PATH'] = DREAMHOST_PYTHON_BINDIR + ":" + os.environ['PATH']

    os.environ['PYTHONDONTWRITEBYTECODE'] = os.path.join(HOME, '.__pycache__')

    if DESIRED_PYTHON not in sys.executable:
        os.execlp(DESIRED_PYTHON, DESIRED_PYTHON, *sys.argv)
    else:
        # If we get here, we are running under the DESIRED_PYTHON
        # Set up logging for a bottle app
        # https://stackoverflow.com/questions/2557168/how-do-i-change-the-default-format-of-log-messages-in-python-app-engine
        # root.setLevel(logging.DEBUG)
        import bottle_app
        from ctools import clogging
        bottle_app.expand_memfile_max()
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        hdlr = root.handlers[0]
        fmt = logging.Formatter(clogging.LOG_FORMAT)
        hdlr.setFormatter(fmt)
        application = bottle_app.app
