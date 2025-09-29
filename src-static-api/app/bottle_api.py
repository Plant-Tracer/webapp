"""
API

TODO - all get_user_id() should be replaced with get_user_dict() and then the userdict should be passed around so that we don't need another query.


"""
import json
import logging
import sys
import smtplib
import tempfile
import base64
import io
import csv
import os
import zipfile
from collections import defaultdict
from zipfile import ZipFile

from flask import Blueprint, request, make_response, redirect, current_app, jsonify
from validate_email_address import validate_email

from . import odb
from . import db_object
from . import mailer
from . import tracker
from .apikey import get_user_api_key,get_user_dict,in_demo_mode
from .auth import AuthError,EmailNotInDatabase
from .constants import C,E,POST,GET_POST,__version__
from .odb import InvalidAPI_Key,InvalidMovie_Id,USER_ID,MOVIE_ID,COURSE_ID,LAST_FRAME_TRACKED,DDBO


api_bp = Blueprint('api', __name__)
logger = logging.getLogger(__name__)


### Set VALIDATE_FRAMES to True to force /api/get-frame to validate that each frame
### exists in S3 before the URN is returned.

VALIDATE_FRAMES=True

class InvalidFrameNumber(Exception):
    """Invalid Frame Number Exception"""


################################################################
### Handle invalid apikey exceptions
@api_bp.errorhandler(InvalidAPI_Key)
def invalid_api_key(ex):
    logging.info("invalid_api_key(%s)",ex)
    return E.INVALID_API_KEY, 403


################################################################
# define get(), which gets a variable from either the forms request or the query string
def get(key, default=None):
    logging.debug("request.values=%s",request.values)
    return request.values.get(key, default)

def get_movie_id():
    """Note that movie_id's are no longer integers..."""
    ret = get(MOVIE_ID)
    if not odb.is_movie_id( ret ):
        raise InvalidMovie_Id( ret )
    return ret

def get_course_id():
    """Note that course_id's are no longer integers. They can even have spaces in them!"""
    return get(COURSE_ID)

def get_json(key):
    try:
        return json.loads(request.values.get(key))
    except (TypeError,ValueError,json.decoder.JSONDecodeError):
        return None

def get_int(key, default=None):
    logging.debug("get_int key=%s get(key)=%s",key,get(key))
    try:
        return int(get(key))
    except (TypeError,ValueError):
        return default

def get_float(key, default=None):
    try:
        return float(get(key))
    except (TypeError,ValueError):
        return default

def get_bool(key, default=None):
    v = get(key)
    if v is None:
        return default
    try:
        return v[0:1] in 'yYtT1'
    except (TypeError,ValueError):
        return default

def get_user_id(allow_demo=True):
    """Returns the user_id of the currently logged in user, or throws a response.
    if allow_demo==False, then do not allow the user to be a demo user
    """
    if in_demo_mode() and not allow_demo:
        logging.info("demo mode blocks requested action.")
        raise AuthError('demo accounts not allowed to execute requested action')
    userdict = get_user_dict()
    return userdict['user_id']


################################################################
# /api URLs
################################################################

@api_bp.route('/check-api_key', methods=GET_POST)
def api_check_api_key():
    """API to check the user key and, if valid, return usedict or returns an error.
    validate_api_key() will raise InvalidAPI_Key() for an invalid API key that will be handled above.
    """
    return jsonify({'error': False, 'userinfo' : odb.validate_api_key(get_user_api_key())})


@api_bp.route('/get-logs', methods=POST)
def api_get_logs():
    """Get logs and return in JSON. The database function does all of the security checks, but we need to have a valid user."""
    kwargs = {}
    for kw in ['start_time','end_time','course_id','course_key',
               'movie_id','log_user_id','ipaddr','count','offset']:
        val = request.values.get(kw,None)
        if val:
            kwargs[kw] = val

    logs    = odb.get_logs(user_id=get_user_id(),**kwargs)
    return {'error':False, 'logs': logs}

@api_bp.route('/register', methods=GET_POST)
def api_register():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.values.get('email')
    planttracer_endpoint = request.values.get('planttracer_endpoint')
    if not validate_email(email, check_mx=False):
        logging.info("email not valid: %s", email)
        return E.INVALID_EMAIL
    course_key = request.values.get('course_key').strip()
    if not odb.validate_course_key(course_key=course_key):
        return E.INVALID_COURSE_KEY
    if odb.remaining_course_registrations(course_key=course_key) < 1:
        return E.NO_REMAINING_REGISTRATIONS
    user_name = request.values.get('name')
    user = odb.register_email(email=email, course_key=course_key, user_name=user_name)
    user_id = user[USER_ID]
    new_api_key = odb.make_new_api_key(email=email)
    if not new_api_key:
        logging.info("email not in database: %s",email)
        return E.INVALID_EMAIL
    link_html = f"<p/><p>You can also log in by clicking this link: <a href='/list?api_key={new_api_key}'>login</a></p>"
    try:
        mailer.send_links(email=email, planttracer_endpoint=planttracer_endpoint, new_api_key=new_api_key)
        ret = {'error': False, 'message': 'Registration key sent to '+email+link_html, 'user_id':user_id}
    except mailer.InvalidMailerConfiguration:
        logging.error("Mailer reports Mailer not properly configured.")
        ret =  {'error':True, 'message':'Mailer not properly configured (InvalidMailerConfiguration).'+link_html}
    except mailer.NoMailerConfiguration:
        logging.error("Mailer reports no mailer configured.")
        ret =  {'error':True, 'message':'Mailer not properly configured (NoMailerConfiguration).'+link_html}
    except smtplib.SMTPAuthenticationError:
        logging.error("Mailer reports smtplib.SMTPAuthenticationError.")
        ret = {'error':True, 'message':'Mailer reports smtplib.SMTPAuthenticationError.'+link_html}
    return ret

def send_link(*, email, planttracer_endpoint):
    new_api_key = odb.make_new_api_key(email=email)
    if not new_api_key:
        logging.info("email not in database: %s",email)
        raise EmailNotInDatabase(email)
    mailer.send_links(email=email, planttracer_endpoint=planttracer_endpoint, new_api_key=new_api_key)


@api_bp.route('/resend-link', methods=GET_POST)
def api_send_link():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.values.get('email')
    planttracer_endpoint = request.values.get('planttracer_endpoint')
    logging.info("resend-link email=%s planttracer_endpoint=%s",email,planttracer_endpoint)
    if not validate_email(email, check_mx=C.CHECK_MX):
        logging.info("email not valid: %s", email)
        return E.INVALID_EMAIL
    try:
        send_link(email=email, planttracer_endpoint=planttracer_endpoint)
    except EmailNotInDatabase:
        return E.INVALID_EMAIL
    except mailer.NoMailerConfiguration:
        logging.error("no mailer configuration")
        return E.NO_MAILER_CONFIGURATION
    except mailer.InvalidMailerConfiguration as e:
        logging.error("invalid mailer configuration: %s type(e)=%s",e,type(e))
        return E.INVALID_MAILER_CONFIGURATION
    return {'error': False, 'message': 'If you have an account, a link was sent. If you do not receive a link within 60 seconds, you may need to <a href="/register">register</a> your email address.'}

#pylint: disable=too-many-return-statements
@api_bp.route('/bulk-register', methods=POST)
def api_bulk_register():
    """Allow an admin to register people in the class, increasing the class size as necessary to do so."""

    course_id = get_course_id()
    user_id   = get_user_id()
    if not odb.check_course_admin(course_id = course_id, user_id=user_id):
        return E.INVALID_COURSE_ACCESS

    planttracer_endpoint = request.values.get('planttracer_endpoint') # for emails
    email_addresses      = request.values.get('email-addresses').replace(","," ").replace(";"," ").replace(" ","\n").split("\n")
    user_ids             = []
    try:
        for email in email_addresses:
            email = email.strip()
            if not validate_email(email, check_mx=C.CHECK_MX):
                return E.INVALID_EMAIL
            user = odb.register_email(email=email, course_id=course_id, user_name="")
            send_link(email=email, planttracer_endpoint=planttracer_endpoint)
            user_ids.append(user[USER_ID])
    except EmailNotInDatabase:
        return E.INVALID_EMAIL
    except mailer.NoMailerConfiguration:
        logging.error("no mailer configuration")
        return E.NO_MAILER_CONFIGURATION
    except mailer.InvalidMailerConfiguration as e:
        logging.error("invalid mailer configuration: %s",e)
        return E.INVALID_MAILER_CONFIGURATION
    return {'error':False, 'message':f'Registered {len(email_addresses)} email addresses', 'user_ids':user_ids}

################################################################
##
## Object API
MIME_MAP = {'.jpg':'image/jpeg',
            '.jpeg':'image/jpeg',
            '.mov':'video/mp4',
            '.mp4':'video/mp4',
            '.zip':'application/zip'
            }



################################################################
##
# Movie APIs. All of these need to only be POST to avoid an api_key from being written into the logfile
##

@api_bp.route('/new-movie', methods=POST)
def api_new_movie():
    """Creates a new movie for which we can upload frame-by-frame or all at once.
    Moving can appear here as a file or as a base64 encoded data.
    If no movie is provided, we return a presigned URL that can be used to post the movie to S3 or to the
    /api/upload-movie API (below).

    :param api_key: the user's api_key
    :param title: The movie's title
    :param description: The movie's description
    :param movie_data_sha256: The movie's SHA256. The movie itself is uploaded with a presigned post that is reqturned.
    :return: dict['movie_id'] - The movie_id that is allocated
             dict['presigned_post'] - the post to use for uploading the movie. Sends it directly to S3, or to the handler below.
    """
    # pylint: disable=unsupported-membership-test
    logging.info("api_new_movie")
    user_id    = get_user_id(allow_demo=False)    # require a valid user_id
    user       = odb.get_user(user_id)
    movie_data_sha256 = get('movie_data_sha256')

    if (movie_data_sha256 is None) or (len(movie_data_sha256)!=64):
        return {'error':True,'message':'Movie SHA256 not provided or is invalid. Uploaded failed.'}

    ret = {'error':False}

    # This is where the movie_id is assigned
    ret[ MOVIE_ID ] = odb.create_new_movie(user_id=user_id,
                                           course_id=user['primary_course_id'],
                                           title=request.values.get('title'),
                                           description=request.values.get('description') )

    # Get the object name and create the upload URL
    object_name= db_object.object_name( course_id = odb.course_id_for_movie_id( ret[ MOVIE_ID ]),
                                        movie_id = ret[ MOVIE_ID ],
                                        ext=C.MOVIE_EXTENSION)
    movie_data_urn        = db_object.make_urn( object_name = object_name)
    odb.set_movie_data_urn(movie_id=ret[ MOVIE_ID ], movie_data_urn=movie_data_urn)
    ret['presigned_post'] = db_object.make_presigned_post(urn=movie_data_urn,
                                                          mime_type='video/mp4',
                                                          sha256=movie_data_sha256)
    return ret

@api_bp.route('/get-movie-data', methods=GET_POST)
def api_get_movie_data():
    """
    Gets the user the movie.
    :param api_key:   authentication
    :param movie_id:  movie
    :param format:    if 'zip' - return as as a zipfile
    :param redirect_inline: - if True and we are redirecting, return "#REDIRECT url" (for testing)
    :return:  IF MOVIE IS IN S3 - Redirect to a signed URL.
              IF MOVIE IS IN DB - The raw movie data as a movie.
    """
    movie_id = get_movie_id()
    if not odb.can_access_movie(user_id = get_user_id(), movie_id=movie_id):
        return make_response(E.INVALID_MOVIE_ACCESS, 404)

    data_urn = odb.get_movie_data(movie_id=movie_id,
                                  zipfile = get('format')=='zip',
                                  get_urn = True)

    # This is used for testing redirect response in the test program
    if get_bool('redirect_inline'):
        return "#REDIRECT " + data_urn

    # Otherwise, redirect to the signed url
    return redirect(db_object.make_signed_url(urn=data_urn))


def set_movie_metadata(*,user_id=odb.ROOT_USER_ID, set_movie_id,movie_metadata):
    """Update the movie metadata."""
    for prop in ['fps','width','height','total_frames','total_bytes']:
        if prop in movie_metadata:
            logger.warning("Setting %s in %s; it would be better to do all sets at once",prop, set_movie_id)
            odb.set_metadata(user_id=user_id, set_movie_id=set_movie_id, prop=prop, value=movie_metadata[prop])


################
# get-frame api_bp.
# Gets a single frame. Use cookie or API_KEY authenticaiton.
# Note that you can also get single frames with a signed URL from get-movie-metadata
#
def api_get_frame_jpeg(*,movie_id, frame_number):
    """Returns the JPEG for a given frame, or raises InvalidFrameAccess().
    If we have to extract the frame, write it to the database
    Used by get-frame below. Assumes that we have already verified access to the frame
    """
    movie_data = odb.get_movie_data(movie_id = movie_id)
    if movie_data is None:
        raise odb.InvalidFrameAccess()

    ret = tracker.extract_frame(movie_data = movie_data, frame_number = frame_number, fmt = 'jpeg')
    movie_metadata = tracker.extract_movie_metadata(movie_data=movie_data)
    set_movie_metadata(set_movie_id=movie_id, movie_metadata=movie_metadata)
    return ret

def api_get_frame_urn(*,frame_number,movie_id):
    """Returns the URN for a frame in a movie. If the frame does not have URN, create one."""
    urn = odb.get_frame_urn(frame_number=frame_number, movie_id=movie_id)
    if urn is not None:
        return urn
    # Get the frame data so we can get it a URN
    frame_data = api_get_frame_jpeg(frame_number=frame_number, movie_id=movie_id)
    frame_urn = odb.create_new_movie_frame(movie_id=movie_id,
                                           frame_number=frame_number,
                                           frame_data=frame_data)
    assert frame_urn is not None
    return frame_urn

@api_bp.route('/get-frame', methods=GET_POST)
def api_get_frame():
    """
    Gets a frame as a JPEG.
    If not is not in the object store
         - Grab it from the movie
         - write to the object store.
    Then:
         - return with a redirect ot the object store.

    :param api_key:   authentication
    :param movie_id:   movie_id
    :param frame_number: get the frame by frame_number (starting with 0)

    :return: - either the image (as a JPEG) or a JSON object. With JSON, includes:
      error - 404 - movie or frame does not exist
      no error - redirect to the signed URL
    """
    user_id      = get_user_id(allow_demo=True)
    frame_number = get_int('frame_number',0)
    movie_id     = get_movie_id()

    logging.debug('logging.debug /get-frame. user_id=%s frame_number=%s movie_id=%s',user_id,frame_number,movie_id)
    if not odb.can_access_movie(user_id=user_id, movie_id=movie_id):
        logging.info("User %s cannot access movie_id %s",user_id, movie_id)
        return make_response(jsonify(E.INVALID_MOVIE_ACCESS), 403)

    if frame_number<0:
        logging.error("invalid frame number %s",frame_number)
        return make_response(jsonify(E.INVALID_FRAME_NUMBER), 400)

    # See if there is a urn
    urn = odb.get_frame_urn(movie_id=movie_id, frame_number=frame_number)
    logging.debug("urn=%s",urn)
    if urn is not None and not db_object.object_exists(urn):
        logging.warning("%s does not exist",urn)
        odb.purge_movie_frames(movie_id=movie_id, frame_numbers=[frame_number])
        urn = None

    if urn is None:
        # the frame is not in the database, so we need to make it.
        logging.debug('getframe 5')
        try:
            frame_data = api_get_frame_jpeg(movie_id=movie_id, frame_number=frame_number)
            assert frame_data is not None
        except ValueError:
            return make_response(jsonify(E.INVALID_FRAME_NUMBER), 400)
        urn = odb.create_new_movie_frame(movie_id = movie_id, frame_number = frame_number, frame_data=frame_data)
        assert urn is not None

    logging.debug('getframe 4')
    logging.debug("api_get_frame urn=%s",urn)
    url = db_object.make_signed_url(urn=urn)
    logging.debug("api_get_frame url=%s",url)
    logging.debug('getframe 10 ')
    return redirect(url)


################################################################
## Movie editing

@api_bp.route('/edit-movie', methods=POST)
def api_edit_movie():
    """ edit a movie
    :param api_key: user authentication
    :param movie_id: the id of the movie to delete
    :param action: what to do. Must be one of 'rotate90cw'

    Note that set_movie_data() automatically updates the movie version number

    """
    movie_id = get_movie_id()
    user_id  = get_user_id(allow_demo=False)
    if not odb.can_access_movie(user_id=user_id, movie_id=movie_id):
        return E.INVALID_MOVIE_ACCESS

    action = get("action")
    if action=='rotate90cw':
        with tempfile.NamedTemporaryFile(suffix='.mp4') as movie_input:
            with tempfile.NamedTemporaryFile(suffix='.mp4') as movie_output:
                movie_input.write( odb.get_movie_data( movie_id = movie_id))
                tracker.rotate_movie(movie_input.name, movie_output.name, transpose=1)
                movie_output.seek(0)
                movie_data = movie_output.read()
                odb.set_movie_data(movie_id=movie_id, movie_data=movie_data)
                return {'error': False}
    else:
        return E.INVALID_EDIT_ACTION


@api_bp.route('/delete-movie', methods=POST)
def api_delete_movie():
    """ delete a movie
    :param api_key: - the User's API key.
    :param movie_id: the id of the movie to delete
    :param delete: 1 (default) to delete the movie, 0 to undelete the movie.
    """
    if not odb.can_access_movie(user_id=get_user_id(allow_demo=False),
                                movie_id=get_movie_id()):
        return E.INVALID_MOVIE_ACCESS
    odb.delete_movie(movie_id=get_movie_id(),
                    delete=get_bool('delete',True))
    return {'error': False}

################################################################
## get movie list and movie metadata data

@api_bp.route('/list-movies', methods=POST)
def api_list_movies():
    return jsonify({'error': False, 'movies': odb.list_movies(user_id=get_user_id())})

@api_bp.route('/get-movie-metadata', methods=GET_POST)
def api_get_movie_metadata():
    """
    Gets the metadata for a specific movie and its last tracked frame
    :param api_key:   authentication
    :param movie_id:  movie
    :param frame_start: if provided, first frame to provide metadata about
    :param frame_count: if provided, number of frames to get info on. 0 is no frames
    :param get_all_if_tracking_completed: if status is TRACKING_COMPLETED_FLAG, return all of the metadata

    Returns JSON dictionary:
    ['metadata'] - movie metadata (same as get-metadata)
    ['frames']   - dictionary individual frames
    ['frames'][10]      (where 10 is a frame number) - per-frame dictionary
    ['frames'][10]['markers'] - array of the trackpoints for that frame
    """
    user_id = get_user_id()
    movie_id = get_movie_id()
    frame_start = get_int('frame_start')
    frame_count = get_int('frame_count')
    get_all_if_tracking_completed = get_bool('get_all_if_tracking_completed')

    if not odb.can_access_movie(user_id=user_id, movie_id=movie_id):
        return make_response(E.INVALID_MOVIE_ACCESS,404)

    movie_metadata =  odb.get_movie_metadata(movie_id=movie_id, get_last_frame_tracked=True)

    # If we do not have the movie width and height, get them and write them back to the database
    if (not movie_metadata.get('width',None)) or (not movie_metadata.get('height',None)):
        movie_data     = odb.get_movie_data(movie_id = movie_id)

        if movie_data is None:
            return make_response(E.NO_MOVIE_DATA, 400)

        # Write them back
        movie_metadata = {**movie_metadata, **tracker.extract_movie_metadata(movie_data=movie_data)}
        set_movie_metadata(user_id=user_id, set_movie_id=movie_id, movie_metadata=movie_metadata)

    # If we have a movie_zipfile_urn, create a signed url (this can't be stored in the database...)
    if movie_metadata.get('movie_zipfile_urn',None):
        movie_metadata['movie_zipfile_url'] = db_object.make_signed_url(urn=movie_metadata['movie_zipfile_urn'])

    ret = {'error':False, 'metadata':movie_metadata }

    # If status TRACKING_COMPLETED_FLAG and the user has requested to get all trackpoints,
    # then get all the trackpoints.
    tracking_completed = movie_metadata.get('status','') == C.TRACKING_COMPLETED
    if tracking_completed and get_all_if_tracking_completed:
        frame_start = 0
        frame_count = C.MAX_FRAMES
    if frame_start is not None:
        if frame_count is None:
            return make_response(E.FRAME_START_NO_FRAME_COUNT, 400)
        if frame_count<1:
            return make_response(E.FRAME_COUNT_GT_0, 400)
        #
        # Get the trackpoints and then group by frame_number for the response
        ret['frames'] = defaultdict(dict)
        tpts = odb.get_movie_trackpoints(movie_id=movie_id,
                                         frame_start=frame_start,
                                         frame_count=frame_count)
        for tpt in tpts:
            frame = ret['frames'][tpt['frame_number']]
            if 'markers' not in frame:
                frame['markers'] = []
            frame['markers'].append(tpt)

    logger.debug("get_movie_metadata returns: %s",ret)
    return jsonify(ret)


@api_bp.route('/get-movie-trackpoints',methods=GET_POST)
def api_get_movie_trackpoints():
    """Downloads the movie trackpoints as a CSV or JSON
    :param api_key:   authentication
    :param movie_id:   movie
    :param: format - 'xlsx' or 'json'
    """
    movie_id = get_movie_id()
    if odb.can_access_movie(user_id=get_user_id(), movie_id=movie_id):
        # get_movie_trackpoints() returns a dictionary for each trackpoint.
        # we want a dictionary for each frame_number
        trackpoint_dicts = odb.get_movie_trackpoints(movie_id=movie_id)
        frame_numbers  = sorted( set(( tp['frame_number'] for tp in trackpoint_dicts) ))
        labels         = sorted( set(( tp['label'] for tp in trackpoint_dicts) ))
        frame_dicts    = defaultdict(dict)

        if get('format')=='json':
            return jsonify({'error':'False', 'trackpoint_dicts':trackpoint_dicts})

        for tp in trackpoint_dicts:
            frame_dicts[tp['frame_number']][tp['label']+' x'] = tp['x']
            frame_dicts[tp['frame_number']][tp['label']+' y'] = tp['y']

        fieldnames = ['frame_number']
        for label in labels:
            fieldnames.append(label+' x')
            fieldnames.append(label+' y')
        logging.debug("fieldnames=%s",fieldnames)

        # Now write it out with the dictwriter
        with io.StringIO() as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, restval='', extrasaction='ignore')
            writer.writeheader()
            for frame in frame_numbers:
                frame_dicts[frame]['frame_number'] = frame
                writer.writerow(frame_dicts[frame])
            response = make_response(f.getvalue())
            response.headers['Content-Type'] =  'text/csv'
            return response
    return E.INVALID_MOVIE_ACCESS


################################################################
## User management

##
## All of the users and the courses that this person can see
##
@api_bp.route('/list-users', methods=POST)
def api_list_users():
    return {**{'error': False}, **odb.list_users_courses(user_id=get_user_id())}

@api_bp.route('/list-users-courses', methods=POST)
def api_list_users_courses():
    return {**{'error': False}, **odb.list_users_courses(user_id=get_user_id())}


@api_bp.route('/ver', methods=GET_POST)
def api_ver():
    """Report the python version. Allows us to validate we are using Python3.
    Run the dictionary below through the VERSION_TEAMPLTE with jinja2.
    """
    current_app.logger.error("api_ver")
    return {'__version__': __version__, 'sys_version': sys.version}

################################################################
##
## For debug
##
@api_bp.route('/add', methods=GET_POST)
def api_add():
    a = get_float('a')
    b = get_float('b')
    try:
        return {'result': a+b, 'error': False}
    except (TypeError, ValueError):
        return {'error': True, 'message': 'arguments malformed'}



################################################################
################################################################
## Movie tracking
## Tracking is requested from the client and run in a background lambda function.

# pylint: disable=too-few-public-methods
# pylint: disable=consider-using-with
class MovieTrackCallback:
    """Service class to create a callback instance to update the movie status"""
    def __init__(self, *, user_id, movie_id):
        self.user_id = user_id
        self.movie_id = movie_id
        self.movie_metadata = None
        self.movie_zipfile_tf = tempfile.NamedTemporaryFile(suffix='.zip',prefix=f'movie_{movie_id}',delete=False)
        self.movie_zipfile    = ZipFile(self.movie_zipfile_tf.name, mode='w', compression=zipfile.ZIP_DEFLATED,compresslevel=9)
        self.last_frame_tracked = -1
        self.ziplen = 0

    def notify(self, *, frame_number, frame_data, frame_trackpoints): # pylint: disable=unused-argument
        """Update the status and write the frame to the database.
        We only track frames 1..(total_frames-1).
        If there are 296 frames, they are numbered 0 to 295.
        We actually track frames 1 through 295. We add 1 to make the status look correct.
        """
        # Write the frame data to the database if we do not have it
        # Moving to an object-oriented API would make this a whole lot more efficient...

        logging.debug("NOTIFY. self=%s self.ziplen=%s",self,self.ziplen)

        frame_jpeg = tracker.convert_frame_to_jpeg(frame_data, quality=60)
        self.last_frame_tracked = max(self.last_frame_tracked, frame_number)
        self.ziplen += len(frame_jpeg)
        logging.debug("appending frame %d len(frame_jpeg)=%s to zipfile  len=%s",frame_number,len(frame_jpeg),self.ziplen)
        self.movie_zipfile.writestr(f"frame_{frame_number:04}.jpg",frame_jpeg)

        # Update the trackpoints
        odb.put_frame_trackpoints(movie_id=self.movie_id, frame_number=frame_number, trackpoints=frame_trackpoints)

        # Update the movie status (for anyone monitoring)
        total_frames = self.movie_metadata['total_frames']
        message = f"Tracked frames {frame_number+1} of {total_frames}"
        odb.set_metadata(user_id=self.user_id, set_movie_id=self.movie_id, prop='status', value=message)
        logging.debug("NOTIFY AFTER. self=%s self.ziplen=%s",self,self.ziplen)

    def close(self):
        """Close the zipfile"""
        self.movie_zipfile.close()

    @property
    def zipfile_name(self):
        return self.movie_zipfile_tf.name

    @property
    def zipfile_data(self):
        logging.debug("zipfile_data %s length=%s",self.zipfile_name, os.path.getsize(self.zipfile_name))
        with open(self.zipfile_name,'rb') as f:
            return f.read()

    def done(self):
        logging.debug("DONE. Set TRACKING_COMPLETED")
        odb.set_metadata(user_id=self.user_id, set_movie_id=self.movie_id, prop='status', value=C.TRACKING_COMPLETED)
        if self.zipfile_name:
            logging.debug("Unlinking %s length=%s",self.zipfile_name, os.path.getsize(self.zipfile_name))
            os.unlink(self.zipfile_name)


##
## Actual code that runs to track a movie.
## Tracks to end.
## Can be implemented as a background task
def api_track_movie(*,user_id, movie_id, frame_start):
    """Generate trackpoints for a movie based on initial trackpoints stored in the database at frame_start.
    Extracts all frames from a movie and stores them in a zipfile.
    Stores new trackpoints and each frame in the database.
    """
    # Get all the trackpoints for every frame for the movie we are tracking or retracking
    input_trackpoints = odb.get_movie_trackpoints(movie_id=movie_id)

    # Write the movie to a tempfile, because OpenCV has to read movies from files.
    mtc = MovieTrackCallback(user_id = user_id, movie_id = movie_id)
    with tempfile.NamedTemporaryFile(suffix='.mp4',mode='wb') as infile:
        movie_data     = odb.get_movie_data(movie_id=movie_id)
        movie_metadata = tracker.extract_movie_metadata(movie_data=movie_data)
        infile.write( movie_data  )
        infile.flush()

        set_movie_metadata(user_id=user_id, set_movie_id=movie_id, movie_metadata=movie_metadata)

        # Track (or retrack) the movie and create the tracked movie
        # Each time the callback is called it will update the trackpoints for that frame
        # and write the frame to the frame store.
        #
        mtc.movie_metadata = odb.get_movie_metadata(movie_id=movie_id)
        tracker.track_movie(input_trackpoints = input_trackpoints,
                            frame_start       = frame_start,
                            moviefile_input   = infile.name,
                            callback = mtc.notify)
    mtc.close()
    ddbo = DDBO()
    ddbo.update_table(ddbo.movies, movie_id, {LAST_FRAME_TRACKED:mtc.last_frame_tracked})

    # Note: this puts the entire object in memory. That may be an issue at some point
    object_name = db_object.object_name(course_id=odb.course_id_for_movie_id(movie_id), movie_id=movie_id,ext='_mp4.zip')
    urn = db_object.make_urn(object_name=object_name)
    db_object.write_object(urn=urn, object_data=mtc.zipfile_data)
    odb.set_metadata(user_id=user_id, set_movie_id=movie_id, prop='movie_zipfile_urn',value=urn)
    mtc.done() # sets the status to tracking complete


@api_bp.route('/track-movie-queue', methods=GET_POST)
def api_track_movie_queue():
    """Tracks a movie that has been uploaded.
    :param api_key: the user's api_key
    :param movie_id: the movie to track; a new movie will be created
    :param frame_start: the frame to start tracking; frames 0..(frame_start-1) have track points copied.
    :param run_async: if True, do not wait for completion
    :return: dict['error'] = True/False
             dict['message'] = message to display
             dict['frame_start'] = where the tracking started
    """

    # pylint-disable: disable=unsupported-membership-test
    movie_id       = get_movie_id()
    user_id        = get_user_id(allow_demo=False)
    run_async      = get_bool('run_async')
    if not odb.can_access_movie(user_id=user_id, movie_id=movie_id):
        return make_response(jsonify(E.INVALID_MOVIE_ACCESS), 400)

    # Make sure we are not tracking a movie that is not an original movie
    movie_row = odb.list_movies(user_id=user_id, movie_id=movie_id)
    assert len(movie_row)==1
    if movie_row[0]['orig_movie'] is not None:
        return make_response(jsonify(E.MUST_TRACK_ORIG_MOVIE), 400)

    if run_async:
        raise RuntimeError("TODO - launch with concurrent.futures.ThreadPoolExecutor")
    else:
        logging.debug("calling api_track_movie")
        api_track_movie(user_id=user_id, movie_id=movie_id, frame_start=get_int('frame_start'))
        logging.debug("return from api_track_movie")
        return jsonify({'error': False, 'message':'Tracking is completed'})

    # We return all the trackpoints to the client, although the client currently doesn't use them


## /new-frame is being able to create our own time lapse movie
## It's for a camera app that we haven't written yet

@api_bp.route('/new-frame', methods=POST)
def api_new_frame():
    """Create a new frame and return its frame_urn.
    If frame exists, just update the frame_data (if frame data is provided).
    :param: api_key  - api_key
    :param: movie_id - the movie
    :param: frame_number - the frame to create
    :param: frame_data - if provided, it's uploaded; otherwise we just enter the frame into the database if it doesn't exist
    :return: frame_urn - that's what we care about

    """
    movie_id=get_movie_id()
    if not odb.can_access_movie(user_id=get_user_id(allow_demo=False), movie_id=movie_id):
        return E.INVALID_MOVIE_ACCESS
    try:
        frame_data = base64.b64decode( request.values.get('frame_base64_data'))
    except TypeError:
        frame_data = None
    frame_urn = odb.create_new_movie_frame( movie_id = movie_id,
                                            frame_number = get_int('frame_number'),
                                            frame_data = frame_data)
    return {'error': False, 'frame_urn': frame_urn}


## /put-frame-trackpoints:
## Writes analysis and trackpoints for specific frames. This is used by the client to update the trackpoints before asking for new tracking.

@api_bp.route('/put-frame-trackpoints', methods=POST)
def api_put_frame_trackpoints():
    """
    Writes analysis and trackpoints for specific frames. This is used by the client to update the trackpoints before asking for new tracking.
    :param: api_key  - the api_key
    :param: movie_id - the movie
    :param: frame_number - the the frame
    :param: trackpoints - JSON string, must be an array of trackpoints, if provided
    """
    user_id  = get_user_id(allow_demo=False)
    movie_id = get_movie_id()
    frame_number = get_int('frame_number')
    logging.debug("put_frame_analysis. user_id=%s movie_id=%s frame_number=%s",user_id,movie_id,frame_number)
    if not odb.can_access_movie(user_id=user_id, movie_id=movie_id):
        logging.debug("user %s cannot access movie_id %s",user_id, movie_id)
        return {'error':True, 'message':f'User {user_id} cannot access movie_id={movie_id}'}
    trackpoints=get_json('trackpoints')
    odb.put_frame_trackpoints(movie_id=movie_id, frame_number=frame_number, trackpoints=trackpoints)
    return {'error': False, 'message':'Trackpoints recorded.'}


################################################################
##
# Log API
#
@api_bp.route('/get-log', methods=POST)
def api_get_log():
    """Get what log entries we can. get_user_id() provides access control.
    TODO - add search capabilities.
    """
    return {'error':False, 'logs': odb.get_logs(user_id=get_user_id()) }


################################################################
## Metdata Management (movies and users, it's a common API!)

@api_bp.route('/set-metadata', methods=POST)
def api_set_metadata():
    """ set some aspect of the metadata
    :param api_key: authorization key
    :param movie_id: movie ID - if present, we are setting movie metadata
    :param user_id:  user ID  - if present, we are setting user metadata. (May not be the user_id from the api key)
    :param prop: which piece of metadata to set
    :param value: what to set it to
    :return  error=false
    """
    set_movie_id = get('set_movie_id')
    set_user_id  = get('set_user_id')

    if (set_movie_id is None) and (set_user_id is None):
        return {'error': True, 'result': 'Either set_movie_id or set_user_id is required'}

    value = get('value')
    odb.set_metadata(user_id=get_user_id(allow_demo=False),
                             set_movie_id=set_movie_id,
                             set_user_id=set_user_id,
                             prop=get('property'),
                             value=value)

    return {'error': False}
