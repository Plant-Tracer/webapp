#
#
"""clogging.py - a collection of logging support methods for use at the US Census Bureau.

This module adds support for logging to syslog to the Python logging system.

All messages sent to the default logger will also go to syslog. We use
this in some production environments to aggregate log messages using
syslog and Splunk.

This code also sets up the Python logger so that it reports the
filename, line number, and function name associated with all log
messages. That's proven to be useful. You can change that by changing
the module variables after the module is imported.

To use this logging module, you must call clogging.setup().  The call
must be called in every Python process in which you want logging to go
to syslog. In an EMR system, this means that you need to call it at
least once in every mapper (because a new Python process may be
started up at any time by the Spark system). Calling clogging.setup()
is fast and idempotent---you can call it as often as you want. It
tracks to see if it has been previously called and immediately returns
if it has been.

This code has been tested on both Apple MAC OSX and on Amazon Linux.


Here is sample code for integrating this into Argparse:
    from argparse import ArgumentParser,ArgumentDefaultsHelpFormatter
    parser = ArgumentParser( formatter_class = ArgumentDefaultsHelpFormatter,
                             description="A demo")
    ... existing setup ...
    clogging.add_argument(parser)
    ...
    args = parser.parse_args()
    ...
    clogging.setup(args.loglevel,
                   syslog=True,
                   filename=args.logfilename,
                   log_format=clogging.LOG_FORMAT,
                   syslog_format=clogging.YEAR + " " + clogging.SYSLOG_FORMAT)

"""

import datetime
import logging
import logging.handlers
import os
import os.path
import socket
import functools

__author__ = "Simson L. Garfinkel"
__version__ = "0.0.1"

DEVLOG = "/dev/log"
DEVLOG_MAC = "/var/run/syslog"

# Default log formats.
#

# YEAR is used in callers
YEAR = str(datetime.datetime.now().year)
SYSLOG_FORMAT = "%(filename)s:%(lineno)d (%(funcName)s) %(message)s"
LOG_FORMAT = "%(asctime)s " + SYSLOG_FORMAT
MAX_LENGTH = 1000

# Global state variables. Keep track as to whether or not syslog
# handler was added and whether or not the basicConfig was setup.

################################################################
# Support for ArgumentParser


def add_argument(parser, *, loglevel_default='INFO'):
    """Add the --loglevel argument to the ArgumentParser"""
    parser.add_argument("--loglevel", help="Set logging level",
                        choices=['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'], default=loglevel_default)
    parser.add_argument( "--logfilename", help="output filename for logfile")


def syslog_default_address():
    if os.path.exists(DEVLOG):
        return DEVLOG
    if os.path.exists(DEVLOG_MAC):
        return DEVLOG_MAC
    raise RuntimeError(f"Neither {DEVLOG} nor {DEVLOG_MAC} are present.")


class MaxLengthFormatter(logging.Formatter):
    """Limit the length of a log message."""
    def __init__(self, fmt=None, datefmt=None, style='%', max_length=100):
        super().__init__(fmt, datefmt, style)
        self.max_length = max_length

    def format(self, record):
        original_message = record.getMessage()
        if len(original_message) > self.max_length:
            truncated_message = original_message[:self.max_length] + '...'
            record.msg = truncated_message
        return super().format(record)


@functools.lru_cache(maxsize=1)
def setup_syslog(facility=logging.handlers.SysLogHandler.LOG_LOCAL1,
                 syslog_address=None,
                 syslog_format=YEAR + " " + SYSLOG_FORMAT,
                 use_tcp=False,
                 max_length=MAX_LENGTH):
    # Make a second handler that logs to syslog
    if use_tcp:
        if syslog_address is None:
            syslog_address = ('localhost', 514)
        socktype = socket.SOCK_STREAM

        # From https://stackoverflow.com/questions/52950147/sysloghandler-messages-grouped-on-one-line-on-remote-server
        # This will add a line break to the message before it is 'emitted' which ensures that the messages are
        # split up over multiple lines, see https://bugs.python.org/issue28404
        syslog_format = f'{syslog_format}\n'
        # In order for the above to work, then we need to ensure that the null terminator is not included
        append_nul = False
    else:
        if syslog_address is None:
            syslog_address = syslog_default_address()
        socktype = socket.SOCK_DGRAM
        append_nul = True

    handler = logging.handlers.SysLogHandler(
        address=syslog_address, facility=facility, socktype=socktype)
    handler.append_nul = append_nul
    formatter = MaxLengthFormatter(fmt=syslog_format, max_length=max_length)
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)


# pylint: disable=too-many-arguments
# pylint: disable=unused-argument
# pylint: disable=too-many-positional-arguments
@functools.lru_cache(maxsize=1)
def setup(level='INFO',
          syslog=False,
          syslog_address=None,
          filename=None,
          facility=logging.handlers.SysLogHandler.LOG_LOCAL1,
          log_format=LOG_FORMAT,
          syslog_format=SYSLOG_FORMAT):
    """Set up logging as specified by ArgumentParse. Checks to see if it was previously called and, if so, does a fast return.
    @param syslog     - if True, also create the syslog handler.
    @param filename   - if provided, log to this file, too.
    @param facility   - use this facility, default LOG_LOCAL1
    @param log_format - log this log format for all but syslog
    @param syslog_format - use this for the syslog format.
    """
    # getLevelName sometimes returns a string and sometimes returns an int, and we want it always to be an integer
    loglevel = level if isinstance(
        level, int) else logging.getLevelName(level)

    # Check to see if the logger already has handlers.
    if logging.getLogger().hasHandlers():
        # The logger already has handlers, even though setup wasn't called yet
        # This will happen if a logging.info (or similar) call is made prior to calling this method
        current_level: int = logging.getLogger().getEffectiveLevel()

        # Check to see if the current effective level is lower than what was requested
        # If the current logging level is NOTSET (has not been set yet) OR
        # the requested level is lower, then set it to the requested level
        # See the logger levels here: https://docs.python.org/3/library/logging.html#levels
        if (current_level == logging.NOTSET) or (loglevel < current_level):
            logging.getLogger().setLevel(loglevel)

    if syslog:
        setup_syslog(facility=facility, syslog_address=syslog_address,
                     syslog_format=syslog_format)
