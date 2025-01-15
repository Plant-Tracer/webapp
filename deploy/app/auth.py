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
from .paths import DEFAULT_CREDENTIALS_FILE

COOKIE_MAXAGE = 60*60*24*180
SMTP_ATTRIBS = ['SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_PORT', 'SMTP_HOST']

################################################################
# Authentication configuration - for server
##


def credentials_file():
    name = os.environ.get(C.PLANTTRACER_CREDENTIALS,DEFAULT_CREDENTIALS_FILE)
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
    if C.SMTPCONFIG_ARN in os.environ:
        return dbfile.get_aws_secret_for_arn( os.environ[C.SMTPCONFIG_ARN] )

    cp = config()
    ret = cp['smtp']
    for key in SMTP_ATTRIBS:
        assert key in ret
    return ret

@functools.cache
def get_dbreader():
    """Get the dbreader authentication info from:
    1 - the [dbreader] section of the file specified by the DBCREDENTIALS_PATH environment variable if it exists.
    2 - the [dbreader] section of the credentials file
    """
    if C.DBREADER_ARN in os.environ:
        return dbfile.DBMySQLAuth.FromSecret( os.environ[C.DBREADER_ARN] )
    return dbfile.DBMySQLAuth.FromConfigFile( credentials_file(), 'dbreader')


@functools.cache
def get_dbwriter():
    """Get the dbwriter authentication info from:
    1 - the [dbwriter] section of the file specified by the DBCREDENTIALS_PATH environment variable if it exists.
    2 - the [dbwriter] section of the credentials file
    """
    if C.DBWRITER_ARN in os.environ:
        return dbfile.DBMySQLAuth.FromSecret( os.environ[C.DBWRITER_ARN] )
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
