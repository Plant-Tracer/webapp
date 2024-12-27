"""Authentication Layer

This layer is necessarily customized to Flask.
This provides for all authentication in the planttracer system:
* Database authentication
* Mailer authentication
"""
import os
import os.path
import configparser
import logging
import functools

from . import dbfile
from .constants import C

COOKIE_MAXAGE = 60*60*24*180
SMTP_ATTRIBS = ['SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_PORT', 'SMTP_HOST']

################################################################
# Authentication configuration - for server
##


def credentials_file():
    try:
        name = os.environ[ C.PLANTTRACER_CREDENTIALS ]
    except KeyError as e:
        raise RuntimeError(f"Environment variable {C.PLANTTRACER_CREDENTIALS} must be defined") from e
    if not os.path.exists(name):
        logging.error("Cannot find %s (PLANTTRACER_CREDENTIALS=%s)",os.path.abspath(name),name)
        raise FileNotFoundError(name)
    return name

def config():
    cp = configparser.ConfigParser()
    cp.read( credentials_file() )
    return cp

def smtp_config():
    """Get the smtp config from the [smtp] section of a credentials file.
    If the file specifies a AWS secret, get that.
    """
    cp = config()
    section = cp['smtp']
    if (secret := dbfile.get_aws_secret_for_section( section )) is not None:
        return secret

    for key in SMTP_ATTRIBS:
        assert key in cp['smtp']
    return section

@functools.cache
def get_dbreader():
    """Get the dbreader authentication info from:
    1 - the [dbreader] section of the file specified by the DBCREDENTIALS_PATH environment variable if it exists.
    2 - the [dbreader] section of the credentials file
    """
    return dbfile.DBMySQLAuth.FromConfigFile( credentials_file(), 'dbreader')


@functools.cache
def get_dbwriter():
    """Get the dbwriter authentication info from:
    1 - the [dbwriter] section of the file specified by the DBCREDENTIALS_PATH environment variable if it exists.
    2 - the [dbwriter] section of the credentials file
    """
    logging.debug("get_dbwriter. credentials_file=%s",credentials_file())
    return dbfile.DBMySQLAuth.FromConfigFile( credentials_file(), 'dbwriter')


class AuthError(Exception):
    """Integrated error handling,"""
    status_code = 403

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        rv['error'] = True
        return rv

class EmailNotInDatabase(Exception):
    """Handle error condition below"""
