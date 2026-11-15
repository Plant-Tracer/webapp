"""
Mailer tests are all done with the local mail server.

Originally we tested with a real mail server, but we couldn't reach it from Github actions.
TODO: Test with real mail server when running on Dreamhost?
"""


import time
import uuid
import copy
from urllib.parse import urlencode

import pytest
from jinja2.nativetypes import NativeEnvironment
from app import odb
from app import apikey
from app import mailer
from app.constants import E, logger

from app.odb import COURSE_KEY


MSG = """to: {{ to_addrs }}
from: {{ from_addr }}
subject: This is a test subject {{ guid }}

This is a test message.
"""

FAKE_USER_EMAIL = f'fake-user@{str(uuid.uuid4())}.planttracer.com'
FAKE_NAME       = f'fake-name-{str(uuid.uuid4())}'
FAKE_SENDER     = f'do-not-reply@{str(uuid.uuid4())}.planttracer.com'

#@pytest.mark.skip(reason="changing authentication")
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
    def callback(num, M):
        if nonce in M['subject']:
            return mailer.DELETE
        return None

    imap_config = mailer_config['imap']
    for i in range(50):
        deleted = mailer.imap_inbox_scan(imap_config, callback)
        if deleted > 0:
            break

        logger.warning("response %s not found. Sleep again count %d", nonce, i)
        time.sleep(0.1)
    if deleted == 0:
        raise RuntimeError(f"Could not find and delete test message using smtp_config={smtp_config} imap_config={imap_config}")


#@pytest.mark.skip(reason="changing authentication")
def test_register_email(client, mailer_config,new_course):
    """Some tests of the email registration software in db"""
    cfg = copy.copy(new_course)
    course_key = cfg[COURSE_KEY]

    with pytest.raises(odb.InvalidUser_Email):
        odb.register_email(email='invalid-email', user_name='valid-name', course_key=course_key)

    with pytest.raises(ValueError):
        odb.register_email(email=FAKE_USER_EMAIL, user_name='valid-name', course_key=None, course_id=None)

    with pytest.raises(odb.InvalidCourse_Key):
        odb.register_email(email=FAKE_USER_EMAIL, user_name='valid-name', course_key='invalid-course-key', course_id=None)


    invalid_course = client.post('/api/register', data={'email': FAKE_USER_EMAIL, 'course_key': 'invalid-course-key'})
    assert invalid_course.json == E.INVALID_COURSE_KEY

    response = client.post('/api/register',
                           data = {'email':FAKE_USER_EMAIL,
                                   'course_key':course_key,
                                   'name':FAKE_NAME,
                                   'planttracer_endpoint': 'http://localhost/'})
    assert response.status_code == 200

    try:
        user_id = response.json['user_id']
    except KeyError as e:
        raise ValueError(f"/api/register response {response.json} is invalid") from e

    key = odb.get_first_api_key_for_user(user_id)
    login_url = f'http://localhost/login?api_key={key}'
    params = {odb.API_KEY: key, odb.COURSE_ID: cfg[odb.COURSE_ID]}
    camera_url = f'http://localhost/camera?{urlencode(params)}'

    def check_registration_email(_number, message):
        if message['To'] != FAKE_USER_EMAIL:
            return None
        plain = message.get_body(preferencelist=('plain',)).get_content()
        html = message.get_body(preferencelist=('html',)).get_content()
        assert login_url in plain and login_url in html
        assert camera_url in plain
        assert camera_url.replace('&', '&amp;') in html
        return mailer.DELETE

    try:
        for _ in range(50):
            if mailer.imap_inbox_scan(mailer_config['imap'], check_registration_email):
                break
            time.sleep(0.1)
        else:
            pytest.fail('Registration message did not arrive')
        camera = client.get(camera_url, follow_redirects=True)
        assert camera.status_code == 200
        assert camera.request.path == '/camera'
        assert b'id="camera-root"' in camera.data
        assert client.get_cookie(apikey.cookie_name()).value == key
    finally:
        odb.delete_user(user_id=user_id, purge_movies=True)
