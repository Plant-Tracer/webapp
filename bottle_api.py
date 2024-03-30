"""
API
"""

import time
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
from collections import defaultdict


from validate_email_address import validate_email
import bottle
from bottle import request
from zappa.asynchronous import task


import db
import db_object
import auth

from constants import C,E,__version__,POST,GET_POST,MIME
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
    if 'id' not in userdict:
        logging.info("no ID in userdict = %s", userdict)
        raise bottle.HTTPResponse(body='user_id is not valid', status=501, headers={ 'Location': '/'})
    if userdict['demo'] and not allow_demo:
        logging.info("demo account blocks requeted action")
        raise bottle.HTTPResponse(body='{"Error":true,"message":"demo accounts not allowed to execute requested action."}',
                                  status=503, headers={ 'Location': '/'})
    return userdict['id']


def fix_types(obj):
    """Process JSON so that it dumps without `default=str`, since we can't
    seem to get bottle to do that."""
    return json.loads(json.dumps(obj,default=str))


def get_user_dict():
    """Returns the user_id of the currently logged in user, or throws a response"""
    api_key = auth.get_user_api_key()
    if api_key is None:
        logging.info("api_key is none")
        # This will redirect to the / and produce a "Session expired" message
        raise bottle.HTTPResponse(body='', status=301, headers={ 'Location': '/'})
    userdict = db.validate_api_key(api_key)
    if not userdict:
        logging.info("api_key %s is invalid  ipaddr=%s request.url=%s",
                     api_key,request.environ.get('REMOTE_ADDR'),request.url)
        auth.clear_cookie()
        # This will produce a "Session expired" message
        if request.url.endswith("/error"):
            raise bottle.HTTPResponse(body='', status=301, headers={ 'Location': '/logout'})
        raise bottle.HTTPResponse(body='', status=301, headers={ 'Location': '/error'})
    return userdict

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
# Movie APIs. All of these need to only be POST to avoid an api_key from being written into the logfile
##


@api.route('/new-movie', method='POST')
def api_new_movie():
    """Creates a new movie for which we can upload frame-by-frame or all at once.
    Moving can appear here as a file or as a base64 encoded data.
    If no movie is provided, we return a presigned URL that can be used to post the movie to S3 or to the
    /upload-movie API (below).

    :param api_key: the user's api_key
    :param title: The movie's title
    :param description: The movie's description
    :param movie_data: If present, the movie file itself
    :param movie_base64_data - if present, the movie file, base64 encoded
    :param movie_data_sha256: If present, the SHA256. Signifies we want to upload by presigned URL
    :return: dict['movie_id'] - uploaded movie
             dict['movie_s3'] - s3:// if it is being uploaded to s3
             dict['upload_url'] - URL for uploading
    """

    # pylint: disable=unsupported-membership-test
    logging.info("api_new_movie")
    user_id    = get_user_id(allow_demo=False)    # require a valid user_id
    movie_data_sha256 = get('movie_data_sha256')
    movie_data = None
    movie_metadata = None
    movie_data_urn = None
    # First see if a file named movie was uploaded
    if 'movie_data' in request.files:
        with io.BytesIO() as f:
            request.files['movie_data'].save(f)
            movie_data = f.getvalue()
            if len(movie_data) > C.MAX_FILE_UPLOAD:
                return {'error': True, 'message': f'Upload larger than larger than {C.MAX_FILE_UPLOAD} bytes.'}
        logging.debug("api_new_movie: movie uploaded as a file")

    #
    # It turns out that you can upload arbitrary data in an HTTP POST
    # provided that it is a file upload, but not in POST fields. That
    # is why I it has to be base64-encoded.
    if movie_data is None:
        movie_base64_data = request.forms.get('movie_base64_data',None)
        if movie_base64_data is not None:
            movie_data = base64.b64decode(movie_base64_data)
        logging.debug("api_new_movie: movie_base64_data from request.forms.get")
    else:
        logging.debug("api_new_movie: movie_base64_data is None")

    if movie_data is not None:
        if len(movie_data) > C.MAX_FILE_UPLOAD:
            logging.debug("api_new_movie: movie length %s bigger than %s",len(movie_data), C.MAX_FILE_UPLOAD)
            return {'error': True, 'message': f'Upload larger than larger than {C.MAX_FILE_UPLOAD} bytes.'}

        movie_data_sha256 = db_object.sha256(movie_data)
        movie_metadata = tracker.extract_movie_metadata(movie_data=movie_data)
    ret = {'error':False}

    if movie_data_sha256:
        object_name = movie_data_sha256 + C.MOVIE_EXTENSION
        movie_data_urn        = db_object.make_urn(object_name=object_name)
        ret['presigned_post'] = db_object.make_presigned_post(urn=movie_data_urn,
                                                              mime_type='video/mp4',
                                                              sha256=movie_data_sha256)

    if movie_data is not None:
        assert movie_data_sha256 is not None
        assert movie_data_urn is not None
    ret['movie_id'] = db.create_new_movie(user_id=user_id,
                                   title=request.forms.get('title'),
                                   description=request.forms.get('description'),
                                   movie_data=movie_data,
                                   movie_metadata = movie_metadata,
                                   movie_data_sha256 = movie_data_sha256,
                                   movie_data_urn = movie_data_urn )
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
    :param: key    - where the file gets uploaded
    :param: request.files[0] - the file!
    """
    scheme = get('scheme')
    key = get('key')
    #movie_mime_type = get('mime_type')
    movie_data_sha256 = get('sha256')
    with io.BytesIO() as f:
        request.files[0].save(f)
        movie_data = f.getvalue()
        if len(movie_data) > C.MAX_FILE_UPLOAD:
            return {'error': True, 'message': f'Upload larger than larger than {C.MAX_FILE_UPLOAD} bytes.'}
    if db_object.sha256(movie_data) != movie_data_sha256:
        return {'error': True, 'message':
                f'movie_data_sha256={movie_data_sha256} but post.sha256={db_object.sha256(movie_data)}'}
    urn = db_object.make_urn(object_name=key, scheme=scheme)
    db_object.write_object(urn, movie_data)
    return {'error':False,'message':'Upload ok.'}


@api.route('/get-movie-data', method=GET_POST)
def api_get_movie_data():
    """
    :param api_key:   authentication
    :param movie_id:  movie
    :param redirect_inline: - if True and we are redirecting, return "#REDIRECT url"
    :return:  IF MOVIE IS IN S3 - Redirect to a signed URL.
              IF MOVIE IS IN DB - The raw movie data as a movie.
    """
    try:
        movie_id = get_int('movie_id')
        movie = db.Movie(movie_id, user_id=get_user_id())
    except db.UnauthorizedUser as e:
        raise bottle.HTTPResponse(body=f'user={get_user_id()} movie_id={movie_id}', status=404) from e

    # If we have a movie, return it
    if movie.data is not None:
        bottle.response.set_header('Content-Type', movie.mime_type)
        return movie.data

    # Looks like we need a url
    url = movie.url()
    if get_bool('redirect_inline'):
        return "#REDIRECT " + url
    logging.info("Redirecting movie_id=%s to %s",movie.movie_id, url)
    return bottle.redirect(url)



@api.route('/get-movie-metadata', method=GET_POST)
def api_get_movie_metadata():
    """
    Gets the metadata for a specific movie and its last tracked frame
    :param api_key:   authentication
    :param movie_id:   movie
    """
    user_id = get_user_id()
    movie_id = get_int('movie_id')
    logging.info("get_movie_metadata() movie_id=%s user_id=%s",movie_id,user_id)
    if db.can_access_movie(user_id=user_id, movie_id=movie_id):
        metadata =  db.get_movie_metadata(user_id=user_id, movie_id=movie_id)[0]
        metadata['last_tracked_frame'] = db.last_tracked_frame(movie_id = movie_id)
        return {'error':False, 'metadata':fix_types(metadata)}


    return E.INVALID_MOVIE_ACCESS

@api.route('/get-movie-trackpoints',method=GET_POST)
def api_get_movie_trackpoints():
    """Downloads the movie trackpoints as a CSV
    :param api_key:   authentication
    :param movie_id:   movie
    :param: format - 'xlsx' or 'json'
    """
    if db.can_access_movie(user_id=get_user_id(), movie_id=get_int('movie_id')):
        # get_movie_trackpoints() returns a dictionary for each trackpoint.
        # we want a dictionary for each frame_number
        trackpoint_dicts = db.get_movie_trackpoints(movie_id=get_int('movie_id'))
        frame_numbers  = sorted( ( tp['frame_number'] for tp in trackpoint_dicts) )
        labels         = sorted( ( tp['label'] for tp in trackpoint_dicts) )
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


@api.route('/delete-movie', method=POST)
def api_delete_movie():
    """ delete a movie
    :param movie_id: the id of the movie to delete
    :param delete: 1 (default) to delete the movie, 0 to undelete the movie.
    """
    if db.can_access_movie(user_id=get_user_id(allow_demo=False),
                           movie_id=get_int('movie_id')):
        db.delete_movie(movie_id=get_int('movie_id'),
                        delete=get_bool('delete',True))
        return {'error': False}
    return E.INVALID_MOVIE_ACCESS


@api.route('/list-movies', method=POST)
def api_list_movies():
    return {'error': False, 'movies': fix_types(db.list_movies(user_id=get_user_id()))}


# pylint: disable=too-few-public-methods
class MovieTrackCallback:
    """Service class to create a callback instance to update the movie status"""
    def __init__(self, *, user_id, movie_id):
        self.user_id = user_id
        self.movie_id = movie_id
        self.movie_metadata = None
        self.last     = 0

    def notify(self, arg):
        max_frame = max( (obj['frame_number'] for obj in arg) )
        total_frames = self.movie_metadata['total_frames']
        message = f"Tracked frames {max_frame} of {total_frames}"

        if time.time() > self.last + C.NOTIFY_UPDATE_INTERVAL:
            logging.debug("MovieTrackCallback %s",message)
            db.set_metadata(user_id=self.user_id, set_movie_id=self.movie_id, prop='status', value=message)
            self.last = time.time()

    def done(self):
        db.set_metadata(user_id=self.user_id, set_movie_id=self.movie_id, prop='status', value=C.TRACKING_COMPLETED)

@task
def api_track_movie(*,user_id, movie_id, engine_name, engine_version, frame_start):
    """Generate trackpoints for a movie based on initial trackpoints stored in the database at frame_start.
    Stores new trackpoints in the datqbase. No longer renders new movie: that's now in render_tracked_movie
    """
    # Find trackpoints we are tracking or retracking
    input_trackpoints = db.get_movie_trackpoints(movie_id=movie_id)
    logging.debug("len(input_trackpoints)=%s",len(input_trackpoints))

    # If there are no trackpoints, we just go through the motions...

    # Write the movie to a tempfile, because OpenCV has to read movies from files.
    mtc = MovieTrackCallback(user_id = user_id, movie_id = movie_id)
    with tempfile.NamedTemporaryFile(suffix='.mp4',mode='wb') as infile:
        movie_data     = db.get_movie_data(movie_id=movie_id)
        movie_metadata = tracker.extract_movie_metadata(movie_data=movie_data)
        infile.write( movie_data  )
        infile.flush()

        # While I'm here, update the movie metadata
        for prop in ['fps','width','height','total_frames','total_bytes']:
            if prop in movie_metadata:
                db.set_metadata(user_id=user_id, set_movie_id=movie_id, prop=prop, value=movie_metadata[prop])


        # Track (or retrack) the movie and create the tracked movie
        # This creates an output file that has the trackpoints animated
        # and an array of all the trackpoints
        mtc.movie_metadata = db.get_movie_metadata(movie_id=movie_id, user_id=user_id)[0]
        tracked = tracker.track_movie(engine_name=engine_name,
                                      engine_version=engine_version,
                                      input_trackpoints = input_trackpoints,
                                      frame_start      = frame_start,
                                      moviefile_input  = infile.name,
                                      callback = mtc.notify)

    # Get new trackpoints for each frame and save them into the database
    output_trackpoints   = tracked['output_trackpoints']
    output_trackpoints_by_frame = defaultdict(list)
    for tp in output_trackpoints:
        output_trackpoints_by_frame[tp['frame_number']].append(tp)

    # Write all of the trackpoints by frame that were re-tracked
    for (frame_number,trackpoints) in output_trackpoints_by_frame.items():
        if frame_number >= frame_start:
            frame_id = db.create_new_frame(movie_id=movie_id, frame_number=frame_number)
            db.put_frame_trackpoints(frame_id = frame_id,
                                     trackpoints = trackpoints)
    mtc.done()                  # sets the status to tracking complete

@api.route('/track-movie-queue', method=GET_POST)
def api_track_movie_queue():
    """Tracks a movie that has been uploaded.
    :param api_key: the user's api_key
    :param movie_id: the movie to track; a new movie will be created
    :param frame_start: the frame to start tracking; frames 0..(frame_start-1) have track points copied.
    :param engine_name: string description tracking engine to use. May be omitted to get default engine.
    :param engine_version - string to describe which version number of engine to use. May be omitted for default version.
    :return: dict['error'] = True/False
             dict['message'] = message to display
             dict['frame_start'] = where the tracking started
    """

    # pylint: disable=unsupported-membership-test
    movie_id       = get_int('movie_id')
    user_id        = get_user_id(allow_demo=True)
    if not db.can_access_movie(user_id=user_id, movie_id=movie_id):
        return E.INVALID_MOVIE_ACCESS

    # Make sure we are not tracking a movie that is not an original movie
    movie_row = db.list_movies(user_id=user_id, movie_id=movie_id)
    assert len(movie_row)==1
    if movie_row[0]['orig_movie'] is not None:
        return E.MUST_TRACK_ORIG_MOVIE

    api_track_movie(user_id=user_id, movie_id=movie_id,
                    engine_name=get('engine_name'),
                    engine_version=get('engine_version'),
                    frame_start=get_int('frame_start'))

    # We return all the trackpoints to the client, although the client currently doesn't use them
    return {'error': False, 'message':'Tracking is queued'}


##
# Movie analysis API
#
@api.route('/new-movie-analysis', method=POST)
def api_new_movie_analysis():
    """Creates a new movie analysis
    :param api_key: the user's api_key
    :param movie_id: The movie to associate this movie analysis with
    :param engine_id: The engine used to create the analyis
    :param annotations: The movie analysis's annotations, that is, a JSON document containing analysis data
    """

    user_id  = get_user_id(allow_demo=False)
    movie_id = request.forms.get('movie_id')
    if not db.can_access_movie(user_id=user_id, movie_id=movie_id):
        return E.INVALID_MOVIE_ACCESS

    movie_analysis_id = db.create_new_movie_analysis(movie_id=movie_id,
                                                     engine_id=request.forms.get('engine_id'),
                                                     annotations=request.forms.get('annotations'))['movie_analysis_id']
    return {'error': False, 'movie_analysis_id': movie_analysis_id}


################################################################
### Frame API

@api.route('/new-frame', method=POST)
def api_new_frame():
    """Create a new frame and return its frame_id.
    If frame exists, just update the frame_data (if frame data is provided).
    Returns frame_id.
    :param: api_key  - api_key
    :param: movie_id - the movie
    :param: frame_number - the frame to create
    :param: frame_data - if provided, it's uploaded; otherwise we just enter the frame into the dfatabase if it doesn't exist
    :return: frame_id - that's what we care about

    """
    if not db.can_access_movie(user_id=get_user_id(allow_demo=False), movie_id=request.forms.get('movie_id')):
        return E.INVALID_MOVIE_ACCESS
    try:
        frame_data = base64.b64decode( request.forms.get('frame_base64_data'))
    except TypeError:
        frame_data = None
    frame_id = db.create_new_frame( movie_id = get_int('movie_id'),
                               frame_number = get_int('frame_number'),
                               frame_data = frame_data)
    assert isinstance( frame_id, int)
    return {'error': False, 'frame_id': frame_id}

def api_get_jpeg(*,frame_id=None, frame_number=None, movie_id=None):
    # is frame_id provided?
    if (frame_id is not None) and db.can_access_frame(user_id = get_user_id(), frame_id=frame_id):
        row =  db.get_frame(frame_id=frame_id)
        return row.get('frame_data',None)
    # Is there a movie we can access?
    if frame_number is not None and db.can_access_movie(user_id = get_user_id(), movie_id=movie_id):
        try:
            return tracker.extract_frame(movie_data = db.get_movie_data(movie_id = movie_id),
                                         frame_number = frame_number,
                                         fmt = 'jpeg')
        except ValueError as e:
            return bottle.HTTPResponse(status=500, body=f"frame number {frame_number} out of range: "+e.args[0])
    logging.info("fmt=jpeg but INVALID_FRAME_ACCESS with frame_id=%s and frame_number=%s and movie_id=%s",frame_id,frame_number,movie_id)
    return E.INVALID_FRAME_ACCESS


@api.route('/get-frame', method=GET_POST)
def api_get_frame():
    """
    Get a frame and its annotation from a movie. Return from the frame database. If not there, grab it from the movie

    :param api_key:   authentication
    :param movie_id:   movie
    :param frame_id:   just get by frame_id
    :param frame_number: get the frame by frame_number (starting with 0)
    :param format:     jpeg - just get the image;
                       json (default) - get the image (default), json annotation and trackpoints
                       // todo - frame_id - just get the frame_id

    :return: - either the image (as a JPEG) or a JSON object. With JSON, includes:
      error        = true or false
      message      - the message if there is an error
      movie_id     - the movie (always returned)
      frame_id     - the id of the frame (always returned)
      frame_number - the number of the frame (always returned)
      last_tracked_frame - the frame number of the highest frame with trackpoints
      annotations - a JSON object of annotations from the databsae.
      trackpoints - a list of the trackpoints
    """
    user_id      = get_user_id(allow_demo=True)
    frame_id     = get_int('frame_id')
    frame_number = get_int('frame_number')
    movie_id     = get_int('movie_id')
    fmt          = get('format', 'jpeg').lower()

    logging.debug("api_get_frame fmt=%s movie_id=%s frame_number=%s",fmt,movie_id,frame_number)
    if fmt not in ['jpeg', 'json']:
        logging.info("fmt is not in jpeg or json")
        return E.INVALID_FRAME_FORMAT

    if not db.can_access_movie(user_id=user_id, movie_id=movie_id):
        logging.info("User %s cannot access movie_id %s",user_id, movie_id)
        return E.INVALID_MOVIE_ACCESS

    if fmt=='jpeg':
        # Return just the JPEG for the frame, with no metadata
        bottle.response.set_header('Content-Type', MIME.JPEG)
        return api_get_jpeg(frame_id=frame_id, frame_number=frame_number, movie_id=movie_id)

    # See if get_frame can find the movie frame
    ret = db.get_frame(movie_id=movie_id, frame_id = frame_id, frame_number=frame_number)
    if ret:
        # Get any frame annotations and trackpoints
        ret['annotations'] = db.get_frame_annotations(frame_id=ret['frame_id'])
        ret['trackpoints'] = db.get_frame_trackpoints(frame_id=ret['frame_id'])

    else:
        # the frame is not in the database, so we need to make it
        if frame_id is not None:
            return E.INVALID_FRAME_ID_DB
        frame_id = db.create_new_frame(movie_id = movie_id, frame_number = frame_number)
        ret = {'movie_id':movie_id,
               'frame_id':frame_id,
               'frame_number':frame_number}

    # If we do not have frame_data, extract it from the movie (but don't store in database)
    if ret.get('frame_data',None) is None:
        logging.debug('no frame_data provided. extracting movie_id=%s frame_number=%s',movie_id,frame_number)
        try:
            ret['frame_data'] = tracker.extract_frame(movie_data=db.get_movie_data(movie_id=movie_id),
                                                      frame_number=frame_number,
                                                      fmt='jpeg')
        except ValueError:
            return {'error':True,
                    'message':f'frame number {frame_number} is out of range'}

    # Convert the frame_data to a data URL
    ret['data_url'] = f'data:image/jpeg;base64,{base64.b64encode(ret["frame_data"]).decode()}'
    del ret['frame_data']

    ret['last_tracked_frame'] = db.last_tracked_frame(movie_id = movie_id)
    ret['error'] = False
    #
    # Need to convert all datetimes to strings.
    # We then return the dictionary, which bottle runs json.dumps() on
    # and returns MIME type of "application/json"
    # JQuery will then automatically decode this JSON into a JavaScript object,
    # without having to call JSON.parse()
    return fix_types(ret)

@api.route('/put-frame-analysis', method=POST)
def api_put_frame_analysis():
    """
    Writes analysis and trackpoints for specific frames; frame_id is required
    :param: api_key  - the api_key
    :param: frame_id - the frame.
    :param: movie_id - the movie
    :param: frame_number - the the frame
    :param: engine_name - the engine name (if you don't; new engine_id created automatically)
    :param: engine_version - the engine version.
    :param: annotations - JSON string, must be an array or a dictionary, if provided
    :param: trackpoints - JSON string, must be an array of trackpoints, if provided
    """
    frame_id  = get_int('frame_id')
    user_id   = get_user_id(allow_demo=True)
    logging.debug("put_frame_analysis. frame_id=%s user_id=%s",frame_id,user_id)
    if frame_id is None:
        frame_id = db.create_new_frame(movie_id=get_int('movie_id'), frame_number=get_int('frame_number'))
        logging.debug("frame_id is now %s",frame_id)
    if not db.can_access_frame(user_id=user_id, frame_id=frame_id):
        logging.debug("user %s cannot access frame_id %s",user_id, frame_id)
        return {'error':True, 'message':f'User {user_id} cannot access frame_id={frame_id}'}
    annotations=get_json('annotations')
    trackpoints=get_json('trackpoints')
    logging.debug("put_frame_analysis. frame_id=%s annotations=%s trackpoints=%s",frame_id,annotations,trackpoints)
    if annotations is not None:
        db.put_frame_annotations(frame_id=frame_id,
                                 annotations=annotations,
                                 engine_name=get('engine_name'),
                                 engine_version=get('engine_version'))
    if trackpoints is not None:
        db.put_frame_trackpoints(frame_id=frame_id, trackpoints=trackpoints)
    return {'error': False, 'message':'Analysis recorded.'}


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

"""
db.get_metadata() not implemented ye.
@api.route('/get-metadata', method='POST')
def api_get_metadata():
    gmovie_id = get_bool('get_movie_id')
    guser_id  = get_bool('get_user_id')

    if (gmovie_id is None) and (guser_id is None):
        return {'error': True, 'result': 'Either get_movie_id or get_user_id is required'}

    return {'error': False, 'result': db.get_metadata(user_id=get_user_id(),
                                                      get_movie_id=gmovie_id,
                                                      get_user_id=guser_id,
                                                      property=request.forms.get('property'),
                                                      value=request.forms.get('value'))}
"""


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
    """Demo for reporting python version. Allows us to validate we are using Python3.
    Run the dictionary below through the VERSION_TEAMPLTE with jinja2.
    """
    logging.debug("api_ver")
    print("api_ver")
    return {'__version__': __version__, 'sys_version': sys.version}


################################################################
##
## Demo and debug
##
@api.route('/add', method=GET_POST)
def api_add():
    a = get_float('a')
    b = get_float('b')
    try:
        return {'result': a+b, 'error': False}
    except (TypeError, ValueError):
        return {'error': True, 'message': 'arguments malformed'}
