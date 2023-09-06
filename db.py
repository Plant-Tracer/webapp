# Database code

"""Database code for Plant Tracer"""

import functools
import os
import base64
import uuid
import logging

from jinja2.nativetypes import NativeEnvironment
from validate_email_address import validate_email

from paths import DBREADER_BASH_FILE,DBWRITER_BASH_FILE,TEMPLATE_DIR
from lib.ctools import dbfile


import mailer

EMAIL_TEMPLATE_FNAME = 'email.txt'


class InvalidEmail(RuntimeError):
    """Exception thrown in email is invalid"""

class InvalidAPI_Key(RuntimeError):
    """ API Key is invalid """

class InvalidCourse_Key(RuntimeError):
    """ API Key is invalid """



@functools.cache
def get_dbreader():
    """Get the dbreader authentication info from the DBREADER_BASH_FILE if it exists. Variables there are
    shadowed by environment variables MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE.
    If the file doesn't exist, send in None, hoping that the environment variables exist."""
    fname = DBREADER_BASH_FILE if os.path.exists(DBREADER_BASH_FILE) else None
    return dbfile.DBMySQLAuth.FromBashEnvFile( fname )

@functools.cache
def get_dbwriter():
    """Get the dbwriter authentication info from the DBWRITER_BASH_FILE if it exists. Variables there are
    shadowed by environment variables MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE.
    If the file doesn't exist, send in None, hoping that the environment variables exist."""
    fname = DBWRITER_BASH_FILE if os.path.exists(DBWRITER_BASH_FILE) else None
    return dbfile.DBMySQLAuth.FromBashEnvFile( fname )


################################################################
##  USER MANAGEMENT
############################################
def validate_api_key( api_key ):
    """Validate API key. return User dictionary or None if key is not valid"""
    res = dbfile.DBMySQL.csfr( get_dbreader(),
                               "SELECT * from api_keys left join users on user_id=users.id where api_key=%s and enabled=1 LIMIT 1",
                               (api_key, ), asDicts=True)

    if len(res)>0:
        dbfile.DBMySQL.csfr( get_dbwriter(),
                             """UPDATE api_keys
                             SET last_used_at=now(),
                             first_used_at=if(first_used_at is null,now(),first_used_at),
                             use_count=use_count+1
                             WHERE api_key=%s""",
                             (api_key,))
        return res[0]
    return {}

##
def register_email(email, course_key, name):
    """Register email for a given course
    :param: email - user email
    :param: course_key - the key
    :return: the number of users registered
    """

    CHECK_MX = False            # True doesn't work
    if not validate_email(email, check_mx=CHECK_MX):
        raise InvalidEmail( email )
    res = dbfile.DBMySQL.csfr( get_dbreader(), "SELECT id FROM courses WHERE course_key=%s",(course_key,))
    if (not res) or (len(res)!=1) :
        raise InvalidCourse_Key( course_key )

    course_id = res[0][0]
    return dbfile.DBMySQL.csfr( get_dbwriter(),
                         """INSERT INTO users (email, primary_course_id, name) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE email=%s""",
                         ( email, course_id, name, email ))

def rename_user(user_id, old_email, new_email):
    """Changes a user's email. Requires a correct old_email"""
    dbfile.DBMySQL.csfr( get_dbwriter(), "UPDATE users SET email=%s where id=%s AND email=%s",
                         ( old_email, user_id, new_email))

def delete_user( email ):
    """Delete a user. A course cannot be deleted if it has any users. A user cannot be deleted if it has any movies.
    Also deletes the user from any courses where they may be an admin.
    """
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE FROM admins WHERE user_id in (select id from users where email=%s)", (email,))
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE FROM users WHERE email=%s", (email,))


def lookup_user( *, email ):
    try:
        return dbfile.DBMySQL.csfr( get_dbreader(), "select * from users where email=%s",(email,), asDicts=True)[0]
    except IndexError:
        return {}

def new_api_key( email ):
    """Create a new api_key for an email that is registered
    :param: email - the email
    :return: api_key - the api_key
    """
    api_key = str(uuid.uuid4()).replace('-','')
    dbfile.DBMySQL.csfr( get_dbwriter(),
                         """INSERT INTO api_keys (user_id, api_key)
                            VALUES ((select id from users where email=%s and enabled=1), %s)""",
                         (email, api_key))
    return api_key

def delete_api_key(api_key):
    """Deletes an api_key
    :param: api_key - the api_key
    :return: the number of keys deleted
    """
    if len(api_key) < 10:
        raise InvalidAPI_Key(api_key)
    return dbfile.DBMySQL.csfr( get_dbwriter(),
                                """DELETE FROM api_keys WHERE api_key=%s""",
                                (api_key,))

def send_links( email, planttracer_endpoint ):
    """Creates a new api key and sends it to email. Won't resend if it has been sent in MIN_SEND_INTERVAL"""
    PROJECT_EMAIL = 'admin@planttracer.com'

    logging.warning("TK: Insert delay for MIN_SEND_INTERVAL")

    TO_ADDRS = [ email ]
    with open(os.path.join( TEMPLATE_DIR, EMAIL_TEMPLATE_FNAME ),"r") as f:
        msg_env = NativeEnvironment().from_string( f.read() )
    msg = msg_env.render( to_addrs   = ",".join([email]),
                          from_addr  = PROJECT_EMAIL,
                          planttracer_endpoint  = planttracer_endpoint,
                          api_key    = new_api_key( email ))

    DRY_RUN = False
    smtp_config = mailer.smtp_config_from_environ()
    #smtp_config['SMTP_DEBUG'] = False
    mailer.send_message( from_addr   = PROJECT_EMAIL,
                         to_addrs    = TO_ADDRS,
                         smtp_config = smtp_config,
                         dry_run     = DRY_RUN,
                         msg         = msg
                        )


################################################################
## Course Management
################################################################

def lookup_course( *, course_id ):
    try:
        return dbfile.DBMySQL.csfr( get_dbreader(), "select * from courses where id=%s",(course_id,), asDicts=True)[0]
    except IndexError:
        return {}

def create_course(course_key, course_name, max_enrollment, course_section=None):
    """Create a new course
    :return: course_id of the new course
    """
    return dbfile.DBMySQL.csfr( get_dbwriter(), "INSERT into courses (course_key, course_name, max_enrollment, course_section) values (%s,%s,%s,%s)",
                                (course_key, course_name, max_enrollment, course_section))

def delete_course(course_key):
    """Delete a course.
    :return: number of courses deleted.
    """
    return dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from courses where course_key=%s", (course_key,))

def make_course_admin( email, *, course_key=None, course_id=None ):
    if course_id:
        dbfile.DBMySQL.csfr( get_dbwriter(), "INSERT into admins (course_id, user_id) values (%s, (select id from users where email=%s))",
                             (course_id, email))
    if course_key:
        dbfile.DBMySQL.csfr( get_dbwriter(), "INSERT into admins (course_id, user_id) values ((select id from courses where course_key=%s), (select id from users where email=%s))",
                             (course_key, email))

def remove_course_admin( email, *, course_key=None, course_id=None ):
    if course_id:
        dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE FROM admins WHERE course_id=%s and user_id in (select id from users where email=%s)",
                             (course_id, email))
    if course_key:
        dbfile.DBMySQL.csfr( get_dbwriter(),
                             "DELETE FROM admins where course_id in (SELECT id FROM courses WHERE course_key=%s) "
                             "AND user_id IN (SELECT id FROM users WHERE email=%s)",
                             (course_key, email))


def check_course_admin( user_id, course_id ):
    """Return True if user_id is an admin in course_id"""
    res = dbfile.DBMySQL.csfr( get_dbreader(), "SELECT * FROM admins WHERE user_id=%s AND course_id=%s LIMIT 1",
                               (user_id,course_id))
    return len(res)==1


def validate_course_key( course_key ):
    res = dbfile.DBMySQL.csfr( get_dbreader(),
                              """SELECT course_key FROM courses WHERE course_key=%s LIMIT 1""", (course_key,))
    return len(res)==1 and res[0][0]==course_key

def remaining_course_registrations( course_key ):
    res = dbfile.DBMySQL.csfr( get_dbreader(),
                              """SELECT max_enrollment - (SELECT COUNT(*) FROM users WHERE primary_course_id=(SELECT id FROM courses WHERE course_key=%s))
                                 FROM courses WHERE course_key=%s""",
                              ( course_key,course_key))
    try:
        return int(res[0][0])
    except (IndexError,ValueError):
        return 0



################################################################
## Movie Management
################################################################


def get_movie_metadata( user_id, movie_id ):
    cmd = """SELECT * from movies WHERE
                (user_id=%s OR
                 course_id=(select primary_course_id from users where id=%s) OR
                 course_id in (select course_id from admins where user_id=%s))"""
    params = [user_id, user_id, user_id]
    if movie_id:
        cmd += " AND movie_id=%s"
        params.append(movie_id)
    return dbfile.DBMySQL.csfr( get_dbreader(), cmd, params, asDicts=True)

def can_access_movie( user_id, movie_id ):
    """Return if the user is allowed to access the movie"""
    res = dbfile.DBMySQL.csfr(
        get_dbreader(),
        """select count(*) from movies WHERE id=%s AND
        (user_id=%s OR
        course_id=(select primary_course_id from users where id=%s) OR
        course_id in (select course_id from admins where user_id=%s))""",
        (movie_id, user_id, user_id, user_id))
    return res[0][0]>0

def purge_movie(  movie_id ):
    """Actually delete a movie and all its frames"""
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from movie_frames where movie_id=%s", (movie_id,))
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from movie_data where movie_id=%s", (movie_id,))
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from movies where id=%s", (movie_id,))

def delete_movie( movie_id, delete=1 ):
    """Set a movie's deleted bit to be true"""
    dbfile.DBMySQL.csfr( get_dbwriter(), "UPDATE movies SET deleted=%s where id=%s", (delete, movie_id,))

def create_new_movie(user_id, *, title=None, description=None, movie_data=None):
    res = dbfile.DBMySQL.csfr( get_dbreader(),"select primary_course_id from users where id=%s",(user_id,))
    if not res or len(res)!=1:
        logging.error("len(res)=%s",len(res))
        logging.error("res=%s",res)
        raise RuntimeError(f"user_id={user_id} len(res)={len(res)} res={res}")
    primary_course_id = res[0][0]
    movie_id = dbfile.DBMySQL.csfr( get_dbwriter(),
                                    """INSERT INTO movies (title,description,user_id,course_id) VALUES (%s,%s,%s,%s)
                                    """,
                                    (title, description, user_id, primary_course_id ))
    if movie_data:
        dbfile.DBMySQL.csfr( get_dbwriter(),
                             "INSERT INTO movie_data (movie_id, movie_data) values (%s,%s)",
                             (movie_id, movie_data))
    return movie_id

def create_new_frame( movie_id, frame_msec, frame_base64_data ):
    frame_data = base64.b64decode( frame_base64_data )
    frame_id = dbfile.DBMySQL.csfr( get_dbwriter(),
                                    """INSERT INTO movie_frames (movie_id, frame_msec, frame_data)
                                       VALUES (%s,%s,%s)
                                       ON DUPLICATE KEY UPDATE frame_msec=%s, frame_data=%s""",
                                        ( movie_id, frame_msec, frame_base64_data,
                                          frame_data, frame_msec))
    return frame_id


def list_movies( user_id ):
    """Return a list of movies that the user is allowed to access.
    This should be updated so that we can request only a specific movie
    """
    return dbfile.DBMySQL.csfr( get_dbreader(),
                                """SELECT * from movies LEFT JOIN users on movies.user_id = users.id
                                WHERE user_id=%s
                                OR
                                (course_id = (SELECT course_id FROM users WHERE id=%s) AND published>0 AND deleted=0)
                                OR
                                (course_id in (SELECT course_id FROM admins WHERE user_id=%s))""",
                                (user_id, user_id, user_id), asDicts=True)

# set movie metadata privileges array:
# columns indicate WHAT is being set, WHO can set it, and HOW to set it
SET_MOVIE_METADATA = {
    # title can be changed by the owner or the admin
    'title':'update movies set title=%s where id=%s and (@is_owner or @is_admin)',

    # description can be changed by owner or admin
    'description':'update movies set description=%s where id=%s and (@is_owner or @is_admin)',

    # the user can delete or undelete movies; the admin can only delete them
    'deleted':'update movies set deleted=%s where id=%s and (@is_owner or (@is_admin and deleted=0))',

    # the admin can publish or unpublish movies; the user can only unpublish them
    'published':'update movies set published=%s where id=%s and (@is_admin or (@is_owner and published!=0))',
}

def set_metadata(*, user_id, set_movie_id=None, set_user_id=None, property, value):
    """We tried doing this in a single statement and it failed"""
    # First compute @is_owner

    logging.warning("set_user_id=%s set_movie_id=%s property=%s value=%s",set_user_id, set_movie_id,property,value)
    assert isinstance(user_id,int)
    assert isinstance(set_movie_id,int) or (set_movie_id is None)
    assert isinstance(set_user_id,int) or (set_user_id is None)
    assert isinstance(property,str)
    assert value is not None

    MAPPER = {0:'FALSE',
              1:'TRUE'}

    if set_movie_id:
        res = dbfile.DBMySQL.csfr( get_dbreader(), "SELECT %s in (select user_id from movies where id=%s)", (user_id, set_movie_id))
        is_owner = MAPPER[res[0][0]]

        res = dbfile.DBMySQL.csfr( get_dbreader(), "SELECT %s in (select user_id from admins where course_id=(select course_id from movies where id=%s))",
                                   (user_id, set_movie_id))
        is_admin = MAPPER[res[0][0]]
        logging.warning("user_id=%s set_movie_id=%s property=%s value=%s is_owner=%s is_admin=%s",user_id, set_movie_id, property, value, is_owner,is_admin)

        cmd = SET_MOVIE_METADATA[property].replace('@is_owner',is_owner).replace('@is_admin',is_admin)
        args = [ value, set_movie_id ]

        ret = dbfile.DBMySQL.csfr( get_dbwriter(), cmd, args)
        return ret

    # Currently, users can only set their own data
    if set_user_id:
        if user_id == set_user_id:
            property = property.lower()
            if property in ['name','email']:
                ret = dbfile.DBMySQL.csfr( get_dbwriter(),
                                           f"UPDATE users set {property}=%s where id=%s",
                                           (value, user_id))
                return ret
