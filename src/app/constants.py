"""
Constants are created in classes so we can import the class and don't have to import each constant.
"""

#pylint: disable=too-few-public-methods,disable=invalid-name

import logging
import os

__version__ = '0.9.6'

# these aren't strictly constants...
log_level = os.getenv("LOG_LEVEL","INFO").upper()
logger = logging.getLogger(__name__)

def printable80(d):
    values = dict(d)
    for (k,v) in values:
        if len(str(v))>80:
            k[v] = str(v)[0:80]+"..."
    return values


# but these are:
GET=['GET']
POST=['POST']
GET_POST = ['GET','POST']



class C:
    """Constants"""
    # AWS variables (used by boto3)
    AWS_DEFAULT_REGION = 'AWS_DEFAULT_REGION'
    AWS_PROFILE = 'AWS_PROFILE'
    TABLE_CREATE_SLEEP_TIME = 1.0 # in seconds

    # Environment variables for AWS Configuration
    PROJECT_EMAIL = 'admin@planttracer.com'
    PLANTTRACER_S3_BUCKET = 'PLANTTRACER_S3_BUCKET'
    PLANTTRACER_API_BASE='PLANTTRACER_API_BASE'
    PLANTTRACER_STATIC_BASE='PLANTTRACER_STATIC_BASE'
    DEMO_COURSE_ID = 'DEMO_COURSE_ID'                         # run in demo mode with this course_id
    FFMPEG_PATH = 'FFMPEG_PATH'
    AWS_ACCESS_KEY_ID = 'AWS_ACCESS_KEY_ID'
    AWS_SECRET_ACCESS_KEY = 'AWS_SECRET_ACCESS_KEY'
    AWS_ENDPOINT_URL = 'AWS_ENDPOINT_URL'
    AWS_ENDPOINT_URL_DYNAMODB = 'AWS_ENDPOINT_URL_DYNAMODB' # official name
    AWS_ENDPOINT_URL_S3 = 'AWS_ENDPOINT_URL_S3' # official name
    DYNAMODB_TABLE_PREFIX = 'DYNAMODB_TABLE_PREFIX'
    PLANTTRACER_CREDENTIALS = 'PLANTTRACER_CREDENTIALS' # where the .ini file is with [smtp] and [imap] config
    SMTPCONFIG_ARN = 'SMTPCONFIG_ARN'                   # if set, the ARN of the AWS Secrets manager for the SMTP config
    SMTPCONFIG_JSON = 'SMTPCONFIG_JSON'                 # if set, a JSON dictionary of the SMTP configuration

    # test values
    TEST_ACCESS_KEY_ID = 'minioadmin'
    TEST_SECRET_ACCESS_KEY = 'minioadmin'
    TEST_PLANTTRACER_S3_BUCKET = 'planttracer-local'
    TEST_ENDPOINT_URL_S3 = 'http://localhost:9100'
    TEST_ENDPOINT_URL_DYNAMODB = 'http://localhost:8010'

    DEFAULT_MAX_ENROLLMENT = 100
    LOG_MAX_RECORDS = 1024

    # Logging
    LOGGING_CONFIG='%(asctime)s  %(filename)s:%(lineno)d %(levelname)s: %(message)s'
    LOGGING_LEVEL=logging.WARNING

    # Demo mode
    # special key (must begin with an 'a' and be 33 characters)
    DEMO_MODE_API_KEY  = 'a123456789012345678901234567890bc'

    # Other
    EMAIL_TEMPLATE_FNAME = 'email.txt'
    MAX_FUNC_RETURN_LOG = 4096      # do not log func_return larger than this
    FAVICON = 'icon.png'
    API_BASE='API_BASE'
    STATIC_BASE='STATIC_BASE'
    TRACKING_COMPLETED='TRACKING COMPLETED' # keep case; it's used as a flag
    MAX_FILE_UPLOAD = 1024*1024*256
    MAX_FRAMES = 1e6            # max possible frames in a movie
    NOTIFY_UPDATE_INTERVAL = 5.0
    TRACK_DELAY = 'TRACK_DELAY'
    CHECK_MX = False                # True didn't work
    DEFAULT_GET_TIMEOUT = 10
    YES = 'YES'
    NO = 'NO'
    MOVIE_EXTENSION = ".mov"
    ZIP_MOVIE_EXTENSION = '_mp4.zip'
    JPEG_EXTENSION = ".jpg"
    PUT = 'put'
    GET = 'get'
    SCHEME_S3 = 's3'
    SCHEME_DB = 'db'
    SCHEME_DB_MAX_OBJECT_LEN = 16_000_000
    REDIRECT_FOUND = 302
    API_KEY_COOKIE_BASE = 'api_key'
    API_KEY_COOKIE_MAX_AGE = 60*60*24*180

class MIME:
    """MIME Types"""
    JPEG = 'image/jpeg'
    MP4 = 'video/quicktime'
    ZIP = 'application/zip'

class E:
    """Error constants"""
    def __init__(self):
        raise RuntimeError("Do not instantiate this class. It exists solely for its static constants.")
    CALC_RESULTS_PARAM_INVALID = { 'error': True, 'message': 'All coordinates must be provided (not none) and time elapsed must be greater than zero.'}
    NO_FILE_PARAMETER = {'error':True, 'message':'upload request a file parameter named "file".'}
    INVALID_API_KEY = {'error': True, 'message': 'Invalid api_key'}
    INVALID_COURSE_ACCESS = { 'error':True, 'message':'User is not authorized to manipulate course.'}
    INVALID_COURSE_ID = {'error': True, 'message': 'There is no course for that course ID'}
    INVALID_COURSE_KEY = {'error': True, 'message': 'There is no course for that course key.'}
    INVALID_EMAIL = {'error': True, 'message': 'Invalid email address'}
    INVALID_FRAME_NUMBER = { 'error': True, 'message': 'Invalid frame number'}
    INVALID_FRAME_ACCESS = { 'error': True, 'message': 'User does not have access to requested movie frame.'}
    INVALID_FRAME_FORMAT = { 'error': True, 'message': 'Format must be "json" or "jpeg".'}
    INVALID_MOVIE_ACCESS = { 'error': True, 'message': 'User does not have access to requested movie.'}
    INVALID_MOVIE_FRAME = { 'error': True, 'message': 'Could not retrieve the movie frame.'}
    INVALID_MOVIE_ID = {'error': True, 'message': 'movie_id is invalid or missing'}
    NO_MOVIE_DATA = {'error': True, 'message': 'No data is available for that movie_id'}
    INVALID_EDIT_ACTION = {'error' : True, 'message':'invalid movie edit action'}
    INVALID_REQUEST_JPEG = {'error': True, 'message':'Invalid request when requesting JPEG'}
    NO_EMAIL_REGISTER = {'error':True,'message':'could not register email addresses.'}
    NO_REMAINING_REGISTRATIONS = { 'error': True, 'message': 'That course has no remaining registrations. Please contact your faculty member.'}
    TRACK_FRAMES_SAME = {'error':True, 'message':'The frames references in api_get_frame are the same frame'}
    FRAME1_IS_NONE = {'error':True, 'message':'Frame1 in track_frame is None'}
    NO_TRACKPOINTS = {'error':True, 'message':'No trackpoints provided for tracking operation'}
    INVALID_MAILER_CONFIGURATION = {'error':True, 'message':'Invalid mailer configuration. Please review error.log on server for more information'}
    MUST_TRACK_ORIG_MOVIE = {'error':True, 'message':'Must track original movies'}
    NO_MAILER_CONFIGURATION = {'error':True, 'message':'Email cannot be sent as no mailer has been configured.'}
    FRAME_START_NO_FRAME_COUNT = {'error':True, 'message':'frame_start provided but frame_count is not provided'}
    FRAME_COUNT_GT_0 = {'error':True, 'message':'frame_count must be greater than 0'}


#pylint: enable=too-few-public-methods
