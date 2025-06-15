"""Authentication Layer

This layer is necessarily customized to Flask.
This provides for all authentication in the planttracer system:
* Database authentication
* Mailer authentication
"""
import os
import os.path
import logging
import json

import boto3
from botocore.exceptions import ClientError

from .constants import C

logging.basicConfig(format=C.LOGGING_CONFIG, level=C.LOGGING_LEVEL)
logger = logging.getLogger(__name__)

AWS_SECRET_NAME = 'AWS_SECRET_NAME'
AWS_REGION_NAME = 'AWS_REGION_NAME'
SECRETSMANAGER = 'secretsmanager'


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



################################################################
## AWS Secrets Stuff

class SecretsManagerError(Exception):
    """ SecretsManagerError """

def get_aws_secret_for_arn(secret_name):
    region_name = secret_name.split(':')[3]
    logging.debug("secret_name=%s region_name=%s",secret_name, region_name)
    session = boto3.Session()
    client = session.client( service_name=SECRETSMANAGER,
                             region_name=region_name)
    try:
        get_secret_value_response = client.get_secret_value( SecretId=secret_name )
    except ClientError as e:
        logging.error('Cannot get secretId=%s',secret_name)
        raise SecretsManagerError(e) from e
    secret = json.loads(get_secret_value_response['SecretString'])
    return secret


def get_aws_secret_for_section(section):
    if AWS_SECRET_NAME in section:
        secret_name = os.path.expandvars(section[AWS_SECRET_NAME])
        return get_aws_secret_for_arn(secret_name)
    return None

################################################################
# Authentication configuration - for server
##
