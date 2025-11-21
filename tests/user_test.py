"""
Test the various functions in the database involving user creation.
"""

import uuid
import logging
import copy

from app import odb
from app import odbmaint
from app.constants import C
from app.odb import ExistingCourse_Id, UserExists, COURSE_ID, API_KEY, COURSE_KEY
from dbutil import DEMO_COURSE_ID,DEMO_COURSE_NAME,DEFAULT_ADMIN_EMAIL,DEFAULT_ADMIN_NAME,DEMO_USER_EMAIL,DEMO_USER_NAME

# Fixtures are imported in conftest.py
from .fixtures.local_aws import ADMIN_EMAIL



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
    logging.info("Created course %s admin_email %s", course_key, admin_email )

    # Check course lookup functions
    c1 = odb.lookup_course_by_key(course_key = cfg[COURSE_KEY])
    c2 = odb.lookup_course_by_id(course_id = cfg[COURSE_ID])
    assert c1 == c2
    assert c1[ COURSE_KEY  ] == cfg[COURSE_KEY]


# Make sure that there is a demo user
def test_demo_user(new_course):
    #cfg = copy.copy(new_course)
    try:
        odbmaint.create_course(course_id  = DEMO_COURSE_ID,
                               course_name = DEMO_COURSE_NAME,
                               course_key = str(uuid.uuid4())[0:8],
                               admin_email = DEFAULT_ADMIN_EMAIL,
                               admin_name  = DEFAULT_ADMIN_NAME,
                               max_enrollment = 2)
    except ExistingCourse_Id:
        pass

    try:
        odb.register_email(DEMO_USER_EMAIL, DEMO_USER_NAME, course_id=DEMO_COURSE_ID)
    except UserExists:
        pass

    # Create the demo user to own the demo movies
    odb.make_new_api_key(email=DEMO_USER_EMAIL, demo_user=True)        # Give the demo user an API key
    userdict = odb.validate_api_key( C.DEMO_MODE_API_KEY )
    assert 'created' in userdict

def test_add_remove_user_and_admin(new_course):
    """Tests creating a new user and adding them to the course as an admin"""
    cfg = copy.copy(new_course)
    #course_key = cfg[COURSE_KEY]

    for admin in range(0,2):
        new_email = f"some-user{str(uuid.uuid4())[0:8]}@company.com"
        user_id = odb.register_email(email=new_email,
                                  course_key=cfg[COURSE_KEY],
                                  user_name='User Name',
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


def test_course_list(client, new_course):
    cfg        = copy.copy(new_course)
    #user_email = cfg[USER_EMAIL]
    api_key    = cfg[API_KEY]

    user_dict = odb.validate_api_key(api_key)
    user_id   = user_dict['user_id']
    #primary_course_id = user_dict['primary_course_id']

    recs1 = odb.list_users_courses(user_id=user_id)
    users1 = recs1['users']

    matches = [user for user in users1 if user['user_id']==user_id]
    assert len(matches)>0

    # Make sure that there is an admin in the course (it's the user)
    recs2 = odb.list_admins()
    assert len(recs2)>=1        # we could do a better test

    # Make sure that the endpoint works
    response = client.post('/api/list-users',
                           data = {'api_key': api_key})

    res = response.get_json()
    assert res['error'] is False
    users2 = res['users']

    # There is only an admin in the course. Make sure it is the same
    assert len(users2) in [1]
    assert users1[0]['user_name'] == users2[0]['user_name']
