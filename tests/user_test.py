"""
Test the various functions in the database involving user creation.
"""

import sys
import os
import uuid
import logging
import pytest
import base64
import time
import copy
import hashlib
from os.path import abspath, dirname

from app import odb
from app import odbmaint
from app import bottle_api
from app import bottle_app
from app.paths import TEST_DIR, TEST_DATA_DIR
from app.constants import C

from app.odb import EMAIL

from fixtures.app_client import client
from fixtures.local_aws import local_ddb, local_s3, new_course, COURSE_KEY, ADMIN_EMAIL, COURSE_NAME, COURSE_ID, USER_EMAIL



################################################################
## fixture tests
################################################################

def test_ddb(local_ddb):
    logging.info("test_ddb local_ddb=%s",local_ddb)

def test_ddb2(local_ddb):
    logging.info("test_ddb local_ddb=%s",local_ddb)

def test_new_course(new_course):
    cfg = copy.copy(new_course)
    course_key = cfg[COURSE_KEY]
    admin_email = cfg[ADMIN_EMAIL]
    logging.info("Created course %s", course_key )

    # Check course lookup functions
    c1 = odb.lookup_course_by_key(course_key = cfg[COURSE_KEY])
    c2 = odb.lookup_course_by_id(course_id = cfg[COURSE_ID])
    assert c1 == c2
    assert c1[ COURSE_KEY  ] == cfg[COURSE_KEY]


def test_demo_user(new_course):
    cfg = copy.copy(new_course)
    demo_email  = cfg[USER_EMAIL].replace("@","+demo@")

    odb.register_email(demo_email, "Demo User", course_id=cfg[COURSE_ID], demo_user=1, admin=0)
    res = odb.list_demo_users()
    logging.debug("res=%s",res)
    assert len(res)==1
    assert res[0]['email']==demo_email
    assert odb.remaining_course_registrations(course_key=cfg[COURSE_KEY]) == C.DEFAULT_MAX_ENROLLMENT - 3

def test_add_remove_user_and_admin(new_course):
    """Tests creating a new user and adding them to the course as an admin"""
    cfg = copy.copy(new_course)
    course_key = cfg[COURSE_KEY]

    for admin in range(0,2):
        new_email = f"some-user{str(uuid.uuid4())[0:8]}@company.com"
        user_id = odb.register_email(email=new_email,
                                  course_key=cfg[COURSE_KEY],
                                  full_name='User Name',
                                  admin = admin)['user_id']

        logging.info("generated admin_email=%s user_id=%s",new_email, user_id)
        course_id = odb.lookup_course_by_key(course_key = cfg[COURSE_KEY])['course_id']

        if not admin:
            assert not odb.check_course_admin(user_id=user_id, course_id=course_id)
            odb.add_course_admin(admin_id = user_id, course_id = course_id)
            assert odb.check_course_admin(user_id=user_id, course_id=course_id)
            odb.remove_course_admin(admin_id = user_id, course_id = course_id)
            assert not odb.check_course_admin(user_id=user_id, course_id=course_id)

        if admin:
            assert odb.check_course_admin(user_id=user_id, course_id=course_id)
            odb.add_course_admin(admin_id = user_id, course_id = course_id)
            assert odb.check_course_admin(user_id=user_id, course_id=course_id)
            odb.remove_course_admin(admin_id = user_id, course_id = course_id)
            assert not odb.check_course_admin(user_id=user_id, course_id=course_id)
        odb.delete_user(user_id=user_id)
