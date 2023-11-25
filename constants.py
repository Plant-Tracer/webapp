"""
Constants are created in classes so we can import the class and don't have to import each constant.
"""

#pylint: disable=too-few-public-methods
class Engines:
    """Engines"""
    NULL_ENGINE = "NULL"
    MANUAL_ENGINE = "MANUAL"        # analysis entered by a person

class MIME:
    """MIME Types"""
    JPEG = 'image/jpeg'

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
    INVALID_TRACK_FRAME_MSEC = {'error': True, 'message': 'If track is true, then msec_delta must be +1'}
    NO_EMAIL_REGISTER = {'error':True,'message':'could not register email addresses.'}
    NO_REMAINING_REGISTRATIONS = { 'error': True, 'message': 'That course has no remaining registrations. Please contact your faculty member.'}
#pylint: enable=too-few-public-methods
