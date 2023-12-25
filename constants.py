"""
Constants are created in classes so we can import the class and don't have to import each constant.
"""

#pylint: disable=too-few-public-methods
class C:
    """Constants"""
    DBCREDENTIALS_PATH = 'DBCREDENTIALS_PATH'
    CREDENTIALS_INI = 'etc/credentials.ini'


class Engines:
    """Engines"""
    NULL = "NULL"               # points are copied from input to output
    MANUAL = "MANUAL"           # analysis entered by a person
    CV2 = "CV2"                 # first CV2 algorithm

class MIME:
    """MIME Types"""
    JPEG = 'image/jpeg'
    MP4 = 'video/quicktime'

class E:
    """Error constants"""
    def __init__(self):
        raise RuntimeError("Do not instantiate this class. It exists solely for its static constants.")
    CALC_RESULTS_PARAM_INVALID = { 'error': True, 'message': 'All coordinates must be provided (not none) and time elapsed must be greater than zero.'}
    INVALID_API_KEY = {'error': True, 'message': 'Invalid api_key'}
    INVALID_COURSE_ACCESS = { 'error':True, 'message':'User is not authorized to manipulate course.'}
    INVALID_COURSE_KEY = {'error': True, 'message': 'There is no course for that course key.'}
    INVALID_EMAIL = {'error': True, 'message': 'Invalid email address'}
    INVALID_FRAME_ACCESS = { 'error': True, 'message': 'User does not have access to requested movie frame.'}
    INVALID_FRAME_FORMAT = { 'error': True, 'message': 'Format must be "json" or "jpeg".'}
    INVALID_FRAME_ID = {'error': True, 'message': 'frame_id is invalid or missing'}
    INVALID_MOVIE_ACCESS = { 'error': True, 'message': 'User does not have access to requested movie.'}
    INVALID_MOVIE_FRAME = { 'error': True, 'message': 'Could not retrieve the movie frame.'}
    INVALID_MOVIE_ID = {'error': True, 'message': 'movie_id is invalid or missing'}
    INVALID_REQUEST_JPEG = {'error': True, 'message':'Invalid request when requesting JPEG'}
    NO_EMAIL_REGISTER = {'error':True,'message':'could not register email addresses.'}
    NO_REMAINING_REGISTRATIONS = { 'error': True, 'message': 'That course has no remaining registrations. Please contact your faculty member.'}
    TRACK_FRAMES_SAME = {'error':True, 'message':'The frames references in api_get_frame are the same frame'}
    FRAME1_IS_NONE = {'error':True, 'message':'Frame1 in track_frame is None'}
    NO_TRACKPOINTS = {'error':True, 'message':'No trackpoints provided for tracking operation'}

#pylint: enable=too-few-public-methods
