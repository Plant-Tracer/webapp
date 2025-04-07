#!/usr/bin/env python36

"""This program implements an autoresponder. It's in the mailstats repository
because the responder does analysis of mail files."""

import sys
import smtplib
import logging
import imaplib
import os
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
