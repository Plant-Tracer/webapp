# Database code

"""Database code for Plant Tracer"""

import functools
import os
import base64
import uuid
import logging
import json
import sys
import copy
import smtplib
from typing import Optional
#import inspect

from jinja2.nativetypes import NativeEnvironment
from validate_email_address import validate_email

from paths import TEMPLATE_DIR,ROOT_DIR
from constants import C

import auth
from auth import get_user_api_key, get_user_ipaddr, get_dbreader, get_dbwriter
from lib.ctools import dbfile
from mailer import InvalidEmail
import mailer

if sys.version < '3.11':
    raise RuntimeError("Requires python 3.11 or above.")

EMAIL_TEMPLATE_FNAME = 'email.txt'
SUPER_ADMIN_COURSE_ID = -1      # this is the super course. People who are admins in this course see everything.

class InvalidAPI_Key(RuntimeError):
    """ API Key is invalid """

class InvalidCourse_Key(Exception):
    """ API Key is invalid """

LOG_DB = 'LOG_DB'
LOG_INFO = 'LOG_INFO'
LOG_WARNING = 'LOG_WARNING'
logging_policy = set()
logging_policy.add(LOG_DB)

LOG_MAX_RECORDS = 5000
MAX_FUNC_RETURN_LOG = 4096      # do not log func_return larger than this
CHECK_MX = False            # True doesn't work

################################################################
# Logging
################################################################


"""
    caller_frame = inspect.currentframe().f_back
    caller_name = caller_frame.f_code.co_name
    caller_keys, _, _, caller_args = inspect.getargvalues(caller_frame)
    args_json = json.dumps(caller_args, default=str)
"""


logit_DEBUG = False
def logit(*, func_name, func_args, func_return):
    # Get the name of the caller
    user_api_key = get_user_api_key()
    user_ipaddr = get_user_ipaddr()

    # Make copies of func_args and func_return so we can modify without fear
    func_args = copy.copy(func_args)
    func_return = copy.copy(func_return)

    if 'movie_data' in func_args and func_args['movie_data'] is not None:
        func_args['movie_data'] = f"({len(func_args['movie_data'])} bytes)"

    func_args   = json.dumps(func_args, default=str)
    func_return = json.dumps(func_return, default=str)

    if len(func_return) > MAX_FUNC_RETURN_LOG:
        func_return = json.dumps({'log_size':len(func_return), 'error':True}, default=str)

    logging.debug("%s(%s) = %s ", func_name, func_args, func_return)

    if LOG_DB in logging_policy:
        dbfile.DBMySQL.csfr(get_dbwriter(),
                            """INSERT INTO logs (
                                time_t,
                                apikey_id, user_id, ipaddr,
                                func_name, func_args, func_return)
                         VALUES (UNIX_TIMESTAMP(),
                                (select min(id) from api_keys where api_key=%s),
                                   (select min(user_id) from api_keys where api_key=%s), %s,
                                 %s, %s, %s )""",
                            (user_api_key, user_api_key, user_ipaddr,
                             func_name, func_args, func_return),
                            debug=logit_DEBUG)

    if LOG_INFO in logging_policy:
        logging.info("%s func_name=%s func_args=%s func_return=%s",
                     user_ipaddr, func_name, func_args, func_return)
    if LOG_WARNING in logging_policy:
        logging.warning("%s func_name=%s func_args=%s func_return=%s",
                        user_ipaddr, func_name, func_args, func_return)


def log(func):
    """Logging decorator --- log both the arguments and what was returned."""
    def wrapper(*args, **kwargs):
        r = func(*args, **kwargs)
        logit(func_name=func.__name__,
              func_args={**kwargs, **{'args': args}},
              func_return=r)
        return r
    return wrapper

def log_args(func):
    """Logging decorator --- log only the arguments, not the response (for things with long responses)."""
    def wrapper(*args, **kwargs):
        logit(func_name=func.__name__,
              func_args={**kwargs, **{'args': args}},
              func_return=None)
        return func(*args, **kwargs)
    return wrapper


def set_log_policy(v):
    logging_policy.clear()
    logging_policy.add(v)


def add_log_policy(v):
    logging_policy.add(v)

#####################
## USER MANAGEMENT ##
#####################

@log_args
def validate_api_key(api_key):
    """
    Validate API key.
    :param: api_key - the key provided by the cookie or the HTML form.
    :return: User dictionary or {} if key is not valid
    """
    ret = dbfile.DBMySQL.csfr(get_dbreader(),
                              """SELECT * from api_keys left join users on user_id=users.id
                              where api_key=%s and api_keys.enabled=1 and users.enabled=1 LIMIT 1""",
                              (api_key, ), asDicts=True)

    if ret:
        dbfile.DBMySQL.csfr(get_dbwriter(),
                            """UPDATE api_keys
                             SET last_used_at=unix_timestamp(),
                             first_used_at=if(first_used_at is null,unix_timestamp(),first_used_at),
                             use_count=use_count+1
                             WHERE api_key=%s""",
                            (api_key,))
        return ret[0]
    return {}

##

@log_args
def lookup_user(*, email=None, user_id=None, get_admin=None, get_courses=None):
    """
    :param: user_id - user ID to get information about.
    :param: group_info - if True get information about the user's groups
    :return: User dictionary augmented with additional information.
    """
    cmd = "select *,id as user_id from users WHERE "
    args = []
    if email:
        cmd += "email=%s "
        args += [email]
    if user_id and not email:
        cmd += "id=%s "
        args += [user_id]
    try:
        ret= dbfile.DBMySQL.csfr(get_dbreader(),cmd, args, asDicts=True)[0]
        # If the user_id was not provided as an argument, provide it.
        if not user_id:
            user_id = ret['user_id']
    except IndexError:
        return {}

    if get_admin:
        ret['admin'] = dbfile.DBMySQL.csfr(get_dbreader(),
                                           """SELECT * from admins where user_id = %s""",
                                           (user_id,), asDicts=True)
    if get_courses:
        ret['courses'] = dbfile.DBMySQL.csfr(get_dbreader(),
                                           """SELECT *,id as course_id from courses where id = %s
                                           OR id in (select course_id from admins where user_id=%s)
                                           """, (user_id,user_id),asDicts=True)
    return ret


################ RENAME AND DELETE ################
@log
def rename_user(*,user_id, email, new_email):
    """Changes a user's email. Requires a correct old_email"""
    dbfile.DBMySQL.csfr(get_dbwriter(), "UPDATE users SET email=%s where id=%s AND email=%s",
                        (email, user_id, new_email))


@log
def delete_user(*,email,purge_movies=False):
    """Delete a user specified by email address.
    :param: email - the email address
    - First deletes the user's API keys
    - Next deletes all of the user's admin bits
    - Finally deletes the user

    Note: this will fail if the user has any outstanding movies (referrential integrity). In that case, the user should simply be disabled.
    Note: A course cannot be deleted if it has any users. A user cannot be deleted if it has any movies.
    Deletes all of the users
    Also deletes the user from any courses where they may be an admin.
    """
    rows = dbfile.DBMySQL.csfr(get_dbreader(),
                               "SELECT id from movies where user_id in (select id from users where email=%s)",
                               (email,))
    if rows:
        if not purge_movies:
            raise RuntimeError(f"user {email} has outstanding movies")
        # This is not the most efficient, but there probably aren't that many movies to purge
        for (movie_id,) in rows:
            purge_movie(movie_id=movie_id)

    dbfile.DBMySQL.csfr(get_dbwriter(), "DELETE FROM admins WHERE user_id in (select id from users where email=%s)", (email,))
    dbfile.DBMySQL.csfr(get_dbwriter(), "DELETE FROM api_keys WHERE user_id in (select id from users where email=%s)", (email,))
    dbfile.DBMySQL.csfr(get_dbwriter(), "DELETE FROM users WHERE email=%s", (email,))


################ REGISTRATION ################

@log
def register_email(*, email, name, course_key=None, course_id=None, demo_user=0):
    """Register a new user as identified by their email address for a given course. Does not make an api_key or send the links with the api_key.
    :param: email - user email
    :param: course_key - the key
    :param: course_id  - the course
    :param: demo_user  - True if this is a demo user
    :return: dictionary of {'user_id':user_id} for user who is registered.
    """

    if not validate_email(email, check_mx=CHECK_MX):
        raise InvalidEmail(email)

    if (course_key is None) and (course_id is None):
        raise ValueError("Either the course_key or the course_id must be provided")

    # Get the course_id if not provided
    if not course_id:
        res = dbfile.DBMySQL.csfr(
            get_dbreader(), "SELECT id FROM courses WHERE course_key=%s", (course_key,))
        if (not res) or (len(res) != 1):
            raise InvalidCourse_Key(course_key)
        course_id = res[0][0]

    dbfile.DBMySQL.csfr(get_dbwriter(),
                        """INSERT INTO users (email, primary_course_id, name, demo)
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE email=%s""",
                        (email, course_id, name, demo_user, email))
    return dbfile.DBMySQL.csfr(get_dbreader(),
                               "SELECT *,id as user_id, primary_course_id as course_id from users where email=%s",
                               (email,),
                               asDicts=True)[0]


@log
def send_links(*, email, planttracer_endpoint, new_api_key):
    """Creates a new api key and sends it to email. Won't resend if it has been sent in MIN_SEND_INTERVAL"""
    PROJECT_EMAIL = 'admin@planttracer.com'

    logging.warning("TK: Insert delay for MIN_SEND_INTERVAL")

    TO_ADDRS = [email]
    with open(os.path.join(TEMPLATE_DIR, EMAIL_TEMPLATE_FNAME), "r") as f:
        msg_env = NativeEnvironment().from_string(f.read())

    logging.info("sending new link to %s",email)
    msg = msg_env.render(to_addrs=",".join([email]),
                         from_addr=PROJECT_EMAIL,
                         planttracer_endpoint=planttracer_endpoint,
                         api_key=new_api_key)

    DRY_RUN = False
    SMTP_DEBUG = "No"
    try:
        smtp_config = auth.smtp_config()
        smtp_config['SMTP_DEBUG'] = SMTP_DEBUG
    except KeyError:
        raise mailer.NoMailerConfiguration()
    try:
        mailer.send_message(from_addr=PROJECT_EMAIL,
                            to_addrs=TO_ADDRS,
                            smtp_config=smtp_config,
                            dry_run=DRY_RUN,
                            msg=msg)
    except smtplib.SMTPAuthenticationError:
        raise mailer.InvalidMailerConfiguration(str(dict(smtp_config)))
    return new_api_key

################ API KEY ################

def make_new_api_key(*,email):
    """Create a new api_key for an email that is registered
    :param: email - the email
    :return: api_key - the api_key
    """
    user = lookup_user(email=email)
    if user and user['enabled'] == 1:
        user_id = user['id']
        api_key = str(uuid.uuid4()).replace('-', '')
        dbfile.DBMySQL.csfr(get_dbwriter(),
                                """INSERT INTO api_keys (user_id, api_key) VALUES (%s,%s)""",

                                (user_id, api_key))
        # Manually log so that the api_key is not logged
        logit(func_name='make_new_api_key', func_args={'email': email}, func_return={'api_key':'*****'})
        return api_key
    return None


@log
def delete_api_key(api_key):
    """Deletes an api_key
    :param: api_key - the api_key
    :return: the number of keys deleted
    """
    if len(api_key) < 10:
        raise InvalidAPI_Key(api_key)
    return dbfile.DBMySQL.csfr(get_dbwriter(),
                               """DELETE FROM api_keys WHERE api_key=%s""",
                               (api_key,))


@log
def list_users(*, user_id):
    """Returns a dictionary with keys:
    'users' - all the courses to which the user has access, and all of the people in them.
    'courses' - all of the courses
    :param: user_id - the user doing the listing (determines what they can see)
    """
    ret = {}
    cmd = """SELECT users.name AS name,users.email AS email,users.primary_course_id as primary_course_id, users.id AS user_id,
                    k.first as first,k.last as last
              FROM users LEFT JOIN
                      (select user_id,min(first_used_at) as first,max(last_used_at) as last from api_keys group by user_id) k
                         ON users.id=k.user_id
              WHERE users.id=%s
                OR users.primary_course_id IN (select primary_course_id from users where id=%s)
                OR users.primary_course_id IN (select course_id from admins where user_id=%s)
                OR %s IN (select user_id from admins where course_id=%s)
              ORDER BY primary_course_id,name,email"""
    args = (user_id, user_id,user_id,user_id,SUPER_ADMIN_COURSE_ID)
    ret['users'] = dbfile.DBMySQL.csfr(get_dbreader(),cmd,args,asDicts=True)

    cmd = """SELECT id as course_id,course_name,course_section,max_enrollment from courses"""
    args = []
    ret['courses'] = dbfile.DBMySQL.csfr(get_dbreader(),cmd,args,asDicts=True)
    return ret

def list_admins():
    """Returns a list of all the admins"""
    return dbfile.DBMySQL.csfr(get_dbreader(),
                               "select *,users.id as user_id FROM users left join admins on users.id=admins.user_id",
                               asDicts=True)

def list_demo_users():
    """Returns a list of all demo accounts and their API keys. This can be downloaded without authentication!"""
    return dbfile.DBMySQL.csfr(get_dbreader(),
                               "select *,users.id as user_id from users left join api_keys on api_keys.user_id=users.id where demo=1 and api_keys.enabled=1",
                               asDicts=True,debug=True)


#########################
### Course Management ###
#########################

def lookup_course(*, course_id):
    try:
        return dbfile.DBMySQL.csfr(get_dbreader(), "select * from courses where id=%s", (course_id,), asDicts=True)[0]
    except IndexError:
        return {}


@log
def create_course(*, course_key, course_name, max_enrollment, course_section=None):
    """Create a new course
    :return: course_id of the new course
    """
    ret = dbfile.DBMySQL.csfr(get_dbwriter(), "INSERT into courses (course_key, course_name, max_enrollment, course_section) values (%s,%s,%s,%s)",
                              (course_key, course_name, max_enrollment, course_section))
    return {'course_id':ret}


@log
def delete_course(*,course_key):
    """Delete a course.
    :return: number of courses deleted.
    """
    return dbfile.DBMySQL.csfr(get_dbwriter(), "DELETE from courses where course_key=%s", (course_key,))


@log
def make_course_admin(*, email, course_key=None, course_id=None):
    """make a course administrator.
    :param email: email address of the administrator
    :param course_key: - if specified, use this course_key
    :param course_id: - if specified, use this course_id
    Note - either course_key or course_id must be None, but both may not be none
    """
    user_id = lookup_user(email=email)['user_id']
    logging.info("make_course_admin. email=%s user_id=%s",email,user_id)

    assert ((course_key is None) and (course_id is not None)) or ((course_key is not None) and (course_id is None))
    if course_key and course_id is None:
        course_id = dbfile.DBMySQL.csfr(get_dbreader(), "SELECT id from courses WHERE course_key=%s",(course_key,))[0][0]
        logging.info("course_id=%s",course_id)

    dbfile.DBMySQL.csfr(get_dbwriter(), "INSERT into admins (course_id, user_id) values (%s, %s)",
                        (course_id, user_id))
    return {'user_id':user_id,'course_id':course_id}


@log
def remove_course_admin(*, email, course_key=None, course_id=None):
    if course_id:
        dbfile.DBMySQL.csfr(get_dbwriter(),
                            "DELETE FROM admins WHERE course_id=%s and user_id in (select id from users where email=%s)",
                            (course_id, email))
    if course_key:
        dbfile.DBMySQL.csfr(get_dbwriter(),
                            "DELETE FROM admins where course_id in (SELECT id FROM courses WHERE course_key=%s) "
                            "AND user_id IN (SELECT id FROM users WHERE email=%s)",
                            (course_key, email))


@log
def check_course_admin(*, user_id, course_id):
    """Return True if user_id is an admin in course_id"""
    res = dbfile.DBMySQL.csfr(get_dbreader(), "SELECT * FROM admins WHERE user_id=%s AND course_id=%s LIMIT 1",
                              (user_id, course_id))
    return len(res) == 1


@log
def validate_course_key(*, course_key):
    res = dbfile.DBMySQL.csfr(get_dbreader(),
                              """SELECT course_key FROM courses WHERE course_key=%s LIMIT 1""", (course_key,))
    return len(res) == 1 and res[0][0] == course_key


@log
def remaining_course_registrations(*,course_key):
    res = dbfile.DBMySQL.csfr(get_dbreader(),
                              """SELECT max_enrollment
                              - (SELECT COUNT(*) FROM users
                              WHERE primary_course_id=(SELECT id FROM courses WHERE course_key=%s))
                              FROM courses WHERE course_key=%s""",
                              (course_key, course_key))
    try:
        return int(res[0][0])
    except (IndexError, ValueError):
        return 0



########################
### Movie Management ###
########################

@log
def get_movie_data(*, movie_id):
    """Returns the movie contents. Does no checking"""
    logging.debug("movie_id=%s",movie_id)
    return dbfile.DBMySQL.csfr(get_dbreader(), "SELECT movie_data from movie_data where movie_id=%s LIMIT 1", (movie_id,))[0][0]


@log
def get_movie_metadata(*,user_id, movie_id):
    """Gets the metadata for all movies accessible by user_id or enumerated by movie_id.
    This is used for the movie list.
    """

    cmd = """SELECT *,id as movie_id from movies WHERE
                ((user_id=%s) OR
                (%s=0) OR
                (course_id=(select primary_course_id from users where id=%s)) OR
                (course_id in (select course_id from admins where user_id=%s)))
    """
    params = [user_id, user_id, user_id, user_id]
    if movie_id:
        cmd += " AND movies.id=%s"
        params.append(movie_id)

    return dbfile.DBMySQL.csfr(get_dbreader(), cmd, params, asDicts=True)

@log
def can_access_movie(*, user_id, movie_id):
    """Return if the user is allowed to access the movie."""
    res = dbfile.DBMySQL.csfr(
        get_dbreader(),
        """select count(*) from movies WHERE id=%s AND
        (user_id=%s OR
        course_id=(select primary_course_id from users where id=%s) OR
        course_id in (select course_id from admins where user_id=%s))""",
        (movie_id, user_id, user_id, user_id))
    return res[0][0] > 0

@log
def can_access_frame(*, user_id, frame_id=None):
    """Return if the user is allowed to access a specific frame.
    """
    res = dbfile.DBMySQL.csfr(
            get_dbreader(),
            """select count(*) from movies WHERE id in (select movie_id from movie_frames where id=%s)
            AND ( (user_id=%s) OR
                  (course_id=(select primary_course_id from users where id=%s)) OR
                  (course_id in (select course_id from admins where user_id=%s)) OR
                  (%s = 0) )
            """,
            (frame_id, user_id, user_id, user_id, user_id))
    return res[0][0] > 0

@log
def movie_frames_info(*,movie_id):
    """Gets information about movie frames"""
    ret = {}
    ret['count'] = dbfile.DBMySQL.csfr(
        get_dbreader(), "SELECT count(*) from movie_frames where movie_id=%s", (movie_id,))[0][0]
    return ret

@log
def purge_movie_frames(*,movie_id):
    """Delete the frames associated with a movie."""
    logging.debug("purge_movie_frames movie_id=%s",movie_id)
    dbfile.DBMySQL.csfr(
        get_dbwriter(), "DELETE from movie_frame_analysis where frame_id in (select id from movie_frames where movie_id=%s)", (movie_id,))
    dbfile.DBMySQL.csfr(
        get_dbwriter(), "DELETE from movie_frame_trackpoints where frame_id in (select id from movie_frames where movie_id=%s)", (movie_id,))
    dbfile.DBMySQL.csfr(
        get_dbwriter(), "DELETE from movie_frames where movie_id=%s", (movie_id,))

@log
def purge_movie_data(*,movie_id):
    """Delete the frames associated with a movie."""
    logging.debug("purge_movie_data movie_id=%s",movie_id)
    dbfile.DBMySQL.csfr(
        get_dbwriter(), "DELETE from movie_data where movie_id=%s", (movie_id,))

@log
def purge_movie(*,movie_id):
    """Actually delete a movie and all its frames"""
    purge_movie_frames(movie_id=movie_id)
    purge_movie_data(movie_id=movie_id)
    dbfile.DBMySQL.csfr(
        get_dbwriter(), "DELETE from movies where id=%s", (movie_id,))


@log
def delete_movie(*,movie_id, delete=1):
    """Set a movie's deleted bit to be true"""
    dbfile.DBMySQL.csfr(
        get_dbwriter(), "UPDATE movies SET deleted=%s where id=%s", (delete, movie_id,))


@log
def create_new_movie(*, user_id, title=None, description=None, movie_data=None, movie_metadata=None, orig_movie=None):
    res = dbfile.DBMySQL.csfr(
        get_dbreader(), "select primary_course_id from users where id=%s", (user_id,))
    if not res or len(res) != 1:
        logging.error("len(res)=%s", len(res))
        logging.error("res=%s", res)
        raise RuntimeError(f"user_id={user_id} len(res)={len(res)} res={res}")
    primary_course_id = res[0][0]
    movie_id = dbfile.DBMySQL.csfr(get_dbwriter(),
                                   """INSERT INTO movies (title,description,user_id,course_id,orig_movie) VALUES (%s,%s,%s,%s,%s)
                                    """,
                                   (title, description, user_id, primary_course_id,orig_movie))
    if movie_data:
        dbfile.DBMySQL.csfr(get_dbwriter(),
                            "INSERT INTO movie_data (movie_id, movie_data) values (%s,%s)",
                            (movie_id, movie_data))
    if movie_metadata:
        dbfile.DBMySQL.csfr(get_dbwriter(),
                            "UPDATE movies SET " + ",".join(f"{key}=%s" for key in movie_metadata.keys()) + " " +
                            "WHERE id = %s",
                            list(movie_metadata.values()) + [movie_id])

    return movie_id


################################################################
## frames
################################################################


# Don't log this; it will blow up the database when movies are updated
def create_new_frame(*, movie_id, frame_number, frame_data=None):
    """Get the frame id specified by movie_id and frame_number.
    if frame_data is provided, update. Otherwise just return the frame_id.
    """

    args = (movie_id, frame_number, movie_id, frame_number)
    a1 = a2 = a3 = ""
    if frame_data is not None:
        a1 = ", frame_data"
        a2 = ",%s"
        a3 = ",frame_data=%s"
        args = (movie_id, frame_number, frame_data, movie_id, frame_number,frame_dat)
    dbfile.DBMySQL.csfr(get_dbwriter(),
                        f"""INSERT INTO movie_frames (movie_id, frame_number{a1})
                        VALUES (%s,%s{a2})
                        ON DUPLICATE KEY UPDATE movie_id=%s,frame_number=%s{a3}""",
                        args)
    frame_id = dbfile.DBMySQL.csfr(get_dbwriter(),"SELECT id from movie_frames where movie_id=%s and frame_number=%s",
                                   (movie_id, frame_number))[0][0]
    return frame_id


def get_frame_annotations(*, frame_id):
    """Returns a list of dictionaries where each dictonary represents a record.
    Within that record, 'annotations' is stored in the database as a JSON string,
    but we turn it into a dictionary on return, so that we don't have JSON encapsulating JSON when we send the data to the client.
    """

    ret = dbfile.DBMySQL.csfr(get_dbreader(),
                               """SELECT movie_frame_analysis.id AS movie_frame_analysis_id,
                                         frame_id,engine_id,annotations,engines.name as engine_name,
                                         engines.version AS engine_version FROM movie_frame_analysis
                               LEFT JOIN engines ON engine_id=engines.id
                               WHERE frame_id=%s ORDER BY engines.name,engines.version""",
                               (frame_id,),
                               asDicts=True)
    # Now go through every annotations cell and decode the object
    for r in ret:
        r['annotations'] = json.loads(r['annotations'])
    return ret

def get_frame_trackpoints(*, frame_id):
    """Returns a list of trackpoint dictionaries where each dictonary represents a trackpoint.
    """
    return  dbfile.DBMySQL.csfr(get_dbreader(),
                               """
                               SELECT id as movie_frame_trackpoints_id,
                                      frame_id,x,y,label FROM movie_frame_trackpoints
                               WHERE frame_id=%s""",
                               (frame_id,),
                               asDicts=True)

def get_movie_trackpoints(*, movie_id):
    """Returns a list of trackpoint dictionaries where each dictonary represents a trackpoint.
    """
    return  dbfile.DBMySQL.csfr(get_dbreader(),
                               """
                               SELECT frame_number,x,y,label
                               FROM movie_frame_trackpoints
                               LEFT JOIN movie_frames ON movie_frame_trackpoints.frame_id = movie_frames.id
                               WHERE movie_id=%s
                               ORDER BY frame_number
                               """,
                               (movie_id,),
                               asDicts=True)

def last_tracked_frame(*, movie_id):
    """Return the last tracked frame_number of the movie"""
    return dbfile.DBMySQL.csfr(get_dbreader(),
                               """SELECT max(movie_frames.frame_number)
                               FROM movie_frame_trackpoints
                               LEFT JOIN movie_frames ON movie_frame_trackpoints.frame_id = movie_frames.id
                               WHERE movie_id=%s
                               """,
                               (movie_id,))[0][0]

def get_frame(*, frame_id=None, movie_id=None, frame_number=None,
              get_annotations=False, get_trackpoints=False):
    """Get a frame by frame_id, or by movie_id and either offset or frame number, Don't log this to prevent blowing up.
    :param: movie_id - the movie_id wanted
    :param: get_annotations - return anotations in the 'annotations' slot
    :param: get_trackpoints - returns the trackpoints in the 'trackpoints' slot.
    :return: returns a dictionary with the frame info
    """
    if frame_id is not None:
        where = 'WHERE id = %s '
        args  = [frame_id]
    else:
        where = "WHERE movie_id=%s AND frame_number=%s"
        args = [movie_id, frame_number]
    cmd = f"""SELECT id as frame_id, movie_id, frame_number, frame_data FROM movie_frames {where} LIMIT 1"""
    rows = dbfile.DBMySQL.csfr(get_dbreader(), cmd, args, asDicts=True)
    if len(rows)!=1:
        return None
    row = rows[0]
    if get_annotations:
        row['annotations'] = get_frame_annotations(frame_id=row['frame_id'])
    if get_trackpoints:
        row['trackpoints'] = get_frame_trackpoints(frame_id=row['frame_id'])
    return row


def get_analysis_engine_id(*, engine_name, engine_version):
    """Create an analysis engine if it does not exist, and return the engine_id"""
    dbfile.DBMySQL.csfr(get_dbwriter(),
                        """INSERT INTO engines
                        (`name`,version) VALUES (%s,%s)
                        ON DUPLICATE KEY UPDATE name=%s""",
                        (engine_name,engine_version,engine_name))
    return dbfile.DBMySQL.csfr(get_dbreader(),
                               """SELECT id from engines
                               WHERE `name`=%s and version=%s""",
                               (engine_name,engine_version))[0][0]

def delete_analysis_engine_id(*, engine_id):
    """Deletes an analysis engine_id. This fails if the engine_id is in use"""
    dbfile.DBMySQL.csfr(get_dbwriter(),
                        "DELETE from engines where id=%s",(engine_id,))

def encode_json(d):
    """Given json data, encode it as base64 and return as an SQL
    statement that processes it. We use this as a way of quoting a
    JSON object that is then inserted into the database. (Other approaches for quoting failed.)"""
    djson = json.dumps(d)
    dlen  = len(djson)
    return "cast(from_base64('" + base64.b64encode( json.dumps(d).encode() ).decode() + f"') as char({dlen+1000}))"

def put_frame_annotations(*,
                       frame_id:int,
                       annotations:Optional[dict | list],
                       engine_id:Optional[int] =None,
                       engine_name:Optional[str]=None,
                       engine_version:Optional[str]=None, ):
    """
    :param: frame_id - integer with frame id
    :param: annotations - a dictionary that will be escaped
    :param: engine_id - engine_id to use
    :param: engine_name - string of engine to use; create the engine_id if it doesn't exist
    :param: engine_version - string of version to use.
    """

    if (engine_id is None) and ((engine_name is None) or (engine_version is None)):
        raise RuntimeError("if engine_id is None, then both engine_name and engine_version must be provided")
    if (engine_name is None) and (engine_id is None):
        raise RuntimeError("if engine_name is None, then engine_id must be provided.")
    if (engine_id is not None) and (engine_name is not None):
        raise RuntimeError("Both engine_name and engine_id may not be provided.")

    # Get the engine_id if only engine_name is provided
    if engine_id is None:
        engine_id = get_analysis_engine_id(engine_name=engine_name, engine_version=engine_version)

    if (not isinstance(annotations,dict)) and (not isinstance(annotations,list)):
        raise ValueError(f"annotations is type {type(annotations)}, should be type dict or list")

    ea = encode_json(annotations)

    #
    # We use base64 encoding to get by the quoting problems.
    # This means we need a format string, rather than a prepared statement.
    # The int() and the ea() provide sufficient protection.
    dbfile.DBMySQL.csfr(get_dbwriter(),
                        f"""INSERT INTO movie_frame_analysis
                        (frame_id, engine_id, annotations)
                        VALUES ({int(frame_id)},{int(engine_id)},{ea})
                        ON DUPLICATE KEY UPDATE
                        annotations={ea} """)

def put_frame_trackpoints(*, frame_id:int, trackpoints:list[dict]):
    """
    :frame_id: the frame to replace. If the frame has existing trackpoints, they are overwritten
    :param: trackpoints - array of dicts where each dict has an x, y and label. Other fields are ignored.
    """
    vals = []
    for tp in trackpoints:
        if ('x' not in tp) or ('y' not in tp) or ('label') not in tp:
            raise KeyError(f'trackpoints element {tp} missing x, y or label')
        vals.extend([frame_id,tp['x'],tp['y'],tp['label']])
    dbfile.DBMySQL.csfr(get_dbwriter(),"DELETE FROM movie_frame_trackpoints where frame_id=%s",(frame_id,))
    if vals:
        args = ",".join(["(%s,%s,%s,%s)"]*len(trackpoints))
        cmd = f"INSERT INTO movie_frame_trackpoints (frame_id,x,y,label) VALUES {args}"
        logging.debug("cmd=%s vals=%s",cmd,vals)
        dbfile.DBMySQL.csfr(get_dbwriter(),cmd,vals)

def delete_frame_analysis(*, frame_id=None, engine_id=None):
    """Deletes all annotations associated with frame_id or engine_id. If frame_id is provided, also delete all trackpoints"""
    if (frame_id is None) and (engine_id is None):
        raise RuntimeError("frame_id and/or engine_id must not be None")

    cmd = "DELETE FROM movie_frame_analysis WHERE "
    args = []
    if frame_id:
        cmd += "frame_id=%s "
        args.append(frame_id)
    if frame_id and engine_id:
        cmd += " AND "
    if engine_id:
        cmd += " engine_id=%s"
        args.append(engine_id)
    dbfile.DBMySQL.csfr(get_dbwriter(),cmd, args)

    if frame_id is not None:
        cmd = "DELETE FROM movie_trackpoints WHERE frame_id=%s"
        dbfile.DBMySQL.csfr(get_dbwriter(), cmd, [frame_id,])


def delete_analysis_engine(*, engine_name, version=None, recursive=None):
    """Delete the analysis engine.
    :param: engine_name - the engine to delete
    :param: version - the version number to delete. If None, delete all versions.
    :param: recursive - if True, delete all of the data that is tagged with this engine
    """
    args = [engine_name]
    where = "name=%s "
    if version:
        where += "AND version=%s "
        args.append(version)
    if recursive:
        dbfile.DBMySQL.csfr(get_dbwriter(), f"delete from movie_analysis where engine_id in (SELECT id from engines where {where})",args)
        dbfile.DBMySQL.csfr(get_dbwriter(), f"delete from movie_frame_analysis where engine_id in (SELECT id from engines where {where})",args)

    dbfile.DBMySQL.csfr(get_dbwriter(), f"delete from engines where {where}",args)


# Don't log this; we run list_movies every time the page is refreshed
def list_movies(*,user_id, movie_id=None, orig_movie=None, no_frames=False):
    """Return a list of movies that the user is allowed to access.
    This should be updated so that we can request only a specific movie
    :param: user_id - only list movies visible to user_id (0 for all movies)
    :param: movie_id - if provided, only use this movie
    :param: orig_movie - if provided, only list movies for which the original movie is orig_movie_id
    :param: no_frames - If true, only list movies that have no frames in movie_frames
    """
    cmd = """SELECT movies.id as movie_id,title,description,movies.created_at as created_at,
          user_id,course_id,published,deleted,date_uploaded,name,email,primary_course_id,orig_movie
          FROM movies LEFT JOIN users ON movies.user_id = users.id
          WHERE
          ((user_id=%s)
            OR (course_id = (SELECT primary_course_id FROM users WHERE id=%s) AND published>0 AND deleted=0)
            OR (course_id in (SELECT course_id FROM admins WHERE user_id=%s))
            OR (%s=0)
          )
          """
    args = [user_id, user_id, user_id, user_id]

    if movie_id:
        cmd += " AND movies.id=%s "
        args.append(movie_id)

    if orig_movie:
        cmd += " AND movies.orig_movie=%s "
        args.append(orig_movie)

    if no_frames:
        cmd += " AND (movies.id not in (select distinct movie_id from movie_frames)) "
    cmd += " ORDER BY movies.id "

    res = dbfile.DBMySQL.csfr(get_dbreader(), cmd, args, asDicts=True)
    return res

###
# Movie analysis
###

@log
def create_new_movie_analysis(*, movie_id, engine_id, annotations):
    if movie_id:
        movie_analysis_id = dbfile.DBMySQL.csfr(get_dbwriter(),
                                                """INSERT INTO movie_analysis (movie_id, engine_id, annotations) VALUES (%s,%s,%s)""",
                                                (movie_id, engine_id, annotations))
        return {'movie_analysis_id': movie_analysis_id}
    else:
        return {'movie_analysis_id': None}

@log
def delete_movie_analysis(*,movie_analysis_id):
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from movie_analysis WHERE id=%s", ([movie_analysis_id]))

@log
def purge_engine(*,engine_id):
    assert engine_id is not None
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from movie_analysis WHERE engine_id=%s", ([engine_id]))
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from movie_frame_analysis WHERE engine_id=%s", ([engine_id]))
    delete_engine(engine_id=engine_id)

@log
def delete_engine(*,engine_id):
    assert engine_id is not None
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from engines WHERE id=%s", ([engine_id]))

################################################################
## Logs
################################################################

# Do we need to log get_logs?
def get_logs( *, user_id , start_time = 0, end_time = None, course_id=None, course_key=None, movie_id=None, log_user_id=None,
              ipaddr=None, count=LOG_MAX_RECORDS, offset=0, security=True):
    """get log entries (to which the user is entitled)
    :param: user_id    - the user who is initiating the query
    :param: start_time - The earliest log entry to provide (time_t)
    :param: end_time   - the last log entry to provide (time_t)
    :param: course_id  - if provided, only provide log entries for this course
    :param: movie_id   - if provided, only provide log entries for this movie
    :param: log_user_id - if provided, only provide log entries for this person
    :param: count      - maximum number of log entries to provide (for paging)
    :param: offset     - Offset into SQL SELECT (for paging)
    :param: security   - False to disable security checks
    :return: list of dictionaries of log records.
    """

    count = max(count, LOG_MAX_RECORDS)

    # First find all of the records requested by the searcher
    cmd = """SELECT * FROM logs WHERE (time_t >= %s """
    args = [start_time]

    if end_time:
        cmd += "AND (time_t <= %s) "
        args.append(end_time)

    if course_id:
        cmd += "AND ((func_args->'$.course_id'=%s) OR (func_return->'$.course_id'=%s)) "
        args += [course_id, course_id]

    if course_key:
        cmd += """AND (func_args->'$.course_key'=%s
                       OR (func_args->'$.course_id' IN (select id from courses where course_key=%s))
                       OR (func_return->'$.course_id' IN (select id from courses where course_key=%s)) )
        """
        args += [course_key, course_key, course_key]

    if movie_id:
        cmd += "AND (func_args->'$.movie_id'=%s) "
        args.append(movie_id)

    if ipaddr:
        cmd += "AND (ipaddr=%s) "
        args.append(ipaddr)

    if log_user_id:
        cmd += "AND ((user_id=%s OR func_args->'$.user_id'=%s OR func_return->'$.user_id'=%s))"
        args += [log_user_id, log_user_id, log_user_id]

    cmd += ") "

    # now put in the security controls

    if security:
        cmd += " AND ("

        # If the user owns the record, or if the record is about the user:
        cmd += "(user_id=%s OR func_args->'$.user_id'=%s OR func_return->'$.user_id'=%s) "
        args += [user_id, user_id, user_id]

        cmd += " OR "

        # If the log record is about a course, and the user is an admin in the course
        cmd += " (func_args->'$.course_id' IN (SELECT course_id FROM admins WHERE user_id=%s ))"
        args += [user_id]

        cmd += " OR "

        cmd += "  (func_return->'$.course_id' IN (SELECT course_id FROM admins WHERE user_id=%s ))"
        args += [user_id]

        # If the user is the super admin:

        cmd += " OR (%s IN (SELECT user_id FROM admins WHERE course_id=%s)) "
        args += [user_id, SUPER_ADMIN_COURSE_ID]

        cmd += ")"

    # finally limit the output for pagination

    cmd += "LIMIT %s OFFSET %s"
    args.append(count)
    args.append(offset)

    return dbfile.DBMySQL.csfr(get_dbreader(), cmd, args, asDicts=True)



################################################################
## Metadata
################################################################


# set movie metadata privileges array:
# columns indicate WHAT is being set, WHO can set it, and HOW to set it
SET_MOVIE_METADATA = {
    # title can be changed by the owner or the admin
    'title': 'update movies set title=%s where id=%s and (@is_owner or @is_admin)',

    # description can be changed by owner or admin
    'description': 'update movies set description=%s where id=%s and (@is_owner or @is_admin)',

    # the user can delete or undelete movies; the admin can only delete them
    'deleted': 'update movies set deleted=%s where id=%s and (@is_owner or (@is_admin and deleted=0))',

    # the admin can publish or unpublish movies; the user can only unpublish them
    'published': 'update movies set published=%s where id=%s and (@is_admin or (@is_owner and published!=0))',
}


@log
def set_metadata(*, user_id, set_movie_id=None, set_user_id=None, prop, value):
    """We tried doing this in a single statement and it failed"""
    # First compute @is_owner

    logging.info("set_user_id=%s set_movie_id=%s prop=%s value=%s",
                 set_user_id, set_movie_id, prop, value)
    assert isinstance(user_id, int)
    assert isinstance(set_movie_id, int) or (set_movie_id is None)
    assert isinstance(set_user_id, int) or (set_user_id is None)
    assert isinstance(prop, str)
    assert value is not None

    MAPPER = {0: 'FALSE', 1: 'TRUE'}

    if set_movie_id:
        res = dbfile.DBMySQL.csfr(get_dbreader(
        ), "SELECT %s in (select user_id from movies where id=%s)", (user_id, set_movie_id))
        is_owner = MAPPER[res[0][0]]

        res = dbfile.DBMySQL.csfr(get_dbreader(),
                                  "SELECT %s in (select user_id from admins where course_id=(select course_id from movies where id=%s))",
                                  (user_id, set_movie_id))
        is_admin = MAPPER[res[0][0]]

        cmd = SET_MOVIE_METADATA[prop].replace(
            '@is_owner', is_owner).replace('@is_admin', is_admin)
        args = [value, set_movie_id]

        ret = dbfile.DBMySQL.csfr(get_dbwriter(), cmd, args)
        return ret

    # Currently, users can only set their own data
    if set_user_id:
        if user_id == set_user_id:
            prop = prop.lower()
            if prop in ['name', 'email']:
                ret = dbfile.DBMySQL.csfr(get_dbwriter(),
                                          f"UPDATE users set {prop}=%s where id=%s",
                                          (value, user_id))
                return ret
    return None
