"""
API
"""

import json
import logging
import sys
import subprocess
import smtplib
import tempfile
import base64
import functools
import io
import csv
import os
import zipfile
from collections import defaultdict
from zipfile import ZipFile

import bottle
from bottle import request,response
from validate_email_address import validate_email
#from zappa.asynchronous import task

import db
import db_object
import auth

from constants import C,E,__version__,GET,POST,GET_POST
import mailer
import tracker

api = bottle.Bottle()

################################################################
## Utility
def expand_memfile_max():
    logging.info("Changing MEMFILE_MAX from %d to %d",
                 bottle.BaseRequest.MEMFILE_MAX, C.MAX_FILE_UPLOAD)
    bottle.BaseRequest.MEMFILE_MAX = C.MAX_FILE_UPLOAD


def is_true(s):
    return str(s)[0:1] in 'yY1tT'

@functools.cache
def git_head_time():
    try:
        return subprocess.check_output("git log --no-walk --pretty=format:%cd".split(),encoding='utf-8')
    except (subprocess.SubprocessError,FileNotFoundError):
        return ""

@functools.cache
def git_last_commit():
    try:
        return subprocess.check_output("git log --pretty=[%h] -1 HEAD".split(),encoding='utf-8')
    except (subprocess.SubprocessError,FileNotFoundError):
        return ""

################################################################
## CORS
# https://stackoverflow.com/questions/17262170/bottle-py-enabling-cors-for-jquery-ajax-requests
# Allows API calls on remote infrastructure from local JavaScript
class EnableCors:               # pylint: disable=too-few-public-methods
    """
    This class adds the three headers (below) to the HTTP header of every API response.
    This allows the JavaScript running locally to execute API calls on another server.
    This makes it possible to debug the JavaScript with the server running on AWS, or vice-versa.
    Environment variable PLANTTRACER_API_BASE specifies where API is hosted.
    Environment variable PLANTTRACER_STATIC_BASE specifies where the JavaScript files are hosted.
    """
    name = 'enable_cors'
    api = 2

    def apply(self, fn, context): # pylint: disable=unused-argument
        def _enable_cors(*args, **kwargs):
            # set CORS headers
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'
            # And run the original function that we wrapped.
            return fn(*args, **kwargs)
        return _enable_cors

api.install(EnableCors())       # install the callback in the Bottle stack

################################################################
# define get(), which gets a variable from either the forms request or the query string
def get(key, default=None):
    logging.debug("%s request.forms.get(%s)=%s",request.forms.keys(),key,request.forms.get(key))
    logging.debug("%s request.query.get(%s)=%s",request.query.keys(),key,request.query.get(key))
    return request.forms.get(key, request.query.get(key, default))

def get_json(key):
    try:
        return json.loads(request.forms.get(key))
    except (TypeError,ValueError,json.decoder.JSONDecodeError):
        return None

def get_int(key, default=None):
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
    userdict = get_user_dict()
    if userdict['demo'] and not allow_demo:
        logging.info("demo account blocks requested action")
        raise auth.http403('demo accounts not allowed to execute requested action')
    return userdict['id']


def fix_types(obj):
    """Process JSON so that it dumps without `default=str`, since we can't
    seem to get bottle to do that."""
    return json.loads(json.dumps(obj,default=str))

def get_user_dict():
    """Returns the user_id of the currently logged in user, or throws a response"""
    logging.debug("get_user_dict(). request.url=%s",request.url)
    api_key = auth.get_user_api_key()
    logging.debug("get_user_dict(). api_key=%s",api_key)
    if api_key is None:
        logging.info("api_key is none or invalid. request=%s",bottle.request.fullpath)
        if bottle.request.fullpath.startswith('/api/'):
            raise auth.http403('invalid API key')
        # Check if we were running under an API

        # This will redirect to the / and produce a "Session expired" message
        raise auth.http403('session expired')
    userdict = db.validate_api_key(api_key)
    if not userdict:
        logging.info("api_key %s is invalid  ipaddr=%s request.url=%s", api_key,request.environ.get('REMOTE_ADDR'),request.url)
        auth.clear_cookie()
        raise auth.http403(f'Error 404: api_key {api_key} is invalid. ')
    return userdict

def page_dict(title='', *, require_auth=False, lookup=True, logout=False,debug=False):
    """Returns a dictionary that can be used by post of the templates.
    :param: title - the title we should give the page
    :param: require_auth  - if true, the user must already be authenticated, or throws an error
    :param: logout - if true, force the user to log out by issuing a clear-cookie command
    :param: lookup - if true, we weren't being called in an error condition, so we can lookup the api_key in the URL or the cookie
    """
    logging.debug("1. page_dict require_auth=%s logout=%s lookup=%s",require_auth,logout,lookup)
    o = urlparse(request.url)
    logging.debug("o=%s",o)
    if lookup:
        api_key = auth.get_user_api_key()
        logging.debug("auth.get_user_api_key=%s",api_key)
        if api_key is None and require_auth is True:
            logging.debug("api_key is None and require_auth is True")
            raise auth.http403("api_key is None and require_auth is True")
    else:
        api_key = None

    if (api_key is not None) and (logout is False):
        # Get the user_dict is from the database
        user_dict = get_user_dict()
        user_name = user_dict['name']
        user_email = user_dict['email']
        user_demo  = user_dict['demo']
        user_id = user_dict['id']
        user_primary_course_id = user_dict['primary_course_id']
        logged_in = 1
        primary_course_name = db.lookup_course_by_id(course_id=user_primary_course_id)['course_name']
        admin = 1 if db.check_course_admin(user_id=user_id, course_id=user_primary_course_id) else 0
        # If this is a demo account, the user cannot be an admin (security)
        if user_demo:
            assert not admin
        # if this is not a demo account and the user_id is set, make sure we set the cookie
        if (user_id is not None) and (not user_demo):
            auth.set_cookie(api_key)

    else:
        user_name  = None
        user_email = None
        user_demo  = 0
        user_id    = None
        user_primary_course_id = None
        primary_course_name = None
        admin = 0
        logged_in = 0

    try:
        movie_id = int(request.query.get('movie_id'))
    except (AttributeError, KeyError, TypeError):
        movie_id = 0            # to avoid errors

    ret= fix_types({
        C.API_BASE: api_base,
        C.STATIC_BASE: static_base,
        'api_key': api_key,     # the API key that is currently active
        'user_id': user_id,     # the user_id that is active
        'user_name': user_name, # the user's name
        'user_email': user_email, # the user's email
        'user_demo':  user_demo,  # true if this is a demo user
        'logged_in': logged_in,
        'admin':admin,
        'user_primary_course_id': user_primary_course_id,
        'primary_course_name': primary_course_name,
        'title':'Plant Tracer '+title,
        'hostname':o.hostname,
        'movie_id':movie_id,
        'demo_mode_available':DEMO_MODE_AVAILABLE,
        'MAX_FILE_UPLOAD': C.MAX_FILE_UPLOAD,
        'dbreader_host':auth.get_dbreader().host,
        'version':__version__,
        'git_head_time':git_head_time(),
        'git_last_commit':git_last_commit()
    })
    for (k,v) in ret.items():
        if v is None:
            ret[k] = "null"
    if debug:
        logging.debug("fixed page_dict=%s",ret)
    return ret




################################################################
# /api URLs
################################################################


@api.route('/check-api_key', method=GET_POST)
def api_check_api_key():
    """API to check the user key and, if valid, return usedict or returns an error."""

    userdict = db.validate_api_key(auth.get_user_api_key())
    if userdict:
        return {'error': False, 'userinfo': fix_types(userdict)}
    return E.INVALID_API_KEY


@api.route('/get-logs', method=POST)
def api_get_logs():
    """Get logs and return in JSON. The database function does all of the security checks, but we need to have a valid user."""
    kwargs = {}
    for kw in ['start_time','end_time','course_id','course_key',
               'movie_id','log_user_id','ipaddr','count','offset']:
        if kw in request.forms.keys():
            kwargs[kw] = request.forms.get(kw)

    logs    = db.get_logs(user_id=get_user_id(),**kwargs)
    return {'error':False, 'logs': logs}

@api.route('/register', method=GET_POST)
def api_register():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    planttracer_endpoint = request.forms.get('planttracer_endpoint')
    if not validate_email(email, check_mx=False):
        logging.info("email not valid: %s", email)
        return E.INVALID_EMAIL
    course_key = request.forms.get('course_key')
    if not db.validate_course_key(course_key=course_key):
        return E.INVALID_COURSE_KEY
    if db.remaining_course_registrations(course_key=course_key) < 1:
        return E.NO_REMAINING_REGISTRATIONS
    name = request.forms.get('name')
    db.register_email(email=email, course_key=course_key, name=name)
    new_api_key = db.make_new_api_key(email=email)
    if not new_api_key:
        logging.info("email not in database: %s",email)
        return E.INVALID_EMAIL
    link_html = f"<p/><p>You can also log in by clicking this link: <a href='/list?api_key={new_api_key}'>login</a></p>"
    try:
        db.send_links(email=email, planttracer_endpoint=planttracer_endpoint, new_api_key=new_api_key)
        ret = {'error': False, 'message': 'Registration key sent to '+email+link_html}
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

class EmailNotInDatabase(Exception):
    """Handle error condition below"""


def send_link(*, email, planttracer_endpoint):
    new_api_key = db.make_new_api_key(email=email)
    if not new_api_key:
        logging.info("email not in database: %s",email)
        raise EmailNotInDatabase(email)
    db.send_links(email=email, planttracer_endpoint=planttracer_endpoint, new_api_key=new_api_key)


@api.route('/resend-link', method=GET_POST)
def api_send_link():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    planttracer_endpoint = request.forms.get('planttracer_endpoint')
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


@api.route('/bulk-register', method=POST)
def api_bulk_register():
    """Allow an admin to register people in the class, increasing the class size as necessary to do so."""
    course_id =  int(request.forms.get('course_id'))
    user_id   = get_user_id()
    planttracer_endpoint = request.forms.get('planttracer_endpoint')
    if not db.check_course_admin(course_id = course_id, user_id=user_id):
        return E.INVALID_COURSE_ACCESS

    email_addresses = request.forms.get('email-addresses').replace(","," ").replace(";"," ").replace(" ","\n").split("\n")
    try:
        for email in email_addresses:
            if not validate_email(email, check_mx=C.CHECK_MX):
                return E.INVALID_EMAIL
            db.register_email(email=email, course_id=course_id, name="")
            send_link(email=email, planttracer_endpoint=planttracer_endpoint)
    except EmailNotInDatabase:
        return E.INVALID_EMAIL
    except mailer.NoMailerConfiguration:
        logging.error("no mailer configuration")
        return E.NO_MAILER_CONFIGURATION
    except mailer.InvalidMailerConfiguration as e:
        logging.error("invalid mailer configuration: %s",e)
        return E.INVALID_MAILER_CONFIGURATION
    return {'error':False, 'message':f'Registered {len(email_addresses)} email addresses'}

################################################################
##
## Object API
MIME_MAP = {'.jpg':'image/jpeg',
            '.jpeg':'image/jpeg',
            '.mov':'video/mp4',
            '.mp4':'video/mp4',
            '.zip':'application/zip'
            }


@api.route('/get-object', method=GET)
def api_get_object():
    """Implement signed URLs. Doesn't need APIkey!"""
    # my object store doesn't implement mime types, so fake them.
    urn = get('urn')
    ext = os.path.splitext( urn )[1]
    bottle.response.set_header('Content-Type', MIME_MAP[ext])
    return db_object.read_signed_url(urn=get('urn'), sig=get('sig'))


################################################################
##
# Movie APIs. All of these need to only be POST to avoid an api_key from being written into the logfile
##

@api.route('/new-movie', method=POST)
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
    movie_data_sha256 = get('movie_data_sha256')

    if (movie_data_sha256 is None) or (len(movie_data_sha256)!=64):
        return {'error':True,'message':'Movie SHA256 not provided or is invalid. Uploaded failed.'}

    ret = {'error':False}

    # This is where the movie_id is assigned
    ret['movie_id'] = db.create_new_movie(user_id=user_id,
                                          title=request.forms.get('title'),
                                          description=request.forms.get('description') )

    # Get the object name and create the upload URL
    object_name= db_object.object_name( course_id = db.course_id_for_movie_id( ret['movie_id']),
                                        movie_id = ret['movie_id'],
                                        ext=C.MOVIE_EXTENSION)
    movie_data_urn        = db_object.make_urn( object_name = object_name)
    db.set_movie_data_urn(movie_id=ret['movie_id'], movie_data_urn=movie_data_urn)
    ret['presigned_post'] = db_object.make_presigned_post(urn=movie_data_urn,
                                                          mime_type='video/mp4',
                                                          sha256=movie_data_sha256)
    return ret


@api.route('/upload-movie', method=POST)
def api_upload_movie():
    """
    Upload a movie that has already been created. This is our receiver for 'presigned posts.'
    We verify that the SHA256 provided matches the SHA256 in the database, then we verify that the uploaded
    file actually has that SHA256.
    :param: mime_type - mime type
    :param: scheme - should be db
    :param: sha256 - should be a hex encoding of the sha256
    :param: key    - where the file gets uploaded -from api_new_movie()
    :param: request.files['file'] - the file!
    """
    scheme = get('scheme')
    key = get('key')
    movie_data_sha256 = get('sha256') # claimed SHA256
    logging.debug("api_upload_movie: request=%s request.files=%s ", request,request.files)
    if 'file' not in request.files: # pylint: disable=unsupported-membership-test
        logging.debug("request.files=%s",request.files)
        return E.NO_FILE_PARAMETER
    with io.BytesIO() as f:
        request.files['file'].save(f)
        movie_data = f.getvalue()
        logging.debug("len(movie_data)=%s",len(movie_data))
        if len(movie_data) > C.MAX_FILE_UPLOAD:
            return {'error': True, 'message': f'Upload larger than larger than {C.MAX_FILE_UPLOAD} bytes.'}
    # make sure claimed SHA256 matches computed SHA256
    if db_object.sha256(movie_data) != movie_data_sha256:
        logging.error("sha256(movie_data)=%s but movie_data_sha256=%s",db_object.sha256(movie_data),movie_data_sha256)
        return {'error': True, 'message':
                f'movie_data_sha256={movie_data_sha256} but post.sha256={db_object.sha256(movie_data)}'}
    urn = db_object.make_urn(object_name=key, scheme=scheme)
    db_object.write_object(urn, movie_data)
    return {'error':False,'message':'Upload ok.'}


@api.route('/get-movie-data', method=GET_POST)
def api_get_movie_data():
    """
    Redirects the user to a URL that downloads the movie.
    :param api_key:   authentication
    :param movie_id:  movie
    :param format:    if 'zip' - return as as a zipfile
    :param redirect_inline: - if True and we are redirecting, return "#REDIRECT url" (for testing)
    :return:  IF MOVIE IS IN S3 - Redirect to a signed URL.
              IF MOVIE IS IN DB - The raw movie data as a movie.
    """
    logging.debug("api_get_movie_data")
    try:
        movie_id = get_int('movie_id')
        movie = db.Movie(movie_id, user_id=get_user_id())
    except (db.UnauthorizedUser,bottle.HTTPResponse) as e:
        logging.debug("user authentication error=%s",e)
        return bottle.HTTPResponse(body=f'user={get_user_id()} movie_id={movie_id}', status=403)

    if get('format')=='zip':
        url = movie.zipfile_url
    else:
        url = movie.url

    if url is None:
        logging.debug("no movie data for movie_id %s",movie_id)
        return bottle.HTTPResponse(body=f'user={get_user_id()} movie_id={movie_id}', status=404)

    # This is used for testing redirect response in the test program
    if get_bool('redirect_inline'):
        return "#REDIRECT " + url
    logging.info("Redirecting movie_id=%s to %s",movie.movie_id, movie.url)
    return bottle.redirect(url)

def set_movie_metadata(*,user_id=0, set_movie_id,movie_metadata):
    """Update the movie metadata."""
    for prop in ['fps','width','height','total_frames','total_bytes']:
        if prop in movie_metadata:
            db.set_metadata(user_id=user_id, set_movie_id=set_movie_id, prop=prop, value=movie_metadata[prop])


################
# get-frame api.
# Gets a single frame. Use cookie or API_KEY authenticaiton.
# Note that you can also get single frames with a signed URL from get-movie-metadata
#
def api_get_frame_jpeg(*,movie_id, frame_number):
    """Returns the JPEG for a given frame, or raises InvalidFrameAccess().
    If we have to extract the frame, write it to the database
    Used by get-frame below. Assumes that we have already verified access to the frame
    """
    movie_data = db.get_movie_data(movie_id = movie_id)
    if movie_data is None:
        raise db.InvalidFrameAccess()
    try:
        ret = tracker.extract_frame(movie_data = movie_data, frame_number = frame_number, fmt = 'jpeg')
        movie_metadata = tracker.extract_movie_metadata(movie_data=movie_data)
        set_movie_metadata(set_movie_id=movie_id, movie_metadata=movie_metadata)
        return ret
    except ValueError as e:
        return bottle.HTTPResponse(status=500, body=f"frame number {frame_number} out of range: "+e.args[0])

def api_get_frame_urn(*,frame_number,movie_id):
    """Returns the URN for a frame in a movie. If the frame does not have URN, create one."""
    urn = db.get_frame_urn(frame_number=frame_number, movie_id=movie_id)
    if urn is not None:
        return urn
    # Get the frame data so we can get it a URN
    frame_data = api_get_frame_jpeg(frame_number=frame_number, movie_id=movie_id)
    frame_urn = db.create_new_frame(movie_id=movie_id,
                                    frame_number=frame_number,
                                    frame_data=frame_data)
    assert frame_urn is not None
    return frame_urn

@api.route('/get-frame', method=GET_POST)
def api_get_frame():
    """
    Gets a frame as a JPEG.
    If not is not in the object store
         - Grab it from the movie
         - write to the object store.
    Then:
         - return with a redirect ot the object store.

    :param api_key:   authentication
    :param movie_id:   movie
    :param frame_number: get the frame by frame_number (starting with 0)

    :return: - either the image (as a JPEG) or a JSON object. With JSON, includes:
      error - 404 - movie or frame does not exist
      no error - redirect to the signed URL
    """
    user_id      = get_user_id(allow_demo=True)
    frame_number = get_int('frame_number')
    movie_id     = get_int('movie_id')

    if not db.can_access_movie(user_id=user_id, movie_id=movie_id):
        logging.info("User %s cannot access movie_id %s",user_id, movie_id)
        return auth.http403(f'Error 404: User {user_id} cannot access movie {movie_id}')

    if frame_number<0:
        return auth.http404(f'Error 404: invalid frame number {frame_number}')

    # See if there is a urn
    urn = db.get_frame_urn(movie_id=movie_id, frame_number=frame_number)
    if urn is None:
        # the frame is not in the database, so we need to make it.
        frame_data = api_get_frame_jpeg(movie_id=movie_id, frame_number=frame_number)
        urn = db.create_new_frame(movie_id = movie_id, frame_number = frame_number, frame_data=frame_data)
        assert urn is not None
    logging.debug("api_get_frame urn=%s",urn)
    url = db_object.make_signed_url(urn=urn)
    logging.debug("api_get_frame url=%s",url)
    return bottle.redirect(url)


################################################################
## Movie editing

@api.route('/edit-movie', method=POST)
def api_edit_movie():
    """ edit a movie
    :param api_key: user authentication
    :param movie_id: the id of the movie to delete
    :param action: what to do. Must be one of 'rotate90cw'

    """
    movie_id = get_int('movie_id')
    user_id  = get_user_id(allow_demo=False)
    if not db.can_access_movie(user_id=user_id, movie_id=movie_id):
        return E.INVALID_MOVIE_ACCESS

    action = get("action")
    if action=='rotate90cw':
        with tempfile.NamedTemporaryFile(suffix='.mp4') as movie_input:
            with tempfile.NamedTemporaryFile(suffix='.mp4') as movie_output:
                movie = db.Movie(movie_id, user_id=get_user_id())
                movie_input.write( movie.data )
                tracker.rotate_movie(movie_input.name, movie_output.name, transpose=1)
                movie_output.seek(0)
                movie.data = movie_data = movie_output.read()
                movie.version += 1
                movie_metadata = tracker.extract_movie_metadata(movie_data=movie_data)
                set_movie_metadata(user_id=user_id, set_movie_id=movie_id, movie_metadata=movie_metadata)

                return {'error': False}
    else:
        return E.INVALID_EDIT_ACTION



@api.route('/delete-movie', method=POST)
def api_delete_movie():
    """ delete a movie
    :param api_key: - the User's API key.
    :param movie_id: the id of the movie to delete
    :param delete: 1 (default) to delete the movie, 0 to undelete the movie.
    """
    if not db.can_access_movie(user_id=get_user_id(allow_demo=False),
                           movie_id=get_int('movie_id')):
        return E.INVALID_MOVIE_ACCESS
    db.delete_movie(movie_id=get_int('movie_id'),
                    delete=get_bool('delete',True))
    return {'error': False}


################################################################
## get movie list and movie metadata data

@api.route('/list-movies', method=POST)
def api_list_movies():
    return {'error': False, 'movies': fix_types(db.list_movies(user_id=get_user_id()))}


@api.route('/get-movie-metadata', method=GET_POST)
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
    movie_id = get_int('movie_id')
    frame_start = get_int('frame_start')
    frame_count = get_int('frame_count')
    get_all_if_tracking_completed = get_bool('get_all_if_tracking_completed')

    if not db.can_access_movie(user_id=user_id, movie_id=movie_id):
        return E.INVALID_MOVIE_ACCESS

    movie_metadata =  db.get_movie_metadata(user_id=user_id, movie_id=movie_id, get_last_frame_tracked=True)[0]
    # If we do not have the movie width and height, get them...
    if (not movie_metadata['width']) or (not movie_metadata['height']):
        movie_data     = db.get_movie_data(movie_id = movie_id)

        if movie_data is None:
            return E.NO_MOVIE_DATA

        # Add in the movie_metadata we just got
        movie_metadata = {**movie_metadata, **tracker.extract_movie_metadata(movie_data=movie_data)}
        set_movie_metadata(user_id=user_id, set_movie_id=movie_id, movie_metadata=movie_metadata)
    # If we have a movie_zipfile_urn, create a signed url
    if movie_metadata.get('movie_zipfile_urn',None):
        movie_metadata['movie_zipfile_url'] = db_object.make_signed_url(urn=movie_metadata['movie_zipfile_urn'])

    ret = {'error':False,
           'metadata':movie_metadata
        }

    # If status TRACKING_COMPLETED_FLAG and the user has requested to get all trackpoints,
    # then get all the trackpoints.
    tracking_completed = movie_metadata.get('status','') == C.TRACKING_COMPLETED
    if tracking_completed and get_all_if_tracking_completed:
        frame_start = 0
        frame_count = C.MAX_FRAMES
    if frame_start is not None:
        if frame_count is None:
            return E.FRAME_START_NO_FRAME_COUNT
        if frame_count<1:
            return E.FRAME_COUNT_GT_0
        #
        # Get the trackpoints and then group by frame_number for the response
        ret['frames'] = defaultdict(dict)
        tpts = db.get_movie_trackpoints(movie_id=movie_id, frame_start=frame_start, frame_count=frame_count)
        for tpt in tpts:
            frame = ret['frames'][tpt['frame_number']]
            if 'markers' not in frame:
                frame['markers'] = []
            frame['markers'].append(tpt)

    return fix_types(ret)


@api.route('/get-movie-trackpoints',method=GET_POST)
def api_get_movie_trackpoints():
    """Downloads the movie trackpoints as a CSV or JSON
    :param api_key:   authentication
    :param movie_id:   movie
    :param: format - 'xlsx' or 'json'
    """
    if db.can_access_movie(user_id=get_user_id(), movie_id=get_int('movie_id')):
        # get_movie_trackpoints() returns a dictionary for each trackpoint.
        # we want a dictionary for each frame_number
        trackpoint_dicts = db.get_movie_trackpoints(movie_id=get_int('movie_id'))
        frame_numbers  = sorted( set(( tp['frame_number'] for tp in trackpoint_dicts) ))
        labels         = sorted( set(( tp['label'] for tp in trackpoint_dicts) ))
        frame_dicts    = defaultdict(dict)

        if get('format')=='json':
            return fix_types({'error':'False',
                              'trackpoint_dicts':trackpoint_dicts})

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
            bottle.response.set_header('Content-Type', 'text/csv')
            return f.getvalue()
    return E.INVALID_MOVIE_ACCESS


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
        self.ziplen += len(frame_jpeg)
        logging.debug("appending frame %d len(frame_jpeg)=%s to zipfile  len=%s",frame_number,len(frame_jpeg),self.ziplen)
        self.movie_zipfile.writestr(f"frame_{frame_number:04}.jpg",frame_jpeg)

        # Update the trackpoints
        db.put_frame_trackpoints(movie_id=self.movie_id, frame_number=frame_number, trackpoints=frame_trackpoints)

        # Update the movie status (for anyone monitoring)
        total_frames = self.movie_metadata['total_frames']
        message = f"Tracked frames {frame_number+1} of {total_frames}"
        db.set_metadata(user_id=self.user_id, set_movie_id=self.movie_id, prop='status', value=message)
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
        db.set_metadata(user_id=self.user_id, set_movie_id=self.movie_id, prop='status', value=C.TRACKING_COMPLETED)
        if self.zipfile_name:
            logging.debug("Unlinking %s length=%s",self.zipfile_name, os.path.getsize(self.zipfile_name))
            os.unlink(self.zipfile_name)

##
## @task causes this to be run in background on zappa, but in foreground when run locally
## It's specific to zappa
## TODO - replace with a reasonable background task, or give up on background tasks
##
#@task
def api_track_movie(*,user_id, movie_id, frame_start):
    """Generate trackpoints for a movie based on initial trackpoints stored in the database at frame_start.
    Stores new trackpoints and each frame in the database. No longer renders new movie: that's now in render_tracked_movie
    """
    # Get all the trackpoints for every frame for the movie we are tracking or retracking
    input_trackpoints = db.get_movie_trackpoints(movie_id=movie_id)

    # Write the movie to a tempfile, because OpenCV has to read movies from files.
    mtc = MovieTrackCallback(user_id = user_id, movie_id = movie_id)
    with tempfile.NamedTemporaryFile(suffix='.mp4',mode='wb') as infile:
        movie_data     = db.get_movie_data(movie_id=movie_id)
        movie_metadata = tracker.extract_movie_metadata(movie_data=movie_data)
        infile.write( movie_data  )
        infile.flush()

        set_movie_metadata(user_id=user_id, set_movie_id=movie_id, movie_metadata=movie_metadata)

        # Track (or retrack) the movie and create the tracked movie
        # Each time the callback is called it will update the trackpoints for that frame
        # and write the frame to the frame store.
        #
        mtc.movie_metadata = db.get_movie_metadata(movie_id=movie_id, user_id=user_id)[0]
        tracker.track_movie(input_trackpoints = input_trackpoints,
                            frame_start       = frame_start,
                            moviefile_input   = infile.name,
                            callback = mtc.notify)
    mtc.close() # close the zipfile
    # Note: this puts the entire object in memory. That may be an issue at some point
    object_name = db_object.object_name(course_id=db.course_id_for_movie_id(movie_id), movie_id=movie_id,ext='_mp4.zip')
    urn = db_object.make_urn(object_name=object_name)
    db_object.write_object(urn=urn, object_data=mtc.zipfile_data)
    db.set_metadata(user_id=user_id, set_movie_id=movie_id, prop='movie_zipfile_urn',value=urn)
    mtc.done() # sets the status to tracking complete

@api.route('/track-movie-queue', method=GET_POST)
def api_track_movie_queue():
    """Tracks a movie that has been uploaded.
    :param api_key: the user's api_key
    :param movie_id: the movie to track; a new movie will be created
    :param frame_start: the frame to start tracking; frames 0..(frame_start-1) have track points copied.
    :return: dict['error'] = True/False
             dict['message'] = message to display
             dict['frame_start'] = where the tracking started
    """

    # pylint: disable=unsupported-membership-test
    movie_id       = get_int('movie_id')
    user_id        = get_user_id(allow_demo=False)
    if not db.can_access_movie(user_id=user_id, movie_id=movie_id):
        return E.INVALID_MOVIE_ACCESS

    # Make sure we are not tracking a movie that is not an original movie
    movie_row = db.list_movies(user_id=user_id, movie_id=movie_id)
    assert len(movie_row)==1
    if movie_row[0]['orig_movie'] is not None:
        return E.MUST_TRACK_ORIG_MOVIE

    logging.debug("calling api_track_movie")
    api_track_movie(user_id=user_id, movie_id=movie_id,
                    frame_start=get_int('frame_start'))

    logging.debug("return from api_track_movie")
    # We return all the trackpoints to the client, although the client currently doesn't use them
    return {'error': False, 'message':'Tracking is queued'}


## /new-frame is being able to create our own time lapse movie
## It's for a camera app that we haven't written yet

@api.route('/new-frame', method=POST)
def api_new_frame():
    """Create a new frame and return its frame_urn.
    If frame exists, just update the frame_data (if frame data is provided).
    :param: api_key  - api_key
    :param: movie_id - the movie
    :param: frame_number - the frame to create
    :param: frame_data - if provided, it's uploaded; otherwise we just enter the frame into the database if it doesn't exist
    :return: frame_urn - that's what we care about

    """
    if not db.can_access_movie(user_id=get_user_id(allow_demo=False), movie_id=request.forms.get('movie_id')):
        return E.INVALID_MOVIE_ACCESS
    try:
        frame_data = base64.b64decode( request.forms.get('frame_base64_data'))
    except TypeError:
        frame_data = None
    frame_urn = db.create_new_frame( movie_id = get_int('movie_id'),
                               frame_number = get_int('frame_number'),
                               frame_data = frame_data)
    return {'error': False, 'frame_urn': frame_urn}


## /put-frame-trackpoints:
## Writes analysis and trackpoints for specific frames. This is used by the client to update the trackpoints before asking for new tracking.

@api.route('/put-frame-trackpoints', method=POST)
def api_put_frame_trackpoints():
    """
    Writes analysis and trackpoints for specific frames. This is used by the client to update the trackpoints before asking for new tracking.
    :param: api_key  - the api_key
    :param: movie_id - the movie
    :param: frame_number - the the frame
    :param: trackpoints - JSON string, must be an array of trackpoints, if provided
    """
    user_id   = get_user_id(allow_demo=False)
    movie_id = get_int('movie_id')
    frame_number = get_int('frame_number')
    logging.debug("put_frame_analysis. user_id=%s movie_id=%s frame_number=%s",user_id,movie_id,frame_number)
    if not db.can_access_movie(user_id=user_id, movie_id=movie_id):
        logging.debug("user %s cannot access movie_id %s",user_id, movie_id)
        return {'error':True, 'message':f'User {user_id} cannot access movie_id={movie_id}'}
    trackpoints=get_json('trackpoints')
    db.put_frame_trackpoints(movie_id=movie_id, frame_number=frame_number, trackpoints=trackpoints)
    return {'error': False, 'message':'Trackpoints recorded.'}


################################################################
##
# Log API
#
@api.route('/get-log', method=POST)
def api_get_log():
    """Get what log entries we can. get_user_id() provides access control.
    TODO - add search capabilities.
    """
    return {'error':False, 'logs': db.get_logs(user_id=get_user_id()) }


################################################################
## Metdata Management (movies and users, it's a common API!)


@api.route('/set-metadata', method='POST')
def api_set_metadata():
    """ set some aspect of the metadata
    :param api_key: authorization key
    :param movie_id: movie ID - if present, we are setting movie metadata
    :param user_id:  user ID  - if present, we are setting user metadata. (May not be the user_id from the api key)
    :param prop: which piece of metadata to set
    :param value: what to set it to
    """
    set_movie_id = get_int('set_movie_id')
    set_user_id  = get_int('set_user_id')

    if (set_movie_id is None) and (set_user_id is None):
        return {'error': True, 'result': 'Either set_movie_id or set_user_id is required'}

    result = db.set_metadata(user_id=get_user_id(allow_demo=False),
                             set_movie_id=set_movie_id,
                             set_user_id=set_user_id,
                             prop=get('property'),
                             value=get('value'))

    return {'error': False, 'result': result}


################################################################
## User management

##
## All of the users that this person can see
##
@api.route('/list-users', method=POST)
def api_list_users():
    return {**{'error': False}, **db.list_users(user_id=get_user_id())}


@api.route('/ver', method=GET_POST)
def api_ver():
    """Report the python version. Allows us to validate we are using Python3.
    Run the dictionary below through the VERSION_TEAMPLTE with jinja2.
    """
    logging.debug("api_ver")
    return {'__version__': __version__, 'sys_version': sys.version}


################################################################
##
## For debug
##
@api.route('/add', method=GET_POST)
def api_add():
    a = get_float('a')
    b = get_float('b')
    try:
        return {'result': a+b, 'error': False}
    except (TypeError, ValueError):
        return {'error': True, 'message': 'arguments malformed'}
