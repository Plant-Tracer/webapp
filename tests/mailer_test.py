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
import copy

from os.path import abspath, dirname, join

from fixtures.localmail_config import mailer_config
from fixtures.app_client import client

from user_test import new_user,new_course,MOVIE_ID,MOVIE_TITLE,API_KEY,COURSE_KEY

import app.db as db
import app.mailer as mailer


MSG = """to: {{ to_addrs }}
from: {{ from_addr }}
subject: This is a test subject {{ guid }}

This is a test message.
"""

FAKE_USER_EMAIL = f'fake-user@{str(uuid.uuid4())}.planttracer.com'
FAKE_NAME       = f'fake-name-{str(uuid.uuid4())}'
FAKE_SENDER     = f'do-not-reply@{str(uuid.uuid4())}.planttracer.com'

@pytest.mark.skip(reason="changing authentication")
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
        raise RuntimeError(f"Could not find and delete test message using smtp_config={smtp_config} imap_config={imap_config}")


@pytest.mark.skip(reason="changing authentication")
def test_register_email(client, mailer_config,new_course):
    cfg = copy.copy(new_course)
    course_key = cfg[COURSE_KEY]

    """Some tests of the email registration software in db"""
    with pytest.raises(mailer.InvalidEmail):
        db.register_email(email='invalid-email', name='valid-name')

    with pytest.raises(ValueError):
        db.register_email(email=FAKE_USER_EMAIL, name='valid-name', course_key=None, course_id=None)

    with pytest.raises(db.InvalidCourse_Key):
        db.register_email(email=FAKE_USER_EMAIL, name='valid-name', course_key='invalid-course-key', course_id=None)


    # try register api
    response = client.post('/api/register',
                           data = {'email':FAKE_USER_EMAIL,
                                   'course_key':course_key,
                                   'name':FAKE_NAME})
    assert response.status_code == 200

    # TODO: verify if registration mail appeared
    # Now delete the user
    db.delete_user(email=FAKE_USER_EMAIL, purge_movies=True)
