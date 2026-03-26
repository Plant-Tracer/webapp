"""
Constants are created in classes so we can import the class and don't have to import each constant.
"""

#pylint: disable=too-few-public-methods,disable=invalid-name

import logging
import os

__version__ = '0.9.7.2'

# these aren't strictly constants...
log_level = os.getenv("LOG_LEVEL","INFO").upper()
logger = logging.getLogger(__name__)

def printable80(d):
    values = dict(d)
    for (k,v) in values.items():
        if len(str(v))>80:
            values[k] = str(v)[0:80]+"..."
    return values


# but these are:
GET=['GET']
POST=['POST']
GET_POST = ['GET','POST']


class C:
    """Constants"""
    # AWS variables (used by boto3)
    AWS_REGION = 'AWS_REGION'
    AWS_PROFILE = 'AWS_PROFILE'
    TABLE_CREATE_SLEEP_TIME = 1.0 # in seconds

    # Environment variables for AWS Configuration
    # SERVER_EMAIL: sender address for all outgoing email (env var name; value default admin@planttracer.com, configured in SES)
    SERVER_EMAIL = 'SERVER_EMAIL'
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
    TEST_ENDPOINT_URL_S3 = 'http://localhost:9000'
    TEST_ENDPOINT_URL_DYNAMODB = 'http://localhost:8000'

    # Confs
    DEFAULT_MAX_ENROLLMENT = 100
    LOG_MAX_RECORDS = 1024
    MOVIE_MAX_WIDTH = 640
    MOVIE_JPEG_QUALITY = 85
    API_KEY_COOKIE_MAX_AGE = 60*60*24*180

    # Logging
    LOGGING_CONFIG='%(asctime)s  %(filename)s:%(lineno)d %(levelname)s: %(message)s'
    LOGGING_LEVEL=logging.WARNING

    # Demo mode
    # special key (must begin with an 'a' and be 33 characters)
    DEMO_MODE_API_KEY  = 'a123456789012345678901234567890bc'

    # Other
    LOGIN_EMAIL_TEMPLATE_FNAME = 'email_login.html'
    COURSE_CREATED_EMAIL_TEMPLATE_FNAME = 'email_course_created.html'
    MAX_FUNC_RETURN_LOG = 4096      # do not log func_return larger than this
    FAVICON = 'icon.png'
    API_BASE='API_BASE'
    STATIC_BASE='STATIC_BASE'
    MAX_FILE_UPLOAD = 1024*1024*256
    MAX_MOVIE_FRAMES = 1e6            # max possible frames in a movie
    NOTIFY_UPDATE_INTERVAL = 5.0
    TRACK_DELAY = 'TRACK_DELAY'
    CHECK_MX = False                # True didn't work
    DEFAULT_GET_TIMEOUT = 10
    YES = 'YES'
    NO = 'NO'
    MOVIE_EXTENSION = ".mov"
    MOVIE_PROCESSED_EXTENSION = '_processed.mp4'  # rotated/scaled movie written by Lambda (rotate or tracking)
    ZIP_MOVIE_EXTENSION = '_mp4.zip'
    # Single place for analysis/shrunk frame size (zip frames and get-frame?size=analysis).
    ANALYSIS_FRAME_MAX_WIDTH = 640
    ANALYSIS_FRAME_MAX_HEIGHT = 480
    JPEG_EXTENSION = ".jpg"
    PUT = 'put'
    GET = 'get'
    SCHEME_S3 = 's3'
    SCHEME_DB = 'db'
    # S3 object key templates (course_id/movie_id{ext} and course_id/movie_id/frame_number{ext})
    MOVIE_TEMPLATE = "{course_id}/{movie_id}{ext}"
    FRAME_TEMPLATE = "{course_id}/{movie_id}/{frame_number:06d}{ext}"
    SCHEME_DB_MAX_OBJECT_LEN = 16_000_000
    REDIRECT_FOUND = 302
    API_KEY_COOKIE_BASE = 'api_key'

    # Lambda/health response
    STATUS_OK = 'ok'
    STATUS_UNAVAILABLE = 'unavailable'
    KEY_STATUS = 'status'
    KEY_REASON = 'reason'

    # API response keys (JSON body)
    API_KEY_ERROR = 'error'
    API_KEY_MESSAGE = 'message'
    API_KEY_METADATA = 'metadata'
    API_KEY_FRAMES = 'frames'
    API_KEY_MARKERS = 'markers'

    # Movie metadata prop names for type coercion (schema.fix_movie_prop_value); single source of truth
    MOVIE_PROPS_INT = (
        'published', 'deleted', 'version', 'last_frame_tracked', 'research_use', 'credit_by_name',
        'date_uploaded', 'total_bytes', 'total_frames', 'width', 'height', 'rotation_steps',
    )
    MOVIE_PROPS_STR = ('fps',)

class MIME:
    """MIME Types"""
    JPEG = 'image/jpeg'
    MP4 = 'video/quicktime'
    ZIP = 'application/zip'

class E:
    """Error constants"""
    def __init__(self):
        raise RuntimeError("Do not instantiate this class. It exists solely for its static constants.")
    CALC_RESULTS_PARAM_INVALID = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'All coordinates must be provided (not none) and time elapsed must be greater than zero.'}
    NO_FILE_PARAMETER = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'upload request a file parameter named "file".'}
    INVALID_API_KEY = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'Invalid api_key'}
    INVALID_COURSE_ACCESS = { C.API_KEY_ERROR: True, C.API_KEY_MESSAGE:'User is not authorized to manipulate course.'}
    INVALID_COURSE_ID = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'There is no course for that course ID'}
    INVALID_COURSE_KEY = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'There is no course for that course key.'}
    INVALID_EMAIL = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'Invalid email address'}
    INVALID_FRAME_NUMBER = { C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'Invalid frame number'}
    INVALID_FRAME_ACCESS = { C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'User does not have access to requested movie frame.'}
    INVALID_FRAME_FORMAT = { C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'Format must be "json" or "jpeg".'}
    INVALID_MOVIE_ACCESS = { C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'User does not have access to requested movie.'}
    INVALID_MOVIE_FRAME = { C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'Could not retrieve the movie frame.'}
    INVALID_MOVIE_ID = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'movie_id is invalid or missing'}
    NO_MOVIE_DATA = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'No data is available for that movie_id'}
    INVALID_EDIT_ACTION = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE:'invalid movie edit action'}
    INVALID_REQUEST_JPEG = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE:'Invalid request when requesting JPEG'}
    NO_EMAIL_REGISTER = {C.API_KEY_ERROR: True,C.API_KEY_MESSAGE:'could not register email addresses.'}
    NO_REMAINING_REGISTRATIONS = { C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: 'That course has no remaining registrations. Please contact your faculty member.'}
    TRACK_FRAMES_SAME = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE:'The frames references in api_get_frame are the same frame'}
    FRAME1_IS_NONE = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE:'Frame1 in track_frame is None'}
    NO_TRACKPOINTS = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE:'No trackpoints provided for tracking operation'}
    INVALID_MAILER_CONFIGURATION = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE:'Invalid mailer configuration. Please review error.log on server for more information'}
    MUST_TRACK_ORIG_MOVIE = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE:'Must track original movies'}
    NO_MAILER_CONFIGURATION = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE:'Email cannot be sent as no mailer has been configured.'}
    FRAME_START_NO_FRAME_COUNT = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE:'frame_start provided but frame_count is not provided'}
    FRAME_COUNT_GT_0 = {C.API_KEY_ERROR: True, C.API_KEY_MESSAGE:'frame_count must be greater than 0'}


#pylint: enable=too-few-public-methods
