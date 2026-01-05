"""
Logging setup utilities.

Simplified version - only includes functionality actually used in this codebase.
"""

import logging
import functools

__author__ = "Simson L. Garfinkel"
__version__ = "0.0.1"

################################################################
# Support for ArgumentParser


def add_argument(parser, *, loglevel_default='INFO'):
    """Add the --loglevel argument to the ArgumentParser"""
    parser.add_argument("--loglevel", help="Set logging level",
                        choices=['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'], default=loglevel_default)
    parser.add_argument("--logfilename", help="output filename for logfile")


@functools.lru_cache(maxsize=1)
def setup(level='INFO'):
    """Set up logging. Checks to see if it was previously called and, if so, does a fast return.
    
    @param level - logging level (string or int)
    """
    # getLevelName sometimes returns a string and sometimes returns an int, and we want it always to be an integer
    loglevel = level if isinstance(level, int) else logging.getLevelName(level)

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
