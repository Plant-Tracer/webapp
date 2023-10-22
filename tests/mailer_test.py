"""
Tests that require a working mail server.
Local mail server provided with a localmail server, which we create in the fixture.

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

from fixtures.localmail_config import localmail_config

sys.path.append(dirname(dirname(abspath(__file__))))

import mailer

MSG = """to: {{ to_addrs }}
from: {{ from_addr }}
subject: This is a test subject {{ guid }}

This is a test message.
"""

guid = str(uuid.uuid4())


def test_send_message(localmail_config):
    TEST_USER_EMAIL    = os.environ['TEST_USER_EMAIL']
    DO_NOT_REPLY_EMAIL = 'do-not-reply@planttracer.com'

    TO_ADDRS = [TEST_USER_EMAIL]
    msg_env = NativeEnvironment().from_string(MSG)
    msg = msg_env.render(to_addrs=",".join(TO_ADDRS),
                         from_addr=TEST_USER_EMAIL,
                         guid=guid)

    DRY_RUN = False
    smtp_config = localmail_config['smtp']
    mailer.send_message(from_addr=DO_NOT_REPLY_EMAIL,
                        to_addrs=TO_ADDRS,
                        smtp_config=smtp_config,
                        dry_run=DRY_RUN,
                        msg=msg
                        )

    # Now let's see if the message got delivered evey 100 msec and then delete it
    # Wait for up to 5 seconds
    def cb(num, M):
        if guid in M['subject']:
            return mailer.DELETE

    imap_config = localmail_config['imap']
    for i in range(50):
        deleted = mailer.imap_inbox_scan(imap_config, cb)
        if deleted > 0:
            break

        logging.warning("response %s not found. Sleep again count %d", guid, i)
        time.sleep(0.1)
    if deleted == 0:
        raise RuntimeError("Could not delete test message")
