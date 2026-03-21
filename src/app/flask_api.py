"""
API

TODO - all get_user_id() should be replaced with get_user_dict() and then the userdict should be passed around so that we don't need another query.


"""
import json
import sys
import smtplib
import io
import csv
from collections import defaultdict


from flask import Blueprint, request, make_response, current_app, jsonify
from validate_email_address import validate_email

from . import config_check
from . import odb
from . import mailer
from . import apikey
from .apikey import get_user_api_key, get_user_dict, in_demo_mode
from .auth import AuthError,EmailNotInDatabase
from .constants import C, E, POST, GET_POST, __version__, logger, log_level, printable80
from .odb import (
    InvalidAPI_Key,
    InvalidMovie_Id,
    USER_ID,
    MOVIE_ID,
    COURSE_ID,
    MOVIE_ZIPFILE_URN,
    MOVIE_ZIPFILE_URL,
    MOVIE_TRACED_URN,
    MOVIE_TRACED_URL,
    MOVIE_METADATA_BULK_PROPS,
    MOVIE_ROTATION,
    MOVIE_STATUS,
    MOVIE_STATE_TRACING_COMPLETED,
    DDBO,
    UnauthorizedUser,
    clear_movie_tracking,
)
from .s3_presigned import (
    make_object_name,
    make_urn,
    make_signed_url,
    make_presigned_post,
)
from .odb_movie_data import (
    delete_movie,
)


api_bp = Blueprint('api', __name__)

################################################################
### Handle invalid apikey exceptions
@api_bp.errorhandler(InvalidAPI_Key)
def invalid_api_key(ex):
    logger.info("invalid_api_key(%s)", ex)
    resp = make_response(jsonify(E.INVALID_API_KEY), 403)
    resp.set_cookie(apikey.cookie_name(), '', expires=0, path='/')
    return resp

@api_bp.errorhandler(UnauthorizedUser)
def unauthorized_user(ex):
    logger.info("UnauthorizedUser(%s)",ex)
    return E.INVALID_MOVIE_ACCESS, 403


################################################################
# define get(), which gets a variable from either the forms request or the query string
def get(key, default=None):
    # If we are logging, don't log super long values... (like movie uploads)
    if log_level=='DEBUG':
        logger.debug("request.values=%s",printable80(request.values))
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
    logger.debug("get_int key=%s get(key)=%s",key,get(key))
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
        logger.info("demo mode blocks requested action.")
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
        logger.info("email not valid: %s", email)
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
        logger.info("email not in database: %s",email)
        return E.INVALID_EMAIL
    link_html = f"<p/><p>You can also log in by clicking this link: <a href='/list?api_key={new_api_key}'>login</a></p>"
    try:
        mailer.send_links(email=email, planttracer_endpoint=planttracer_endpoint, new_api_key=new_api_key)
        ret = {'error': False, 'message': 'Registration key sent to '+email+link_html, 'user_id':user_id}
    except mailer.InvalidMailerConfiguration:
        logger.error("Mailer reports Mailer not properly configured.")
        ret =  {'error':True, 'message':'Mailer not properly configured (InvalidMailerConfiguration).'+link_html}
    except mailer.NoMailerConfiguration:
        logger.error("Mailer reports no mailer configured.")
        ret =  {'error':True, 'message':'Mailer not properly configured (NoMailerConfiguration).'+link_html}
    except smtplib.SMTPAuthenticationError:
        logger.error("Mailer reports smtplib.SMTPAuthenticationError.")
        ret = {'error':True, 'message':'Mailer reports smtplib.SMTPAuthenticationError.'+link_html}
    return ret

def send_link(*, email, planttracer_endpoint):
    new_api_key = odb.make_new_api_key(email=email)
    if not new_api_key:
        logger.info("email not in database: %s",email)
        raise EmailNotInDatabase(email)
    mailer.send_links(email=email, planttracer_endpoint=planttracer_endpoint, new_api_key=new_api_key)


@api_bp.route('/resend-link', methods=GET_POST)
def api_send_link():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.values.get('email')
    planttracer_endpoint = request.values.get('planttracer_endpoint')
    logger.info("resend-link email=%s planttracer_endpoint=%s",email,planttracer_endpoint)
    if not validate_email(email, check_mx=C.CHECK_MX):
        logger.info("email not valid: %s", email)
        return E.INVALID_EMAIL
    try:
        send_link(email=email, planttracer_endpoint=planttracer_endpoint)
    except EmailNotInDatabase:
        return E.INVALID_EMAIL
    except mailer.NoMailerConfiguration:
        logger.error("no mailer configuration")
        return E.NO_MAILER_CONFIGURATION
    except mailer.InvalidMailerConfiguration as e:
        logger.error("invalid mailer configuration: %s type(e)=%s",e,type(e))
        return E.INVALID_MAILER_CONFIGURATION
    return {'error': False, 'message': 'If you have an account, a link was sent. If you do not receive a link within 60 seconds, you may need to <a href="/register">register</a> your email address.'}

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
        logger.error("no mailer configuration")
        return E.NO_MAILER_CONFIGURATION
    except mailer.InvalidMailerConfiguration as e:
        logger.error("invalid mailer configuration: %s",e)
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
             dict['presigned_post'] - the post to use for uploading the movie to the final S3 key.
             After upload the client calls Lambda start-processing; then the movie is available at movie_data_urn.
    """
    # pylint: disable=unsupported-membership-test
    logger.info("api_new_movie")
    origin = f"{request.scheme}://{request.host}"
    upload_ok, upload_msg = config_check.check_s3_upload_readiness(origin)
    if not upload_ok:
        return jsonify({'error': True, 'message': upload_msg}), 503
    user_id    = get_user_id(allow_demo=False)    # require a valid user_id
    user       = odb.get_user(user_id)
    movie_data_sha256 = get('movie_data_sha256')

    if (movie_data_sha256 is None) or (len(movie_data_sha256)!=64):
        return {'error':True,'message':'Movie SHA256 not provided or is invalid. Uploaded failed.'}

    ret = {'error': False}

    research_use = 1 if get('research_use') == '1' else 0
    credit_by_name = 1 if get('credit_by_name') == '1' else 0
    attribution_name = (request.values.get('attribution_name') or '').strip() or None
    if attribution_name is not None:
        attribution_name = attribution_name[:256]
    if credit_by_name == 0:
        attribution_name = None

    ret[MOVIE_ID] = odb.create_new_movie(user_id=user_id,
                                         course_id=user['primary_course_id'],
                                         title=request.values.get('title'),
                                         description=request.values.get('description'),
                                         research_use=research_use,
                                         credit_by_name=credit_by_name,
                                         attribution_name=attribution_name)

    oname = make_object_name(course_id=odb.course_id_for_movie_id(ret[MOVIE_ID]),
                             movie_id=ret[MOVIE_ID],
                             ext=C.MOVIE_EXTENSION)
    movie_data_urn = make_urn(object_name=oname)
    odb.set_movie_data_urn(movie_id=ret[MOVIE_ID], movie_data_urn=movie_data_urn)

    # Always upload to final key
    upload_urn = movie_data_urn
    ret['presigned_post'] = make_presigned_post(
        urn=upload_urn,
        mime_type='video/mp4',
        sha256=movie_data_sha256,
        research_use=str(research_use),
        credit_by_name=str(credit_by_name),
        attribution_name=attribution_name or '')
    return ret

def set_movie_metadata(*, user_id=odb.ROOT_USER_ID, set_movie_id, movie_metadata):
    """Update the movie metadata."""
    for prop in MOVIE_METADATA_BULK_PROPS:
        if prop in movie_metadata:
            logger.warning("Setting %s in %s; it would be better to do all sets at once",prop, set_movie_id)
            odb.set_metadata(user_id=user_id, set_movie_id=set_movie_id, prop=prop, value=movie_metadata[prop])


################################################################
## Movie editing
## Rotation and zip are done only in Lambda (no full movie scan on VM).

@api_bp.route('/edit-movie', methods=POST)
def api_edit_movie():
    """Request movie rotation. VM only updates rotation_steps.

    :param api_key: user authentication
    :param movie_id: the movie to edit
    :param action: must be 'rotate90cw'
    :param rotation_steps: 1–3; total 90° rotations. Client debounces and sends one request.
    Lambda performs rotate and metadata update (width/height swap). Zip is built when user opens Analyze.
    """
    movie_id = get_movie_id()
    user_id = get_user_id(allow_demo=False)
    odb.can_access_movie(user_id=user_id, movie_id=movie_id)

    action = get("action")
    if action != 'rotate90cw':
        return E.INVALID_EDIT_ACTION

    new_rotation = ((get_int(MOVIE_ROTATION,0) or 0) + 90) % 360
    clear_movie_tracking(movie_id)
    ddbo = DDBO()
    ddbo.update_table(ddbo.movies, movie_id, {MOVIE_ROTATION: new_rotation})
    return {"error": False}


@api_bp.route('/delete-movie', methods=POST)
def api_delete_movie():
    """ delete a movie
    :param api_key: - the User's API key.
    :param movie_id: the id of the movie to delete
    :param delete: 1 (default) to delete the movie, 0 to undelete the movie.
    """
    movie = odb.can_access_movie(user_id=get_user_id(allow_demo=False),
                                 movie_id=get_movie_id())
    delete_movie(movie_id=movie[MOVIE_ID], delete=get_bool('delete',True))
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

    movie = odb.can_access_movie(user_id=user_id, movie_id=movie_id)
    movie_metadata = odb.get_movie_metadata(movie_id=movie[MOVIE_ID], get_last_frame_tracked=True)

    # Return only stored metadata; do not generate or write metadata here.
    # Width/height are set when the first frame is served (Lambda get-frame) or by Lambda (rotate-and-zip).

    # If we have a movie_zipfile_urn, create a signed url (this can't be stored in the database...)
    if movie_metadata.get(MOVIE_ZIPFILE_URN, None):
        movie_metadata[MOVIE_ZIPFILE_URL] = make_signed_url(urn=movie_metadata[MOVIE_ZIPFILE_URN])

    # If we have a movie_traced_urn, create a signed url (this can't be stored in the database...)
    if movie_metadata.get(MOVIE_TRACED_URN, None):
        movie_metadata[MOVIE_TRACED_URL] = make_signed_url(urn=movie_metadata[MOVIE_TRACED_URN])

    ret = {C.API_KEY_ERROR: False, C.API_KEY_METADATA: movie_metadata}

    # If status TRACKING_COMPLETED_FLAG and the user has requested to get all trackpoints,
    # then get all the trackpoints.
    tracking_completed = movie_metadata.get(MOVIE_STATUS, '') == MOVIE_STATE_TRACING_COMPLETED
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
        ret[C.API_KEY_FRAMES] = defaultdict(dict)
        tpts = odb.get_movie_trackpoints(movie_id=movie_id,
                                         frame_start=frame_start,
                                         frame_count=frame_count)
        for tpt in tpts:
            frame = ret[C.API_KEY_FRAMES][tpt['frame_number']]
            if C.API_KEY_MARKERS not in frame:
                frame[C.API_KEY_MARKERS] = []
            frame[C.API_KEY_MARKERS].append(tpt)

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
    movie = odb.can_access_movie(user_id=get_user_id(), movie_id=movie_id)

    # NOTE - getting the movie should (soon) get all the trackpoints, as they will all be stored together
    # get_movie_trackpoints() returns a dictionary for each trackpoint.
    # we want a dictionary for each frame_number
    trackpoint_dicts = odb.get_movie_trackpoints(movie_id=movie[MOVIE_ID])
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
    logger.debug("fieldnames=%s",fieldnames)

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

@api_bp.route('/config-check', methods=GET_POST)
def api_config_check():
    """Return DynamoDB, S3 CORS, and S3 bucket region check results as JSON (no auth required)."""
    origin = f"{request.scheme}://{request.host}"
    d_ok, d_msg = config_check.check_dynamodb()
    c_ok, c_msg = config_check.check_s3_cors(origin)
    r_ok, r_msg = config_check.check_s3_bucket_region()
    return jsonify({
        'dynamodb_ok': d_ok,
        'dynamodb_message': d_msg,
        'cors_ok': c_ok,
        'cors_message': c_msg,
        'bucket_region_ok': r_ok,
        'bucket_region_message': r_msg,
    })


################################################################
################################################################
## Tracking: VM does not run tracking; client uses Lambda (see lambda-resize).

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

    NOTE: This can be made much more efficient. We should only be getting the movie data ONCE from dynamoDB...
    """
    logger.debug("log_level=%s", log_level)
    logger.debug("api_put_frame_trackpoints")
    user_id  = get_user_id(allow_demo=False)
    movie_id = get_movie_id()
    frame_number = get_int('frame_number')
    trackpoints = get_json('trackpoints')
    movie = odb.can_access_movie(user_id=user_id, movie_id=movie_id)
    if log_level=='DEBUG':
        logger.debug("put_frame_analysis. user_id=%s movie_id=%s frame_number=%s",user_id,movie[MOVIE_ID],frame_number)
        for tp in trackpoints:
            logger.debug("%s",tp)
    odb.put_frame_trackpoints(movie_id=movie_id, frame_number=frame_number, trackpoints=trackpoints)

    return {'error': False, 'message':f'trackpoints recorded: {len(trackpoints)} '}


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
