#!/usr/bin/env python36

"""This program implements an autoresponder. It's in the mailstats repository
because the responder does analysis of mail files."""

import sys
import smtplib
import logging
import imaplib
import os

from .paths import TEMPLATE_DIR
from constants import C
from email.parser import BytesParser
from email import policy

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
    PROJECT_EMAIL = 'admin@planttracer.com'

    logging.warning("TK: Insert delay for MIN_SEND_INTERVAL")

    TO_ADDRS = [email]
    with open(os.path.join(TEMPLATE_DIR, C.EMAIL_TEMPLATE_FNAME), "r") as f:
        msg_env = NativeEnvironment().from_string(f.read())

    logging.info("sending new link to %s",email)
    msg = msg_env.render(to_addrs=",".join([email]),
                         from_addr=PROJECT_EMAIL,
                         planttracer_endpoint=planttracer_endpoint,
                         api_key=new_api_key)

    DRY_RUN = False
    SMTP_DEBUG = 'YES' if debug else ''
    try:
        smtp_config = auth.smtp_config()
        smtp_config['SMTP_DEBUG'] = SMTP_DEBUG
    except KeyError as e:
        raise mailer.NoMailerConfiguration() from e
    try:
        mailer.send_message(from_addr=PROJECT_EMAIL,
                            to_addrs=TO_ADDRS,
                            smtp_config=smtp_config,
                            dry_run=DRY_RUN,
                            msg=msg)
    except smtplib.SMTPAuthenticationError as e:
        raise mailer.InvalidMailerConfiguration(str(dict(smtp_config))) from e
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
        M = imaplib.IMAP4(host=imap_config[IMAP_HOST], port=int(imap_config[IMAP_PORT]))
    else:
        M = imaplib.IMAP4_SSL(host=imap_config[IMAP_HOST], port=int(imap_config[IMAP_PORT]))
    M.login(imap_config[IMAP_USERNAME], imap_config[IMAP_PASSWORD])
    M.select()
    # pylint: disable=unused-variable
    typ, data = M.search(None, 'ALL')
    # pylint: enable=unused-variable
    for num in data[0].split():
        typ, d2 = M.fetch(num, '(RFC822)')
        for val in d2:
            if isinstance(val, tuple):
                # pylint: disable=unpacking-non-sequence
                (a, b) = val
                # pylint: enable=unpacking-non-sequence
                num = a.decode('utf-8').split()[0]
                msg = BytesParser(policy=policy.default).parsebytes(b)
                if callback(num, msg) is DELETE:
                    M.store(num, '+FLAGS', '\\Deleted')
                    deleted += 1
    try:
        M.expunge()
        M.close()
        M.logout()
    except imaplib.IMAP4. abort as e:
        print(e, file=sys.stderr)
    return deleted


def imap_config_from_environ():
    return {IMAP_HOST: os.environ[IMAP_HOST],
            IMAP_USERNAME: os.environ[IMAP_USERNAME],
            IMAP_PASSWORD: os.environ[IMAP_PASSWORD]
            }
