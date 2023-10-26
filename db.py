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
#import inspect

from jinja2.nativetypes import NativeEnvironment
from validate_email_address import validate_email

from paths import DBREADER_BASH_PATH, DBWRITER_BASH_PATH, TEMPLATE_DIR, DBCREDENTIALS_PATH, BOTTLE_APP_INI_PATH

from auth import get_user_api_key, get_user_ipaddr
from lib.ctools import dbfile
import mailer

if sys.version < '3.11':
    raise RuntimeError("Requires python 3.11 or above.")

EMAIL_TEMPLATE_FNAME = 'email.txt'
SUPER_ADMIN_COURSE_ID = -1      # this is the super course. People who are admins in this course see everything.

class InvalidEmail(RuntimeError):
    """Exception thrown in email is invalid"""

class InvalidAPI_Key(RuntimeError):
    """ API Key is invalid """

class InvalidCourse_Key(RuntimeError):
    """ API Key is invalid """

LOG_DB = 'LOG_DB'
LOG_INFO = 'LOG_INFO'
LOG_WARNING = 'LOG_WARNING'
logging_policy = set()
logging_policy.add(LOG_DB)

LOG_MAX_RECORDS = 5000
MAX_FUNC_RETURN_LOG = 4096      # do not log func_return larger than this
CHECK_MX = False            # True doesn't work

@functools.cache
def get_dbreader():
    """Get the dbreader authentication info from:
    1 - the [dbreader] section of the DBCREDENTIALS file the DBWRITER_BASH_PATH if it exists.
    2 - 'export VAR=VALUE' from the DBWRITER_BASH_PATH if it exists.
    3 - From the environment variables MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE.
    """
    logging.debug("get_dbreader")
    if DBCREDENTIALS_PATH is not None and os.path.exists(BOTTLE_APP_INI_PATH):
        logging.info("authentication from %s", DBCREDENTIALS_PATH)
        return dbfile.DBMySQLAuth.FromConfigFile(DBCREDENTIALS_PATH, 'dbreader')
    fname = DBREADER_BASH_PATH if os.path.exists(DBREADER_BASH_PATH) else None
    logging.info("authentication from %s", fname)
    return dbfile.DBMySQLAuth.FromBashEnvFile(fname)


@functools.cache
def get_dbwriter():
    """Get the dbwriter authentication info from:
    1 - the [dbwriter] section of the DBCREDENTIALS file the DBWRITER_BASH_PATH if it exists.
    2 - 'export VAR=VALUE' from the DBWRITER_BASH_PATH if it exists.
    3 - From the environment variables MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE.
    """

    if DBCREDENTIALS_PATH is not None and os.path.exists(BOTTLE_APP_INI_PATH):
        return dbfile.DBMySQLAuth.FromConfigFile(DBCREDENTIALS_PATH, 'dbwriter')

    fname = DBWRITER_BASH_PATH if os.path.exists(DBWRITER_BASH_PATH) else None
    return dbfile.DBMySQLAuth.FromBashEnvFile(fname)


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

    if not isinstance(func_args, str):
        func_args = json.dumps(func_args, default=str)
    if not isinstance(func_return, str):
        func_return = json.dumps(func_return, default=str)

    if len(func_return) > MAX_FUNC_RETURN_LOG:
        func_return = json.dumps({'log_size':len(func_return), 'error':True})

    logging.debug("func_name=%s func_args=%s func_return=%s logging_policy=%s",
                  func_name, func_args, func_return, logging_policy)

    if LOG_DB in logging_policy:
        logging.debug("LOG_DB in logging_policy")
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
def rename_user(user_id, email, new_email):
    """Changes a user's email. Requires a correct old_email"""
    dbfile.DBMySQL.csfr(get_dbwriter(), "UPDATE users SET email=%s where id=%s AND email=%s",
                        (email, user_id, new_email))


@log
def delete_user(email):
    """Delete a user. A course cannot be deleted if it has any users. A user cannot be deleted if it has any movies.
    Also deletes the user from any courses where they may be an admin.
    """
    dbfile.DBMySQL.csfr(get_dbwriter(
    ), "DELETE FROM admins WHERE user_id in (select id from users where email=%s)", (email,))
    dbfile.DBMySQL.csfr(
        get_dbwriter(), "DELETE FROM users WHERE email=%s", (email,))


################ REGISTRATION ################

@log
def register_email(*, email, name, course_key=None, course_id=None):
    """Register email for a given course
    :param: email - user email
    :param: course_key - the key
    :return: dictionary of {'user_id':user_id} for user who is registered.
    """

    if not validate_email(email, check_mx=CHECK_MX):
        raise InvalidEmail(email)

    assert not ((course_key is None) and (course_id is None))

    # Get the course_id if not provided
    if not course_id:
        res = dbfile.DBMySQL.csfr(
            get_dbreader(), "SELECT id FROM courses WHERE course_key=%s", (course_key,))
        if (not res) or (len(res) != 1):
            raise InvalidCourse_Key(course_key)
        course_id = res[0][0]

    user_id =  dbfile.DBMySQL.csfr(get_dbwriter(),
                               """INSERT INTO users (email, primary_course_id, name) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE email=%s""",
                               (email, course_id, name, email))
    return {'user_id':user_id,'course_id':course_id}


@log
def send_links(*, email, planttracer_endpoint):
    """Creates a new api key and sends it to email. Won't resend if it has been sent in MIN_SEND_INTERVAL"""
    PROJECT_EMAIL = 'admin@planttracer.com'

    logging.warning("TK: Insert delay for MIN_SEND_INTERVAL")

    TO_ADDRS = [email]
    with open(os.path.join(TEMPLATE_DIR, EMAIL_TEMPLATE_FNAME), "r") as f:
        msg_env = NativeEnvironment().from_string(f.read())
    new_api_key = make_new_api_key(email=email)

    if not new_api_key:
        logging.info("not in database: %s",email)
        return
    logging.info("sending new link to %s",email)
    msg = msg_env.render(to_addrs=",".join([email]),
                         from_addr=PROJECT_EMAIL,
                         planttracer_endpoint=planttracer_endpoint,
                         api_key=new_api_key)

    DRY_RUN = False
    SMTP_DEBUG = "No"
    smtp_config = mailer.smtp_config_from_environ()
    smtp_config['SMTP_DEBUG'] = SMTP_DEBUG
    mailer.send_message(from_addr=PROJECT_EMAIL,
                        to_addrs=TO_ADDRS,
                        smtp_config=smtp_config,
                        dry_run=DRY_RUN,
                        msg=msg
                        )

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
    user_id = lookup_user(email=email)['user_id']
    logging.info("make_course_admin. email=%s user_id=%s",email,user_id)

    if course_key and course_id is None:
        course_id = dbfile.DBMySQL.csfr(get_dbreader(), "SELECT id from courses WHERE course_key=%s",(course_key,))[0][0]
        logging.info("course_id=%s",course_id)

    dbfile.DBMySQL.csfr(get_dbwriter(), "INSERT into admins (course_id, user_id) values (%s, %s)",
                        (course_id, user_id))
    return {'user_id':user_id,'course_id':course_id}


@log
def remove_course_admin(*, email, course_key=None, course_id=None):
    if course_id:
        dbfile.DBMySQL.csfr(get_dbwriter(), "DELETE FROM admins WHERE course_id=%s and user_id in (select id from users where email=%s)",
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
    cmd = """SELECT *,id as movie_id from movies WHERE
                ((user_id=%s) OR
                (%s=0) OR
                (course_id=(select primary_course_id from users where id=%s)) OR
                (course_id in (select course_id from admins where user_id=%s))) """
    params = [user_id, user_id, user_id, user_id]
    if movie_id:
        cmd += " AND movies.id=%s"
        params.append(movie_id)
    return dbfile.DBMySQL.csfr(get_dbreader(), cmd, params, asDicts=True)


@log
def can_access_movie(*, user_id, movie_id):
    """Return if the user is allowed to access the movie"""
    res = dbfile.DBMySQL.csfr(
        get_dbreader(),
        """select count(*) from movies WHERE id=%s AND
        (user_id=%s OR
        course_id=(select primary_course_id from users where id=%s) OR
        course_id in (select course_id from admins where user_id=%s))""",
        (movie_id, user_id, user_id, user_id))
    return res[0][0] > 0


@log
def movie_frames_info(*,movie_id):
    """Gets information about movie frames"""
    ret = {}
    ret['count'] = dbfile.DBMySQL.csfr(
        get_dbwriter(), "SELECT count(*) from movie_frames where movie_id=%s", (movie_id,))[0][0]
    return ret

@log
def purge_movie_frames(*,movie_id):
    """Delete the frames associated with a movie."""
    logging.debug("purge_movie_frames movie_id=%s",movie_id)
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
def create_new_movie(*, user_id, title=None, description=None, movie_data=None):
    res = dbfile.DBMySQL.csfr(
        get_dbreader(), "select primary_course_id from users where id=%s", (user_id,))
    if not res or len(res) != 1:
        logging.error("len(res)=%s", len(res))
        logging.error("res=%s", res)
        raise RuntimeError(f"user_id={user_id} len(res)={len(res)} res={res}")
    primary_course_id = res[0][0]
    movie_id = dbfile.DBMySQL.csfr(get_dbwriter(),
                                   """INSERT INTO movies (title,description,user_id,course_id) VALUES (%s,%s,%s,%s)
                                    """,
                                   (title, description, user_id, primary_course_id))
    if movie_data:
        dbfile.DBMySQL.csfr(get_dbwriter(),
                            "INSERT INTO movie_data (movie_id, movie_data) values (%s,%s)",
                            (movie_id, movie_data))
    return {'movie_id':movie_id}


# Don't log this; it will blow up the database when movies are updated
def create_new_frame(*, movie_id, frame_msec, frame_data):
    frame_id = dbfile.DBMySQL.csfr(get_dbwriter(),
                                   """INSERT INTO movie_frames (movie_id, frame_msec, frame_data)
                                       VALUES (%s,%s,%s)
                                       ON DUPLICATE KEY UPDATE frame_msec=%s, frame_data=%s""",
                                   (movie_id, frame_msec, frame_data,
                                    frame_data, frame_msec))
    return {'frame_id':frame_id}


# Get a frame; again, don't log
def get_frame(*, movie_id, frame_msec, msec_delta):
    if msec_delta==0:
        delta = "frame_msec = %s "
    elif msec_delta>0:
        delta = "frame_msec > %s order by frame_msec "
    else:
        delta = "frame_msec < %s order by frame_msec DESC "
    ret = dbfile.DBMySQL.csfr(get_dbreader(),
                               """SELECT movie_id, frame_msec, frame_data
                               FROM movie_frames
                               WHERE movie_id=%s and {delta} LIMIT 1""", (movie_id,frame_msec),asDicts=True)
    if len(ret)>0:
        return ret[0]
    return None


# Don't log this; we run list_movies every time the page is refreshed
def list_movies(user_id):
    """Return a list of movies that the user is allowed to access.
    This should be updated so that we can request only a specific movie
    """
    res = dbfile.DBMySQL.csfr(get_dbreader(),
                              """SELECT movies.id as movie_id,title,description,movies.created_at as created_at,
                                          user_id,course_id,published,deleted,date_uploaded,name,email,primary_course_id
                                FROM movies LEFT JOIN users ON movies.user_id = users.id
                                WHERE (user_id=%s)
                                OR
                                (course_id = (SELECT primary_course_id FROM users WHERE id=%s) AND published>0 AND deleted=0)
                                OR
                                (course_id in (SELECT course_id FROM admins WHERE user_id=%s))
                              OR
                              (%s=0)
                              ORDER BY movies.id
                              """,
                              (user_id, user_id, user_id, user_id), asDicts=True)
    return res


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
