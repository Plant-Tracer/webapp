"""
Test the various functions in the database involving user creation.
"""

import sys
import os
import uuid
import logging
import pytest
import uuid
import base64
import time
import copy
import hashlib
from os.path import abspath, dirname

from fixtures.app_client import client
from fixtures.local_aws import local_s3, new_course

import app.db as db
import app.odbmaint as odbmaint
import app.bottle_api as bottle_api
import app.bottle_app as bottle_app
import app.dbfile as dbfile
from app.paths import TEST_DIR, TEST_DATA_DIR

################################################################
## fixture tests
################################################################

def test_new_course(new_course_user):
    cfg = copy.copy(new_course)
    course_key = cfg[COURSE_KEY]
    admin_email = cfg[ADMIN_EMAIL]
    logging.info("Created course %s", course_key)

    # Check course lookup functions
    c1 = db.lookup_course_by_key(course_key = cfg[COURSE_KEY])
    c2 = db.lookup_course_by_name(course_name = cfg[COURSE_NAME])
    assert c1 == c2
    assert c1['course_key'] == cfg[COURSE_KEY]

def test_demo_user(new_course):
    cfg = copy.copy(new_course)
    demo_email  = cfg[USER_EMAIL].replace("@","+demo@")

    odb.register_email(demo_email, "Demo User", course_id=cfg[COURSE_ID], demo_user=1, admin=0)
    res = odb.list_demo_users()
    assert len(res)==1
    assert res['email']==demo_email
    assert odb.remaining_course_registrations(course_key=cfg[COURSE_KEY]) == C.DEFAULT_MAX_ENROLLMENT - 2


def test_add_remove_user_and_admin(new_course):
    """Tests creating a new user and adding them to the course as an admin"""
    cfg = copy.copy(new_course)
    course_key = cfg[COURSE_KEY]

    for admin in range(0,2):
        new_email = f"some-user{str(uuid.uuid4())[0:8]}@company.com")
        user = odb.register_email(email=admin_email,
                                  course_key=cfg[COURSE_KEY],
                                  name='User Name',
                                  admin = admin)
        user_id = user['user_id']

        logging.info("generated admin_email=%s user_id=%s",admin_email, user_id)
        course_id = odb.lookup_course_by_key(course_key = cfg[COURSE_KEY])['course_id']

        if admin:
            odb.make_course_admin(email = admin_email, course_id = course_id)
            assert odb.check_course_admin(user_id=user_id, course_id=course_id)
            odb.remove_course_admin(email = admin_email, course_id = course_id)
            assert not odb.check_course_admin(user_id=user_id, course_id=course_id)
        odb.delete_user(user_id=user_id)


def test_get_logs(new_course):
    """Incrementally test each part of the get_logs functions. Pretend we are root. We don't really care what the returns are"""
    for security in [False,True]:
        logging.info("security=%s",security)
        db.get_logs( user_id=0 , security=security)
        db.get_logs( user_id=0, start_time = 0 , security=security)
        db.get_logs( user_id=0, end_time = 0 , security=security)
        db.get_logs( user_id=0, course_key = 0 , security=security)
        db.get_logs( user_id=0, movie_id = 0, security=security)
        db.get_logs( user_id=0, log_user_id = 0, security=security)
        db.get_logs( user_id=0, ipaddr = "", security=security)

    api_key  = new_course[API_KEY]
    user_id  = new_course['user_id']
    response = client.post('/api/get-logs',
                           data = {'api_key': api_key, 'user_id':user_id})

    # Turns out that there are no logs with this user, since the scaffolding calls register_email
    # for the new_user with a NULL user_id....

def test_course_list(client, new_course):
    cfg        = copy.copy(new_course)
    user_email = cfg[USER_EMAIL]
    api_key    = cfg[API_KEY]

    user_dict = odb.validate_api_key(api_key)
    user_id   = user_dict['user_id']
    primary_course_id = user_dict['primary_course_id']

    recs1 = odb.list_users(user_id=user_id)
    users1 = recs1['users']

    matches = [user for user in users1 if user['user_id']==user_id]
    assert(len(matches)>0)

    # Make sure that there is an admin in the course who is not the user
    recs2 = odb.list_admins()
    matches = [rec for rec in recs2 if rec['course_id']==primary_course_id and rec['user_id']!=user_id]
    assert len(matches)==1

    # Make sure that the endpoint works
    response = client.post('/api/list-users',
                           data = {'api_key': api_key})

    res = response.get_json()
    assert res['error'] is False
    users2 = res['users']
    # There is the user and the admin; there may also be a demo user
    assert len(users2) in [2,3]
    assert users1[0]['name'] == users2[0]['name']
    assert users1[0]['email'] == users2[0]['email']


@pytest.mark.skip(reason="logging currently disabled")
def test_log_search_user(new_user):
    """Currently we just run logfile queries and count the number of results."""
    cfg        = copy.copy(new_user)
    user_email = cfg[USER_EMAIL]
    api_key    = cfg[API_KEY]

    user_id  = db.validate_api_key(api_key)['user_id']

    ret = db.get_logs( user_id=user_id )
    logging.info("search for user_email=%s user_id=%s returns %s logs",user_email,user_id, len(ret))

    assert len(ret) > 0
    assert len(db.get_logs( user_id=user_id, start_time = 10)) > 0
    assert len(db.get_logs( user_id=user_id, end_time = time.time())) > 0

    # Make sure that restricting the time to something that happened more than a day ago fails,
    # because we just created this user.
    assert len(db.get_logs( user_id=user_id, end_time = time.time()-24*60*60)) ==0

    # Find the course that this user is in
    res = dbfile.DBMySQL.csfr(dbreader, "select primary_course_id from users where id=%s", (user_id,))
    assert(len(res)==1)
    course_id = res[0][0]

    res = dbfile.DBMySQL.csfr(dbreader, "select course_key from courses where id=%s", (course_id,))
    assert(len(res)==1)
    course_key = res[0][0]

    assert(len(db.get_logs( user_id=user_id, course_id = course_id)) > 0)
    assert(len(db.get_logs( user_id=user_id, course_key = course_key)) > 0)

    # Test to make sure that the course admin gets access to this user
    admin_id = dbfile.DBMySQL.csfr(dbreader,
                                   "SELECT user_id FROM admins WHERE course_id=%s LIMIT 1",
                                   (course_id,))[0]
    assert(len(db.get_logs( user_id=admin_id, log_user_id=user_id, course_id = course_id)) > 0)
    assert(len(db.get_logs( user_id=admin_id, log_user_id=user_id, course_key = course_key)) > 0)

    # We should have nothing with this IP address
    assert(len(db.get_logs( user_id=user_id, ipaddr="0.0.0.0"))==0)
