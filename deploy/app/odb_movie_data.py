"""
Routines for reading and writing movie data.
Requires requests.
Moved to a separate python file so that it doesn't need to be loaded for python camera, in the interest of keeping the lambda small.
"""

#pylint: disable=too-many-lines
import logging
import time
import urllib
import urllib.parse

import requests
from botocore.exceptions import ClientError,ParamValidationError

from .s3_presigned import s3_client,make_urn,make_object_name
from .constants import C
from .odb import DDBO,InvalidMovie_Id,is_movie_id,VERSION,course_id_for_movie_id,MOVIE_DATA_URN,DATE_UPLOADED,TOTAL_BYTES,TOTAL_FRAMES,FRAME_URN,DELETED

logger = logging.getLogger(__name__)

def read_object(urn):
    o = urllib.parse.urlparse(urn)
    logging.debug("urn=%s o=%s",urn,o)
    if o.scheme == C.SCHEME_S3 :
        # We are getting the object, so we do not need a presigned url
        try:
            return s3_client().get_object(Bucket=o.netloc, Key=o.path[1:])["Body"].read()
        except ClientError as ex:
            logging.info("ClientError: %s  Bucket=%s  Key=%s",ex,o.netloc,o.path[1:])
            return None
    elif o.scheme in ['http','https']:
        r = requests.get(urn, timeout=C.DEFAULT_GET_TIMEOUT)
        return r.content
    else:
        raise ValueError("Unknown schema: "+urn)

def write_object(urn, object_data):
    logging.info("write_object(%s,len=%s)",urn,len(object_data))
    logger.info("write_object(%s,len=%s)",urn,len(object_data))
    assert "s3://s3://" not in urn
    o = urllib.parse.urlparse(urn)
    if o.scheme== C.SCHEME_S3:
        try:
            s3_client().put_object(Bucket=o.netloc, Key=o.path[1:], Body=object_data)
            return
        except ParamValidationError as e:
            logger.error("ParamValidationError. urn=%s o=%s  e=%s",urn,o,e)
            raise
        except ClientError as e:
            error_code = e.response.get('Error',{}).get('Code','')
            if error_code == 'InvalidBucketName':
                logger.error("*** Bucket '%s' does not exist or is invalid",o.netloc)
            else:
                logging.error("*** Unexpected ClientError: %s",error_code)
            raise
    raise ValueError(f"Cannot write object urn={urn} len={len(object_data)}")

def delete_object(urn):
    logging.debug("delete_object(%s)",urn)
    o = urllib.parse.urlparse(urn)
    if o.scheme== C.SCHEME_S3:
        s3_client().delete_object(Bucket=o.netloc, Key=o.path[1:])
    else:
        raise ValueError(f"Cannot delete object urn={urn}")





########################
### Movie Management ###
########################

def get_movie_data(*, movie_id, zipfile=False, get_urn=False):
    """Returns the movie contents for a movie_id.
    If urn==True, just return the urn
    """
    movie = DDBO().get_movie(movie_id)
    try:
        if zipfile:
            urn = movie['movie_zipfile_urn']
        else:
            urn = movie['movie_data_urn']
    except TypeError as e:
        raise InvalidMovie_Id(movie_id) from e

    if get_urn:
        return urn

    if urn:
        return read_object(urn)
    raise InvalidMovie_Id()



def set_movie_data(*,movie_id, movie_data):
    """If we are setting the movie data, be sure that any old data (frames, zipfile, stored objects) are gone.
    increments version.
    """
    assert is_movie_id(movie_id)
    ddbo = DDBO()
    movie = ddbo.get_movie(movie_id)

    logging.debug("got movie=%s version=%s",movie,movie[VERSION])
    purge_movie_data(movie_id=movie_id)
    purge_movie_frames( movie_id=movie_id )
    purge_movie_zipfile( movie_id=movie_id )
    oname = make_object_name( course_id = course_id_for_movie_id( movie_id ),
                                        movie_id = movie_id,
                                        ext=C.MOVIE_EXTENSION)
    movie_data_urn        = make_urn( object_name = oname)

    write_object(movie_data_urn, movie_data)
    ddbo.update_table(ddbo.movies, movie_id, {MOVIE_DATA_URN:movie_data_urn,
                                              DATE_UPLOADED:int(time.time()),
                                              TOTAL_BYTES:len(movie_data),
                                              TOTAL_FRAMES:None,
                                              VERSION:movie[VERSION]+1 })


################################################################
## Deleting

def purge_movie_data(*,movie_id):
    """Delete the movie data associated with a movie"""
    logging.debug("purge_movie_data movie_id=%s",movie_id)
    ddbo = DDBO()
    urn = ddbo.get_movie(movie_id).get(MOVIE_DATA_URN,None)
    if urn:
        delete_object( urn )
        ddbo.update_table(ddbo.movies,movie_id, {MOVIE_DATA_URN:None})

def purge_movie_frames(*,movie_id, frame_numbers=None):
    """Delete the frames and zipfile associated with a movie.
    :param frames: If None, delete them all
    """

    logging.debug("purge_movie_frames movie_id=%s",movie_id)
    ddbo = DDBO()
    if frame_numbers is None:
        frames = ddbo.get_frames( movie_id )
    else:
        frames = [ddbo.get_movie_frame(movie_id, frame_number) for frame_number in frame_numbers]

    for frame in frames:
        assert isinstance(frame,dict)
        frame_urn = frame.get(FRAME_URN,None)
        if frame_urn is not None:
            delete_object(frame_urn)
    ddbo.delete_movie_frames( frames )


def purge_movie_zipfile(*,movie_id):
    """Delete the frames associated with a movie."""
    logging.debug("purge_movie_data movie_id=%s",movie_id)
    ddbo = DDBO()
    movie = ddbo.get_movie(movie_id)
    if movie.get('movie_zipfile_urn',None) is not None:
        delete_object(movie['movie_zipfile_urn'])
        ddbo.update_table(ddbo.movies, movie_id, {'movie_zipfile_urn':None})

def purge_movie(*,movie_id):
    """Actually delete a movie and all its frames"""
    purge_movie_data(movie_id=movie_id)
    purge_movie_frames( movie_id=movie_id )
    purge_movie_zipfile( movie_id=movie_id )


def delete_movie(*,movie_id, delete=1):
    """Set a movie's deleted bit to be true"""
    assert delete in (0,1)
    ddbo = DDBO()
    ddbo.update_table(ddbo.movies,movie_id, {DELETED:delete})


# New implementation that writes to s3
# Possible -  move jpeg compression here? and do not write out the frame if it was already written out?
def create_new_movie_frame(*, movie_id, frame_number, frame_data=None):
    """Determine the URN for a movie_id/frame_number.
    if frame_data is provided, save it as an object in s3 (Otherwise just return the frame_urn)
    Store frame info in the movie_frames table.
    returns frame_urn
    """
    logging.debug("create_new_movie_frame(movie_id=%s, frame_number=%s, type(frame_data)=%s",movie_id, frame_number, type(frame_data))
    course_id = course_id_for_movie_id(movie_id)
    if frame_data is not None:
        # upload the frame to the store and make a frame_urn
        object_name = make_object_name(course_id=course_id,
                                            movie_id=movie_id,
                                            frame_number = frame_number,
                                            ext=C.JPEG_EXTENSION)
        frame_urn = make_urn( object_name = object_name)
        write_object(frame_urn, frame_data)
    else:
        frame_urn = None

    DDBO().put_movie_frame({"movie_id":movie_id,
                            "frame_number":frame_number,
                            "frame_urn":frame_urn})
    return frame_urn


def get_frame_data(*, movie_id, frame_number):
    """Get a frame by movie_id and either frame number.
    Don't log this to prevent blowing up.
    :param: movie_id - the movie_id wanted
    :param: frame_number - provide one of these. Specifies which frame to get
    :return: returns the frame data or None
    """
    logging.warning("We should only get the value that we need")
    frame_urn = DDBO().get_movie_frame(movie_id, frame_number)[FRAME_URN]
    return read_object(frame_urn)
