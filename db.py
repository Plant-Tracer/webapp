# Database code

"""Database code for Plant Tracer"""

import functools
import os
import base64
import uuid
import logging

from validate_email_address import validate_email

from paths import DBREADER_BASH_FILE,DBWRITER_BASH_FILE
from lib.ctools import dbfile


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
##
def validate_api_key( api_key ):
    """Validate API key. return User dictionary or None if key is not valid"""
    res = dbfile.DBMySQL.csfr( get_dbwriter(),
                               "SELECT * from api_keys left join users on user_id=users.id where api_key=%s",
                               (api_key, ), asDicts=True)
    return res[0] if res else {}



################################################################
## database utility functions

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

##
def register_email(email, course_key):
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
                         """INSERT INTO users (email, primary_course_id) VALUES (%s, %s) ON DUPLICATE KEY UPDATE email=%s""",
                         ( email, course_id, email ))

def rename_user(user_id, old_email, new_email):
    """Changes a user's email. Requires a correct old_email"""
    dbfile.DBMySQL.csfr( get_dbwriter(), "UPDATE users SET email=%s where id=%s AND email=%s",
                         ( old_email, user_id, new_email))

def delete_user( email ):
    """Delete a user. A course cannot be deleted if it has any users. A user cannot be deleted if it has any movies"""
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE FROM users WHERE email=%s", (email,))

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

def new_api_key( email ):
    """Create a new api_key for an email that is registered
    :param: email - the email
    :return: api_key - the api_key
    """
    api_key = str(uuid.uuid4()).replace('-','')
    dbfile.DBMySQL.csfr( get_dbwriter(),
                         """INSERT INTO api_keys (user_id, api_key)
                            VALUES ((select id from users where email=%s), %s)""",
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

def create_new_movie(user_id, title, description, movie_base64_data):
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
    if movie_base64_data:
        dbfile.DBMySQL.csfr( get_dbwriter(),
                             "INSERT INTO movie_data (movie_id, movie_data) values (%s,%s)",
                             (movie_id, base64.b64decode( movie_base64_data )))
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




def send_links(email):
    """Send the links to the email address if they haven't been sent for MIN_SEND_INTERVAL"""
    raise RuntimeError("implement send_links")

def validate_course_key( course_key ):
    res = dbfile.DBMySQL.csfr( get_dbreader(),
                              """SELECT course_key FROM courses WHERE course_key=%s LIMIT 1""", (course_key,))
    return len(res)==1 and res[0][0]==course_key

def remaining_course_registrations( course_key ):
    res = dbfile.DBMySQL.csfr( get_dbreader(),
                              """SELECT max_enrollment - (SELECT COUNT(*) FROM users WHERE course_id=(SELECT id FROM courses WHERE course_key=%s))
                                 FROM courses WHERE course_key=%s""",
                              ( course_key,course_key))
    try:
        return int(res[0][0])
    except (IndexError,ValueError):
        return 0

def list_movies( user_id ):
    """Return a list of movies that the user is allowed to access."""
    return dbfile.DBMySQL.csfr( get_dbreader(),
                                """SELECT * from movies
                                WHERE user_id=%s
                                OR
                                (course_id = (SELECT course_id FROM users WHERE id=%s) AND published>0 AND deleted=0)
                                OR
                                (course_id in (SELECT course_id FROM admins WHERE user_id=%s))""",
                                (user_id, user_id, user_id), asDicts=True)
