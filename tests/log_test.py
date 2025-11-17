import copy
import logging
import time

import pytest

from fixtures.app_client import client
from fixtures.local_aws import USER_EMAIL

from app import odb
from app.odb import API_KEY

# These are for the old MySQL-based logging system (currently disabled)
# dbfile and dbreader would need to be imported from the old system if re-enabled
dbfile = None  # type: ignore
dbreader = None  # type: ignore
db = odb  # type: ignore

@pytest.mark.skip(reason="logging currently disabled")
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
    _response = client.post('/api/get-logs',
                           data = {'api_key': api_key, 'user_id':user_id})

    # Turns out that there are no logs with this user, since the scaffolding calls register_email
    # for the new_user with a NULL user_id....

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
    assert len(res)==1
    course_id = res[0][0]

    res = dbfile.DBMySQL.csfr(dbreader, "select course_key from courses where id=%s", (course_id,))
    assert len(res)==1
    course_key = res[0][0]

    assert len(db.get_logs( user_id=user_id, course_id = course_id)) > 0
    assert len(db.get_logs( user_id=user_id, course_key = course_key)) > 0

    # Test to make sure that the course admin gets access to this user
    admin_id = dbfile.DBMySQL.csfr(dbreader,
                                   "SELECT user_id FROM admins WHERE course_id=%s LIMIT 1",
                                   (course_id,))[0]
    assert len(db.get_logs( user_id=admin_id, log_user_id=user_id, course_id = course_id)) > 0
    assert len(db.get_logs( user_id=admin_id, log_user_id=user_id, course_key = course_key)) > 0

    # We should have nothing with this IP address
    assert len(db.get_logs( user_id=user_id, ipaddr="0.0.0.0"))==0
