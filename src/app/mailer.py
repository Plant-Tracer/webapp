#!/usr/bin/env python36

"""This program implements an autoresponder. It's in the mailstats repository
because the responder does analysis of mail files."""

import sys
import smtplib
import logging
import imaplib
import os
import json
import configparser
from email.parser import BytesParser
from email import policy

from jinja2.nativetypes import NativeEnvironment

from .auth import get_aws_secret_for_arn
from .paths import TEMPLATE_DIR
from .constants import C

logging.basicConfig(format=C.LOGGING_CONFIG, level=C.LOGGING_LEVEL)
logger = logging.getLogger(__name__)

# pylint: disable=invalid-name

SMTP_ATTRIBS = ['SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_PORT', 'SMTP_HOST']
SMTP_HOST = 'SMTP_HOST'
SMTP_USERNAME = 'SMTP_USERNAME'
SMTP_PASSWORD = 'SMTP_PASSWORD'
SMTP_PORT = 'SMTP_PORT'
SMTP_PORT_DEFAULT = 587
SMTP_NO_TLS = 'SMTP_NO_TLS'
SMTP_DEBUG = False

class InvalidEmail(RuntimeError):
    """Exception thrown in email is invalid"""

class InvalidMailerConfiguration(Exception):
    """Note that the mailer configuration is missing"""
    def __init__(self, msg):
        super().__init__()
        self.msg = msg
    def __repr__(self):
        return "InvalidMailerConfiguration: "+self.msg

class NoMailerConfiguration(Exception):
    """ No mailer configured"""

def get_smtp_config():
    """Get the smtp config from the [smtp] section of a credentials file.
    If the file specifies a AWS secret, get that.
    """
    logging.debug("get_smtp_config")
    if C.SMTPCONFIG_ARN in os.environ:
        return get_aws_secret_for_arn( os.environ[C.SMTPCONFIG_ARN] )

    if C.SMTPCONFIG_JSON in os.environ:
        cp = configparser.ConfigParser()
        cp.add_section('smtp')
        for (k,v) in json.loads(os.environ[C.SMTPCONFIG_JSON]).items():
            cp.set('smtp',k,v)
        return cp['smtp']

    cp = configparser.ConfigParser()
    if C.PLANTTRACER_CREDENTIALS not in os.environ:
        raise ValueError(f"{C.PLANTTRACER_CREDENTIALS} not set")
    cp.read(os.environ[C.PLANTTRACER_CREDENTIALS])
    ret = cp['smtp']
    for key in SMTP_ATTRIBS:
        assert key in ret
    return ret


def send_message(*,
                 from_addr: str,
                 to_addrs: [str],
                 msg: str,
                 dry_run: bool = False,
                 smtp_config: dict):
    # Validate types
    assert isinstance(from_addr, str)
    for to_addr in to_addrs:
        assert isinstance(to_addr, str)

    if dry_run:
        print(
            f"==== Will not send this message: ====\n{msg}\n====================\n", file=sys.stderr)
        return

    port = smtp_config.get(SMTP_PORT,  SMTP_PORT_DEFAULT)
    debug = SMTP_DEBUG or smtp_config.get('SMTP_DEBUG','')[0:1]=='Y'

    with smtplib.SMTP(smtp_config[SMTP_HOST], port) as smtp:
        logging.info("sending mail to %s with SMTP", ",".join(to_addrs))
        if debug:
            smtp.set_debuglevel(1)
        smtp.ehlo()
        if SMTP_NO_TLS not in smtp_config:
            smtp.starttls()
        smtp.ehlo()
        smtp.login(smtp_config[SMTP_USERNAME], smtp_config[SMTP_PASSWORD])
        smtp.sendmail(from_addr, to_addrs, msg.encode('utf8'))

def send_links(*, email, planttracer_endpoint, new_api_key, debug=False):
    """Creates a new api key and sends it to email. Won't resend if it has been sent in MIN_SEND_INTERVAL"""

    logging.warning("TK: Insert delay for MIN_SEND_INTERVAL")

    to_addrs = [email]
    with open(os.path.join(TEMPLATE_DIR, C.EMAIL_TEMPLATE_FNAME), "r") as f:
        msg_env = NativeEnvironment().from_string(f.read())

    logging.info("sending new link to %s",email)
    msg = msg_env.render(to_addrs=",".join([email]),
                         from_addr=C.PROJECT_EMAIL,
                         planttracer_endpoint=planttracer_endpoint,
                         api_key=new_api_key)

    dry_run = False
    try:
        smtp_config = get_smtp_config()
        smtp_config['SMTP_DEBUG'] = 'YES' if (SMTP_DEBUG or debug) else ''
    except KeyError as e:
        raise NoMailerConfiguration() from e
    try:
        send_message(from_addr=C.PROJECT_EMAIL,
                            to_addrs=to_addrs,
                            smtp_config=smtp_config,
                            dry_run=dry_run,
                            msg=msg)
    except smtplib.SMTPAuthenticationError as e:
        raise InvalidMailerConfiguration(str(dict(smtp_config))) from e
    return new_api_key

IMAP_HOST = 'IMAP_HOST'
IMAP_PORT = 'IMAP_PORT'
IMAP_USERNAME = 'IMAP_USERNAME'
IMAP_PASSWORD = 'IMAP_PASSWORD'
IMAP_NO_SSL = 'IMAP_NO_SSL'
DELETE = "<DELETE>"


def imap_inbox_scan(imap_config, callback):
    """Call callback on each message in the imap inbox. If callback returns DELETE, then delete the message.
    returns numbers of messages deleted.
    """
    deleted = 0
    if IMAP_NO_SSL in imap_config:
        m = imaplib.IMAP4(host=imap_config[IMAP_HOST], port=int(imap_config[IMAP_PORT]))
    else:
        m = imaplib.IMAP4_SSL(host=imap_config[IMAP_HOST], port=int(imap_config[IMAP_PORT]))
    m.login(imap_config[IMAP_USERNAME], imap_config[IMAP_PASSWORD])
    m.select()
    # pylint: disable=unused-variable
    typ, data = m.search(None, 'ALL')
    # pylint: enable=unused-variable
    for num in data[0].split():
        typ, d2 = m.fetch(num, '(RFC822)')
        for val in d2:
            if isinstance(val, tuple):
                # pylint: disable=unpacking-non-sequence
                (a, b) = val
                # pylint: enable=unpacking-non-sequence
                num = a.decode('utf-8').split()[0]
                msg = BytesParser(policy=policy.default).parsebytes(b)
                if callback(num, msg) is DELETE:
                    m.store(num, '+FLAGS', '\\Deleted')
                    deleted += 1
    try:
        m.expunge()
        m.close()
        m.logout()
    except imaplib.IMAP4. abort as e:
        print(e, file=sys.stderr)
    return deleted


def imap_config_from_environ():
    return {IMAP_HOST: os.environ[IMAP_HOST],
            IMAP_USERNAME: os.environ[IMAP_USERNAME],
            IMAP_PASSWORD: os.environ[IMAP_PASSWORD]
            }
