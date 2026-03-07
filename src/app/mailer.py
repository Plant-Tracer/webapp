#!/usr/bin/env python36

"""Mailer: send email via SMTP (when credentials configured) or AWS SES.
SES is used when no SMTP credentials are present; region is taken from
AWS_REGION (single-region deployment)."""

import sys
import uuid
import smtplib
import imaplib
import os
import json
import configparser
from email.parser import BytesParser
from email import policy

import boto3
from botocore.exceptions import ClientError
from jinja2.nativetypes import NativeEnvironment

from .auth import get_aws_secret_for_arn
from .paths import TEMPLATE_DIR
from .constants import C, logger


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
    """No mailer configured (no SMTP credentials and SES not available)."""


def get_server_email():
    """Return the From address for outgoing mail (env SERVER_EMAIL or default)."""
    return os.environ.get(C.SERVER_EMAIL, 'admin@planttracer.com')


def get_smtp_config():
    """Get the SMTP config from credentials file, ARN, or JSON env.
    Returns None if no SMTP credentials are configured (caller may use SES).
    """
    logger.debug("get_smtp_config")
    if C.SMTPCONFIG_ARN in os.environ:
        return get_aws_secret_for_arn(os.environ[C.SMTPCONFIG_ARN])

    if C.SMTPCONFIG_JSON in os.environ:
        cp = configparser.ConfigParser()
        cp.add_section('smtp')
        for (k, v) in json.loads(os.environ[C.SMTPCONFIG_JSON]).items():
            cp.set('smtp', k, v)
        return cp['smtp']

    if C.PLANTTRACER_CREDENTIALS not in os.environ:
        return None
    cp = configparser.ConfigParser()
    cp.read(os.environ[C.PLANTTRACER_CREDENTIALS])
    if 'smtp' not in cp:
        return None
    ret = cp['smtp']
    for key in SMTP_ATTRIBS:
        if key not in ret:
            return None
    return ret


def _send_via_ses(*, from_addr: str, to_addrs: list, msg: str):
    """Send raw MIME message via AWS SES. Uses AWS_REGION (single-region)."""
    region = os.environ.get(C.AWS_REGION, 'us-east-1')
    client = boto3.client('ses', region_name=region)
    raw = msg.encode('utf-8')
    logger.info("sending mail to %s via SES (region=%s)", ",".join(to_addrs), region)
    client.send_raw_email(
        Source=from_addr,
        Destinations=to_addrs,
        RawMessage={'Data': raw},
    )


def send_message(*,
                 from_addr: str,
                 to_addrs: list,
                 msg: str,
                 dry_run: bool = False,
                 smtp_config: dict = None):
    """Send an email. Uses SMTP if smtp_config is provided, otherwise SES."""
    assert isinstance(from_addr, str)
    for to_addr in to_addrs:
        assert isinstance(to_addr, str)

    if dry_run:
        print(
            f"==== Will not send this message: ====\n{msg}\n====================\n",
            file=sys.stderr)
        return

    if smtp_config:
        port = smtp_config.get(SMTP_PORT, SMTP_PORT_DEFAULT)
        debug = SMTP_DEBUG or smtp_config.get('SMTP_DEBUG', '')[0:1] == 'Y'
        with smtplib.SMTP(smtp_config[SMTP_HOST], port) as smtp:
            logger.info("sending mail to %s with SMTP", ",".join(to_addrs))
            if debug:
                smtp.set_debuglevel(1)
            smtp.ehlo()
            if SMTP_NO_TLS not in smtp_config:
                smtp.starttls()
            smtp.ehlo()
            smtp.login(smtp_config[SMTP_USERNAME], smtp_config[SMTP_PASSWORD])
            smtp.sendmail(from_addr, to_addrs, msg.encode('utf-8'))
    else:
        try:
            _send_via_ses(from_addr=from_addr, to_addrs=to_addrs, msg=msg)
        except ClientError as e:
            raise InvalidMailerConfiguration(str(e)) from e


def _render_mime_template(template_name: str, **kwargs):
    """Render a MIME template (Jinja2) with a unique boundary."""
    path = os.path.join(TEMPLATE_DIR, template_name)
    with open(path, 'r', encoding='utf-8') as f:
        env = NativeEnvironment().from_string(f.read())
    kwargs.setdefault('boundary', 'bound_' + uuid.uuid4().hex)
    return env.render(**kwargs)


def send_links(*, email, planttracer_endpoint, new_api_key, debug=False):
    """Send login/magic-link email. Uses SMTP if configured, else SES."""

    logger.warning("TK: Insert delay for MIN_SEND_INTERVAL")

    to_addrs = [email]
    from_addr = get_server_email()
    msg = _render_mime_template(
        C.LOGIN_EMAIL_TEMPLATE_FNAME,
        to_addrs=",".join([email]),
        from_addr=from_addr,
        planttracer_endpoint=planttracer_endpoint,
        api_key=new_api_key,
    )

    smtp_config = get_smtp_config()
    if smtp_config:
        smtp_config['SMTP_DEBUG'] = 'YES' if (SMTP_DEBUG or debug) else ''
    dry_run = False
    try:
        send_message(
            from_addr=from_addr,
            to_addrs=to_addrs,
            smtp_config=smtp_config,
            dry_run=dry_run,
            msg=msg,
        )
    except smtplib.SMTPAuthenticationError as e:
        raise InvalidMailerConfiguration(str(dict(smtp_config))) from e
    return new_api_key


def send_course_created_email(*,
                              to_addr: str,
                              course_name: str,
                              course_id: str,
                              planttracer_endpoint: str,
                              api_key: str,
                              from_addr: str = None):
    """Send course-created verification email with magic link. Uses SMTP or SES."""
    if from_addr is None:
        from_addr = get_server_email()
    msg = _render_mime_template(
        C.COURSE_CREATED_EMAIL_TEMPLATE_FNAME,
        to_addrs=to_addr,
        from_addr=from_addr,
        course_name=course_name,
        course_id=course_id,
        planttracer_endpoint=planttracer_endpoint,
        api_key=api_key,
    )
    smtp_config = get_smtp_config()
    send_message(
        from_addr=from_addr,
        to_addrs=[to_addr],
        smtp_config=smtp_config,
        dry_run=False,
        msg=msg,
    )

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
