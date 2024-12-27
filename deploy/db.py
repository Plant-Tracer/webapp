# Database code

"""Database code for Plant Tracer"""

# pylint: disable=too-many-lines
# pylint: disable=too-many-arguments

import os
import uuid
import logging
import json
import sys
import copy
import smtplib
import functools

from flask import request

from botocore.exceptions import ClientError,ParamValidationError
from jinja2.nativetypes import NativeEnvironment

# from validate_email_address import validate_email


from . import auth
from . import db_object
from . import dbfile
from . import mailer
from .paths import TEMPLATE_DIR
from .constants import MIME,C
from .auth import get_dbreader, get_dbwriter

if sys.version < '3.11':
    raise RuntimeError("Requires python 3.11 or above.")

EMAIL_TEMPLATE_FNAME = 'email.txt'
SUPER_ADMIN_COURSE_ID = -1      # this is the super course. People who are admins in this course see everything.

LOG_DB = 'LOG_DB'
LOG_INFO = 'LOG_INFO'
LOG_WARNING = 'LOG_WARNING'
logging_policy = set()
logging_policy.add(LOG_DB)

LOG_MAX_RECORDS = 5000
MAX_FUNC_RETURN_LOG = 4096      # do not log func_return larger than this
CHECK_MX = False            # True doesn't work

################################################################
## Errors
################################################################

class DB_Errors(RuntimeError):
    """Base class for DB Errors"""

class InvalidAPI_Key(DB_Errors):
    """ API Key is invalid """

class InvalidCourse_Key(DB_Errors):
    """ Course Key is invalid """

class InvalidMovie_Id(DB_Errors):
    """ MovieID is invalid """
    def __init__(self, v):
        super().__init__(str(v))

class InvalidFrameAccess(DB_Errors):
    """ FrameID is invalid """


class UnauthorizedUser(DB_Errors):
    """ User is not authorized for movie"""

class NoMovieData(DB_Errors):
    """There is no data for the movie"""


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
    user_api_key = 0 # FIXME; was get_user_api_key()
    try:
        user_ipaddr  = request.remote_addr
    except RuntimeError:
        user_ipaddr  = '<local>'

    # Make copies of func_args and func_return so we can modify without fear
    func_args   = copy.copy(func_args)
    func_return = copy.copy(func_return)

    func_args   = json.dumps(func_args, default=str)
    func_return = json.dumps(func_return, default=str)

    if len(func_return) > MAX_FUNC_RETURN_LOG:
        func_return = json.dumps({'log_size':len(func_return), 'error':True}, default=str)

    logging.debug("%s(%s) = %s ", func_name, func_args, func_return)

    if (LOG_DB in logging_policy) and False:
        dbfile.DBMySQL.csfr(get_dbwriter(),
                            """INSERT INTO logs ( time_t, apikey_id, user_id, ipaddr, func_name, func_args, func_return)
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
    """Logging decorator --- log both the arguments and what was returned.
    TODO: add an option parameter of arguments not to log.
    """
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

    logging.debug("validate_api_key(%s)=%s dbreader=%s",api_key,ret,get_dbreader())
    if ret:
        dbfile.DBMySQL.csfr(get_dbwriter(),
                            """UPDATE api_keys
                             SET last_used_at=unix_timestamp(),
                             first_used_at=if(first_used_at is null,unix_timestamp(),first_used_at),
                             use_count=use_count+1
                             WHERE api_key=%s""",
                            (api_key,))
        return dict(ret[0])
    return {}

##

@log_args
def lookup_user(*, email=None, user_id=None, get_admin=None, get_courses=None):
    """
    :param: user_id - user ID to get information about.
    :param: get_admin - if True get information user's admin roles
    :param: get_courses - if True get information about the user's courses
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
                                           """, (ret['primary_course_id'],user_id),asDicts=True)
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
                               "SELECT id as movie_id,title from movies where user_id in (select id from users where email=%s)",
                               (email,),asDicts=True)
    if rows:
        if not purge_movies:
            for row in rows:
                logging.error("row=%s",row)
            raise RuntimeError(f"user {email} has {len(rows)} outstanding movies.")
        # This is not the most efficient, but there probably aren't that many movies to purge
        for row in rows:
            purge_movie(movie_id=row['movie_id'])

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
    except KeyError as e:
        raise mailer.NoMailerConfiguration() from e
    try:
        mailer.send_message(from_addr=PROJECT_EMAIL,
                            to_addrs=TO_ADDRS,
                            smtp_config=smtp_config,
                            dry_run=DRY_RUN,
                            msg=msg)
    except smtplib.SMTPAuthenticationError as e:
        raise mailer.InvalidMailerConfiguration(str(dict(smtp_config))) from e
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
    return dbfile.DBMySQL.csfr(get_dbwriter(), """DELETE FROM api_keys WHERE api_key=%s""", (api_key,))

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
    """Returns a list of all demo accounts."""
    return dbfile.DBMySQL.csfr(get_dbreader(),
                               "select *,users.id as user_id from users where demo=1",
                               asDicts=True)

def get_demo_user_api_key(*,user_id):
    keys = dbfile.DBMySQL.csfr(get_dbreader(),
                               "select api_key from api_keys where user_id=%s and user_id in (select id from users where demo=1)",
                               (user_id,))
    if keys:
        return keys[0][0]
    return None




#########################
### Course Management ###
#########################

def lookup_course_by_id(*, course_id):
    try:
        return dbfile.DBMySQL.csfr(get_dbreader(),
                                   "SELECT * FROM courses WHERE id=%s", (course_id,), asDicts=True)[0]
    except IndexError:
        return {}

def lookup_course_by_key(*, course_key):
    try:
        return dbfile.DBMySQL.csfr(get_dbreader(),
                                   "SELECT * FROM courses WHERE course_key=%s", (course_key,), asDicts=True)[0]
    except IndexError:
        return {}

def lookup_course_by_name(*, course_name):
    try:
        return dbfile.DBMySQL.csfr(get_dbreader(),
                                   "SELECT * FROM courses WHERE course_name=%s", (course_name,), asDicts=True)[0]
    except IndexError:
        return {}
@log
def create_course(*, course_key, course_name, max_enrollment, course_section=None):
    """Create a new course
    :return: course_id of the new course
    """
    ret = dbfile.DBMySQL.csfr(get_dbwriter(),
                              "INSERT into courses (course_key, course_name, max_enrollment, course_section) values (%s,%s,%s,%s)",
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
def remove_course_admin(*, email, course_key=None, course_id=None, course_name=None):
    if course_id:
        dbfile.DBMySQL.csfr(get_dbwriter(),
                            "DELETE FROM admins WHERE course_id=%s and user_id in (select id from users where email=%s)",
                            (course_id, email))
    if course_key:
        dbfile.DBMySQL.csfr(get_dbwriter(),
                            "DELETE FROM admins where course_id in (SELECT id FROM courses WHERE course_key=%s) "
                            "AND user_id IN (SELECT id FROM users WHERE email=%s)",
                            (course_key, email))
    if course_name:
        dbfile.DBMySQL.csfr(get_dbwriter(),
                            "DELETE FROM admins where course_id in (SELECT id FROM courses WHERE course_name=%s) "
                            "AND user_id IN (SELECT id FROM users WHERE email=%s)",
                            (course_name, email))



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
def get_movie_data(*, movie_id:int, zipfile=False):
    """Returns the movie contents for a movie_id.
    Should not be used to provide data to the user.
    """
    what = "movie_zipfile_urn" if zipfile else "movie_data_urn"
    row = dbfile.DBMySQL.csfr(get_dbreader(), f"""SELECT {what} from movies where id=%s""", (movie_id,))
    try:
        urn = row[0][0]
    except IndexError as e:
        raise InvalidMovie_Id(movie_id) from e
    logging.info("movie_id=%s zipfile=%s what=%s urn=%s",movie_id,zipfile,what,urn)

    if urn:
        return db_object.read_object(urn)
    return None


@log
def get_movie_metadata(*,user_id, movie_id, get_last_frame_tracked=False):
    """Gets the metadata for all movies accessible by user_id or enumerated by movie_id.
    This is used for the movie list.
    """

    cmd = """SELECT A.id AS movie_id, A.title AS title, A.description AS description,
                    A.created_at AS created_at, A.user_id AS user_id,
                    A.course_id AS course_id, A.published AS published, A.deleted AS deleted,
                    A.date_uploaded AS date_uploaded, A.mtime AS mtime, A.version AS version,
                    A.fps as fps, A.width as width, A.height as height,
                    A.total_frames AS total_frames, A.total_bytes as total_bytes, A.status AS status,
                    A.movie_data_urn as movie_data_urn,
                    A.movie_zipfile_urn as movie_zipfile_urn,
                    B.id AS tracked_movie_id
             FROM movies A
             LEFT JOIN movies B on A.id=B.orig_movie
             WHERE
                ((A.user_id=%s) OR
                (%s=0) OR
                (A.course_id=(select primary_course_id from users where id=%s)) OR
                (A.course_id in (select course_id from admins where A.user_id=%s)))
    """
    assert isinstance(user_id,int)
    assert isinstance(movie_id,(int,type(None)))
    params = [user_id, user_id, user_id, user_id]
    if movie_id is not None:
        cmd += " AND A.id=%s"
        params.append(movie_id)

    ret = dbfile.DBMySQL.csfr(get_dbreader(), cmd, params, asDicts=True)
    if get_last_frame_tracked:
        ret = [ {**r,**{'last_frame_tracked':last_tracked_frame(movie_id=r['movie_id'])}} for r in ret]
    return ret


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

################################################################
## Movie frames


@log
def create_new_movie(*, user_id, title=None, description=None, orig_movie=None):
    """
    Creates an entry for a new movie and returns the movie_id. The movie content must be uploaded separately.

    :param: user_id  - person creating movie. Stored in movies table.
    :param: title - title of movie. Stored in movies table
    :param: description - description of movie
    :param: movie_metadata - if presented, metadata for the movie. Stored in movies SQL table.
    :param: orig_movie - if presented, the movie_id of the movie on which this is based
    """
    # Create a new movie record
    movie_id = dbfile.DBMySQL.csfr(get_dbwriter(),
                                   """INSERT INTO movies (title,description,user_id,course_id,orig_movie)
                                   VALUES (%s,%s,%s,(select primary_course_id from users where id=%s),%s)
                                    """,
                                   (title, description, user_id, user_id,orig_movie))
    return movie_id


def set_movie_data_urn(*, movie_id, movie_data_urn):
    """
    Sets the movie data for a movie. Either movie_data or movie_data_urn must be provided, but not both.
    :param: movie_data_urn - if presented, the URL at which the data can or will be found.
    """
    dbfile.DBMySQL.csfr(get_dbwriter(),
                        "UPDATE movies set movie_data_urn=%s where id=%s",
                        (movie_data_urn, movie_id))


def set_movie_metadata(*, movie_id, movie_metadata):
    """Set the movie_metadata from a dictionary."""
    dbfile.DBMySQL.csfr(get_dbwriter(),
                        "UPDATE movies SET " + ",".join(f"{key}=%s" for key in movie_metadata.keys()) + " " +
                        "WHERE id = %s",
                        list(movie_metadata.values()) + [movie_id])


def set_movie_data(*,movie_id, movie_data):
    """If we are setting the movie data, be sure that any old data (frames, zipfile, stored objects) are gone"""
    purge_movie_data(movie_id=movie_id)
    purge_movie_frames( movie_id=movie_id )
    purge_movie_zipfile( movie_id=movie_id )
    object_name= db_object.object_name( course_id = course_id_for_movie_id( movie_id ),
                                        movie_id = movie_id,
                                        ext=C.MOVIE_EXTENSION)
    movie_data_urn        = db_object.make_urn( object_name = object_name)
    set_movie_data_urn(movie_id = movie_id, movie_data_urn=movie_data_urn)
    db_object.write_object(movie_data_urn, movie_data)


################################################################
## Deleting

# pylint: disable=unused-argument
def null_callback(*args,**kwargs):
    return

@log
def purge_movie_frames(*,movie_id,callback=null_callback):
    """Delete the frames associated with a movie."""
    logging.debug("purge_movie_frames movie_id=%s",movie_id)
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from movie_frame_trackpoints where  movie_id=%s", (movie_id,))
    for row in dbfile.DBMySQL.csfr(get_dbwriter(),
                                   "SELECT frame_urn from movie_frames where movie_id=%s and frame_urn is not NULL",(movie_id,)):
        if callback:
            callback(row)
        db_object.delete_object(row[0])
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from movie_frames where movie_id=%s", (movie_id,))

@log
def purge_movie_data(*,movie_id,callback=null_callback):
    """Delete the frames associated with a movie."""
    logging.debug("purge_movie_data movie_id=%s",movie_id)
    for row in dbfile.DBMySQL.csfr( get_dbwriter(),
                                    "SELECT movie_data_urn from movies where id=%s and movie_data_urn is not NULL",
                                    (movie_id,), asDicts=True):
        if callback:
            callback(row)
            try:
                db_object.delete_object(row['movie_data_urn'])
            except (ClientError,ParamValidationError):
                logging.warning("invalid URN: %s",row['movie_data_urn'])
    dbfile.DBMySQL.csfr( get_dbwriter(), "UPDATE movies set movie_data_urn=NULL where id=%s",(movie_id,))

@log
def purge_movie_zipfile(*,movie_id,callback=null_callback):
    """Delete the frames associated with a movie."""
    logging.debug("purge_movie_data movie_id=%s",movie_id)
    for row in dbfile.DBMySQL.csfr( get_dbwriter(),
                                    "SELECT movie_zipfile_urn from movies where id=%s and movie_zipfile_urn is not NULL", (movie_id,), asDicts=True):
        try:
            callback(row)
            db_object.delete_object(row['movie_zipfile_urn'])
        except (ClientError,ParamValidationError):
            logging.warning("invalid URN: %s",row['movie_zipfile_urn'])
    dbfile.DBMySQL.csfr( get_dbwriter(), "UPDATE movies set movie_zipfile_urn=NULL where id=%s",(movie_id,))

@log
def purge_movie(*,movie_id, callback=null_callback):
    """Actually delete a movie and all its frames"""
    purge_movie_frames(movie_id=movie_id, callback=callback)
    purge_movie_data(movie_id=movie_id, callback=callback)
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from movies where id=%s", (movie_id,))


@log
def delete_movie(*,movie_id, delete=1):
    """Set a movie's deleted bit to be true"""
    dbfile.DBMySQL.csfr( get_dbwriter(), "UPDATE movies SET deleted=%s where id=%s", (delete, movie_id,))


################################################################



################################################################
## frames
################################################################

@functools.lru_cache(maxsize=128)
def course_id_for_movie_id(movie_id):
    return get_movie_metadata(user_id=0, movie_id=movie_id)[0]['course_id']

@functools.lru_cache(maxsize=128)
def movie_data_urn_for_movie_id(movie_id):
    return get_movie_metadata(user_id=0, movie_id=movie_id)[0]['movie_data_urn']

@functools.lru_cache(maxsize=128)
def movie_zipfile_urn_for_movie_id(movie_id):
    return get_movie_metadata(user_id=0, movie_id=movie_id)[0]['movie_data_urn']

# New implementation that writes to s3
# Possible -  move jpeg compression here? and do not write out the frame if it was already written out?
def create_new_frame(*, movie_id, frame_number, frame_data=None):
    """Get the frame id specified by movie_id and frame_number.
    if frame_data is provided, save it as an object in s3e. Otherwise just return the frame_urn.
    if trackpoints are provided, replace current trackpoints with those. This is used sometimes
    just to update the frame_data

    returns frame_urn
    """
    logging.debug("create_new_frame(movie_id=%s, frame_number=%s, type(frame_data)=%s",movie_id, frame_number, type(frame_data))
    args = (movie_id, frame_number )
    a1 = a2 = a3 = ""
    frame_urn = None
    if frame_data is not None:
        # upload the frame to the store and make a frame_urn
        object_name = db_object.object_name(course_id=course_id_for_movie_id(movie_id),
                                            movie_id=movie_id,
                                            frame_number = frame_number,
                                            ext=C.JPEG_EXTENSION)
        frame_urn = db_object.make_urn( object_name = object_name)
        db_object.write_object(frame_urn, frame_data)

        a1 = ", frame_urn"
        a2 = ",%s"
        a3 = ",frame_urn=%s"
        args = (movie_id, frame_number, frame_urn, frame_urn)

    # Update the database
    logging.debug("a1=%s a2=%s a3=%s args=%s",a1,a2,a3,args)
    dbfile.DBMySQL.csfr(get_dbwriter(),
                        f"""INSERT INTO movie_frames (movie_id, frame_number{a1})
                        VALUES (%s,%s{a2})
                        ON DUPLICATE KEY UPDATE movie_id=movie_id{a3}""",
                        args)
    return frame_urn

@log
def get_frame_urn(*, movie_id, frame_number):
    """Get a frame by movie_id and frame number.
    Don't log this to prevent blowing up.
    :param: movie_id - the movie_id wanted
    :param: frame_number - provide one of these. Specifies which frame to get
    :return: the URN or None
    """
    for row in dbfile.DBMySQL.csfr(get_dbreader(),
                               """SELECT frame_urn FROM movie_frames WHERE movie_id=%s AND frame_number=%s LIMIT 1""",
                               (movie_id, frame_number), asDicts=True):
        return row['frame_urn']
    return None


def get_frame_data(*, movie_id, frame_number):
    """Get a frame by movie_id and either frame number.
    Don't log this to prevent blowing up.
    :param: movie_id - the movie_id wanted
    :param: frame_number - provide one of these. Specifies which frame to get
    :return: returns the frame data or None
    """
    for row in dbfile.DBMySQL.csfr(get_dbreader(),
                               """SELECT frame_urn FROM movie_frames WHERE movie_id=%s AND frame_number=%s LIMIT 1""",
                               (movie_id, frame_number), asDicts=True):
        return db_object.read_object(row['frame_urn'])
    return None


################################################################
## Trackpoints

def get_movie_trackpoints(*, movie_id, frame_start=None, frame_count=None):
    """Returns a list of trackpoint dictionaries where each dictonary represents a trackpoint.
    :param: frame_start, frame_count - optional
    """
    assert (frame_start is None and frame_count is None) or (frame_start is not None and frame_count is not None)

    if frame_start is None:
        args = [movie_id]
        extra = ''
    else:
        args = [movie_id, frame_start, frame_start+frame_count]
        extra = ' and frame_number >= %s and frame_number < %s '

    return  dbfile.DBMySQL.csfr(get_dbreader(),
                               f"""
                               SELECT frame_number,x,y,label FROM movie_frame_trackpoints WHERE movie_id=%s {extra}
                               """,
                               args, asDicts=True)

def get_movie_frame_metadata(*, movie_id, frame_start, frame_count):
    """Returns a set of dictionaries for each frame in the movie. Each dictionary contains movie_id, frame_number, frame_urn
    :param: frame_start, frame_count -
    """
    return  dbfile.DBMySQL.csfr(get_dbreader(),
                                """
                                SELECT movie_id, frame_number, created_at, mtime, frame_urn
                                FROM movie_frames
                                WHERE movie_id=%s and frame_number >= %s and frame_number < %s
                                """,
                                (movie_id, frame_start, frame_start+frame_count), asDicts=True)

def last_tracked_frame(*, movie_id):
    """Return the last tracked frame_number of the movie"""
    return dbfile.DBMySQL.csfr(get_dbreader(),
                               """SELECT max(frame_number) FROM movie_frame_trackpoints WHERE movie_id=%s
                               """,
                               (movie_id,))[0][0]

def put_frame_trackpoints(*, movie_id:int, frame_number:int, trackpoints:list[dict]):
    """
    :frame_number: the frame to replace. If the frame has existing trackpoints, they are overwritten
    :param: trackpoints - array of dicts where each dict has an x, y and label. Other fields are ignored.
    """
    dbfile.DBMySQL.csfr(get_dbwriter(),
                        """DELETE FROM movie_frame_trackpoints WHERE movie_id=%s and frame_number=%s""",(movie_id,frame_number,))
    vals = []
    for tp in trackpoints:
        if ('x' not in tp) or ('y' not in tp) or ('label') not in tp:
            raise KeyError(f'trackpoints element {tp} missing x, y or label')
        vals.extend([movie_id,frame_number,tp['x'],tp['y'],tp['label']])
    if vals:
        args = ",".join(["(%s,%s,%s,%s,%s)"]*len(trackpoints))
        cmd = f"INSERT INTO movie_frame_trackpoints (movie_id,frame_number,x,y,label) VALUES {args}"
        logging.debug("cmd=%s vals=%s",cmd,vals)
        dbfile.DBMySQL.csfr(get_dbwriter(),cmd,vals)


################################################################

# Don't log this; we run list_movies every time the page is refreshed
def list_movies(*,user_id, movie_id=None, orig_movie=None):
    """Return a list of movies that the user is allowed to access.
    This should be updated so that we can request only a specific movie
    :param: user_id - only list movies visible to user_id (0 for all movies)
    :param: movie_id - if provided, only use this movie
    :param: orig_movie - if provided, only list movies for which the original movie is orig_movie_id
    """
    cmd = """SELECT users.name as name,users.email as email,users.primary_course_id as primary_course_id,
          movies.id as movie_id,title,description,movies.created_at as created_at,
          user_id,course_id,published,deleted,date_uploaded,orig_movie,
          fps,width,height,total_frames,total_bytes
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

    cmd += " ORDER BY movies.id "

    res = dbfile.DBMySQL.csfr(get_dbreader(), cmd, args, asDicts=True)
    return res

################################################################
## Logs
################################################################

def get_logs( *, user_id , start_time = 0, end_time = None, course_id=None,
              course_key=None, movie_id=None, log_user_id=None,
              ipaddr=None, count=LOG_MAX_RECORDS, offset=0, security=True):
    """get log entries (to which the user is entitled) - Implements /api/get-log
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
    # these can be changed by the owner or an admin
    'title': 'update movies set title=%s where id=%s and (@is_owner or @is_admin)',
    'description': 'update movies set description=%s where id=%s and (@is_owner or @is_admin)',
    'status': 'update movies set status=%s where id=%s and (@is_owner or @is_admin)',
    'fps': 'update movies set fps=%s where id=%s and (@is_owner or @is_admin)',
    'width': 'update movies set width=%s where id=%s and (@is_owner or @is_admin)',
    'height': 'update movies set height=%s where id=%s and (@is_owner or @is_admin)',
    'total_frames': 'update movies set total_frames=%s where id=%s and (@is_owner or @is_admin)',
    'total_bytes': 'update movies set total_bytes=%s where id=%s and (@is_owner or @is_admin)',
    'version':'update movies set version=%s where id=%s and (@is_owner or @is_admin)',
    'movie_zipfile_urn':'update movies set movie_zipfile_urn=%s where id=%s and (@is_owner or @is_admin)',

    # the user can delete or undelete movies; the admin can only delete them
    'deleted': 'update movies set deleted=%s where id=%s and (@is_owner or (@is_admin and deleted=0))',

    # the admin can publish or unpublish movies; the user can only unpublish them
    'published': 'update movies set published=%s where id=%s and (@is_admin or (@is_owner and published!=0))',
}


@log
def set_metadata(*, user_id, set_movie_id=None, set_user_id=None, prop, value):
    """We tried doing this in a single statement and it failed
    :param user_id: - user doing the setting. 0 for root
    :param set_movie_id: - if not None, the movie for which we are setting metadata
    :param set_user_id: - if not None, the user for which we are setting metadata
    :param prop - the name of the metadata property being set
    :param value - the value of the metadata property being set

    """
    # First compute @is_owner
    logging.info("set_user_id=%s set_movie_id=%s prop=%s value=%s", set_user_id, set_movie_id, prop, value)
    assert isinstance(user_id, int)
    assert isinstance(set_movie_id, int) or (set_movie_id is None)
    assert isinstance(set_user_id, int) or (set_user_id is None)
    assert isinstance(prop, str)
    assert value is not None

    MAPPER = {0: 'FALSE', 1: 'TRUE'}

    if set_movie_id:
        # We are changing metadata for a movie; make sure that this user is allowed to do so.
        # root is always allowed to do so
        if user_id==0:
            is_owner = "TRUE"
            is_admin = "TRUE"
        else:
            res = dbfile.DBMySQL.csfr(
                get_dbreader(),
                """SELECT %s in (select user_id from movies where id=%s)""", (user_id, set_movie_id))
            # Find out if the user is the owner of the movie
            is_owner = MAPPER[res[0][0]]

            # Find out if the user is an admin of the movie's course
            res = dbfile.DBMySQL.csfr(get_dbreader(),
                                      """
                                      SELECT %s IN (select user_id from admins
                                                    WHERE course_id=(select course_id
                                                    FROM movies WHERE id=%s))
                                      """,
                                      (user_id, set_movie_id))
            is_admin = MAPPER[res[0][0]]
        # Create the command that updates the movie metadata if the user is the owner of the movie or admin
        try:
            cmd   = SET_MOVIE_METADATA[prop].replace( '@is_owner', is_owner).replace('@is_admin', is_admin)
        except KeyError as e:
            logging.error("Cannot set property %s from %s",prop,e)
            raise ValueError('Cannot set property '+prop) from e
        args  = [value, set_movie_id]
        ret   = dbfile.DBMySQL.csfr(get_dbwriter(), cmd, args)
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


################################################################
## Movie Class (in transition)
## A higher-level interface to movies.
################################################################

class Movie():
    """Simple representation of movies that may be stored in SQL database or on S3.
    Not used for creating movies, but can be used for updating them
    More intelligence will move into this class over time.
    """
    __slots__ = ['movie_id', 'sha256', 'mime_type']
    def __init__(self, movie_id, *, user_id=None):
        """
        :param movie_id: - the id of the movie
        :param user_id: - the user_id requesting access. If provided, the user must have access.
        """
        assert isinstance(movie_id,int)
        assert isinstance(user_id,(int,type(None)))
        self.movie_id  = movie_id
        self.mime_type = MIME.MP4
        self.sha256 = None
        if (user_id is not None) and not can_access_movie(user_id=user_id, movie_id=movie_id):
            raise UnauthorizedUser(f"user_id={user_id} movie_id={movie_id}")

    def __repr__(self):
        return f"<Movie {self.movie_id} urn={self.movie_data_urn} sha256={self.sha256}>"

    @property
    def data(self):
        """Return the object data"""
        return get_movie_data(movie_id=self.movie_id)

    @property
    def movie_data_urn(self):
        return movie_data_urn_for_movie_id(self.movie_id)

    @property
    def movie_zipfile_urn(self):
        return movie_zipfile_urn_for_movie_id(self.movie_id)

    @data.setter
    def data(self, movie_data):
        set_movie_data(movie_id=self.movie_id, movie_data=movie_data)

    @property
    def url(self):
        """Return a URL for accessing the data. This is a self-signed URL"""
        return db_object.make_signed_url(urn=self.movie_data_urn)

    @property
    def zipfile_url(self):
        """Return a URL for accessing the zipfile. This is a self-signed URL"""
        return db_object.make_signed_url(urn=self.movie_zipfile_urn)

    @property
    def metadata(self):
        """Returns a dictionary of the movie metadata"""
        res = get_movie_metadata(user_id=0, movie_id = self.movie_id)
        logging.debug("metadata=%s",res[0])
        return res[0]

    @property
    def version(self):
        return self.metadata['version']

    @version.setter
    def version(self, value):
        set_metadata(user_id = 0, set_movie_id=self.movie_id, prop='version', value=value)
