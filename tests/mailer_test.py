"""
Mailer tests are all done with the local mail server.

Originally we tested with a real mail server, but we couldn't reach it from Github actions.
TODO: Test with real mail server when running on Dreamhost?
"""


from jinja2.nativetypes import NativeEnvironment
import time
import sys
import os
import uuid
import logging
import pytest
import configparser
import threading

from os.path import abspath, dirname, join

from fixtures.localmail_config import mailer_config

sys.path.append(dirname(dirname(abspath(__file__))))

import db
import mailer
from mailer import InvalidEmail
from db import InvalidCourse_Key

MSG = """to: {{ to_addrs }}
from: {{ from_addr }}
subject: This is a test subject {{ guid }}

This is a test message.
"""

FAKE_USER_EMAIL = 'fake-user@planttracer.com'
FAKE_SENDER     = 'do-not-reply@planttracer.com'

def test_send_message(mailer_config):
    nonce = str(uuid.uuid4())

    TO_ADDRS = [FAKE_USER_EMAIL]
    msg_env = NativeEnvironment().from_string(MSG)
    msg = msg_env.render(to_addrs=",".join(TO_ADDRS),
                         from_addr=FAKE_USER_EMAIL,
                         guid=nonce)

    DRY_RUN = False
    smtp_config = mailer_config['smtp']
    mailer.send_message(from_addr=FAKE_SENDER,
                        to_addrs=TO_ADDRS,
                        smtp_config=smtp_config,
                        dry_run=DRY_RUN,
                        msg=msg)

    # Now let's see if the message got delivered evey 100 msec and then delete it
    # Wait for up to 5 seconds
    def cb(num, M):
        if nonce in M['subject']:
            return mailer.DELETE

    imap_config = mailer_config['imap']
    for i in range(50):
        deleted = mailer.imap_inbox_scan(imap_config, cb)
        if deleted > 0:
            break

        logging.warning("response %s not found. Sleep again count %d", nonce, i)
        time.sleep(0.1)
    if deleted == 0:
        raise RuntimeError("Could not delete test message")


def test_register_email():
    """Some tests of the email registration software in db"""
    with pytest.raises(InvalidEmail):
        db.register_email(email='invalid-email', name='valid-name')

    with pytest.raises(ValueError):
        db.register_email(email='user@company.com', name='valid-name', course_key=None, course_id=None)

    with pytest.raises(InvalidCourse_Key):
        db.register_email(email='user@company.com', name='valid-name', course_key='invalid-course-key', course_id=None)
