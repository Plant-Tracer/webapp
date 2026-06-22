import uuid
import os
import time
import json
from decimal import Decimal

import pytest

from app import odb
from app.odb import UserExists,InvalidUser_Id,LAST_FRAME_TRACKED,MOVIE_ID,COURSE_ID,USER_ID,EMAIL,API_KEY
from app.constants import logger
from app.schema import Trackpoint

# Fixtures are imported in conftest.py

def rand8():
    return str(uuid.uuid4())[0:8]

MYDIR = os.path.dirname(__file__)

randrun = rand8()

TEST_ADMIN_ID = odb.new_user_id()
TEST_ADMIN_EMAIL = f'new.admin-{randrun}@example.com'
TEST_COURSE_ID = f'test-course-{randrun}'
TEST_COURSE_NAME = f'Introduction to Plant Tracer {randrun}'
TEST_MOVIE_ID = odb.new_movie_id()
TEST_COURSE_KEY = f'k-{randrun}'
TEST_COURSE_MAX_ENROLLMENT = 30
TEST_COURSE_DATA = {
    COURSE_ID: TEST_COURSE_ID,
    'course_name': TEST_COURSE_NAME,
    'course_key': TEST_COURSE_KEY,
    'admins_for_course': [TEST_ADMIN_ID],
    'max_enrollment': TEST_COURSE_MAX_ENROLLMENT
}

TEST_USER_ID = odb.new_user_id()
TEST_USER_EMAIL = f'new.user-{randrun}@example.com'
TEST_USER_NAME = f'Firstname {randrun} Lastname'
TEST_USER_DATA = {
    USER_ID: TEST_USER_ID,
    'email': TEST_USER_EMAIL,
    'user_name': TEST_USER_NAME,
    'created': int(time.time()),
    'enabled': 1,
    'admin_for_courses': [],
    'courses': [],
    'primary_course_id': TEST_COURSE_ID,
    'primary_course_name': TEST_COURSE_NAME,
}

TEST_ADMIN_DATA = {
    USER_ID: TEST_USER_ID,
    'email': TEST_USER_EMAIL,
    'user_name': 'Admin Firstname Lastname',
    'created': int(time.time()),
    'enabled': 1,
    'admin_for_courses': [TEST_COURSE_ID],
    'courses': [TEST_COURSE_ID],
    'primary_course_id': TEST_COURSE_ID,
    'primary_course_name': TEST_COURSE_NAME,
}

TEST_MOVIE_DATA = {
    MOVIE_ID: TEST_MOVIE_ID,
    COURSE_ID: TEST_COURSE_ID,
    USER_ID: TEST_USER_ID,
    'user_name': TEST_USER_NAME,
    'title': 'My New Awesome Movie',
    'published': 0,
    'deleted': 0,
    'description': 'A fantastic new movie project.',
    'movie_zipfile_urn':'s3://bogus/movie-data.zip',
    'movie_data_urn':'s3://bogus/movie-data.mp4',
    LAST_FRAME_TRACKED:0,
    'created_at':int(time.time()),
    'date_uploaded':int(time.time()),
    'fps':"29.92",
    'total_frames':10,
    'total_bytes':100,
    odb.TRACKPOINT_ORIGIN: odb.TRACKPOINT_ORIGIN_BOTTOM_LEFT,
}

TEST_MOVIE_FRAME_DATA = {
    MOVIE_ID: TEST_MOVIE_ID,
    'frame_number': 0,
    'frame_urn':'s3://bogus/movie-frame.jpg',
    'trackpoints':[{'x':Decimal(10),'y':Decimal(20),'label':'name1'},
                   {'x':Decimal(45),'y':Decimal(55),'label':'name2'}]
}


def create_trim_test_movie(local_ddb, *, total_frames=5, trim_start_frame=None, trim_end_frame=None):
    course_id = f"trim-course-{rand8()}"
    course_key = f"trim-key-{uuid.uuid4().hex[:16]}"
    user_id = odb.new_user_id()
    movie_id = odb.new_movie_id()
    local_ddb.put_course({
        COURSE_ID: course_id,
        'course_name': f"Trim Course {rand8()}",
        'course_key': course_key,
        'admins_for_course': [],
        'max_enrollment': 10,
    })
    local_ddb.put_user({
        USER_ID: user_id,
        'email': f"trim-{uuid.uuid4().hex[:8]}@example.com",
        'user_name': 'Trim User',
        'created': int(time.time()),
        'enabled': 1,
        'admin_for_courses': [],
        'courses': [course_id],
        'primary_course_id': course_id,
        'primary_course_name': 'Trim Course',
    })
    movie = {
        MOVIE_ID: movie_id,
        COURSE_ID: course_id,
        USER_ID: user_id,
        'user_name': 'Trim User',
        'title': 'Trim test movie',
        'published': 0,
        'deleted': 0,
        'description': 'Trim semantics test.',
        'movie_zipfile_urn': 's3://bogus/trim.zip',
        'movie_data_urn': 's3://bogus/trim.mov',
        LAST_FRAME_TRACKED: 0,
        'created_at': int(time.time()),
        'date_uploaded': int(time.time()),
        'fps': "29.92",
        'total_frames': total_frames,
        'total_bytes': 100,
        odb.TRACKPOINT_ORIGIN: odb.TRACKPOINT_ORIGIN_BOTTOM_LEFT,
    }
    if trim_start_frame is not None:
        movie[odb.TRIM_START_FRAME] = trim_start_frame
    if trim_end_frame is not None:
        movie[odb.TRIM_END_FRAME] = trim_end_frame
    local_ddb.put_movie(movie)
    for frame_number in range(total_frames):
        local_ddb.put_movie_frame({
            MOVIE_ID: movie_id,
            'frame_number': frame_number,
            'frame_urn': f's3://bogus/frame-{frame_number}.jpg',
        })
    return movie_id


# pylint: disable=too-many-statements
def test_odb(local_ddb):
    ddbo = local_ddb
    start_time = int(time.time())

    # Create the course
    ddbo.put_course(TEST_COURSE_DATA)
    assert ddbo.get_course(TEST_COURSE_ID) == TEST_COURSE_DATA

    # Create the user.
    ddbo.put_user(TEST_USER_DATA)
    # This should fail because the user we are putting exist
    try:
        with pytest.raises(UserExists):
            ddbo.put_user(TEST_USER_DATA)
    except Exception as e:
        logger.error("exception=%s %s",type(e),e)
        raise

    # Register the user into the course (adds user to course; updates user's courses list)
    odb.register_email(TEST_USER_EMAIL, TEST_USER_NAME, course_id=TEST_COURSE_ID)

    actual_user = ddbo.get_user(TEST_USER_ID)
    expected_user = {**TEST_USER_DATA, 'courses': [TEST_COURSE_ID]}
    if actual_user != expected_user:
        print("\n--- ddbo.get_user(TEST_USER_ID) ---")
        print(json.dumps(actual_user, indent=2, default=str))
        print("\n--- expected (TEST_USER_DATA with courses after register_email) ---")
        print(json.dumps(expected_user, indent=2, default=str))
    assert actual_user == expected_user
    assert ddbo.get_user_email(TEST_USER_EMAIL) == expected_user

    # Create a movie
    ddbo.put_movie(TEST_MOVIE_DATA)
    assert ddbo.get_movie(TEST_MOVIE_ID) == TEST_MOVIE_DATA
    assert ddbo.get_movies_for_user_id(TEST_USER_ID) == [TEST_MOVIE_DATA]

    # Create a movie frame
    ddbo.put_movie_frame(TEST_MOVIE_FRAME_DATA)
    assert len(ddbo.get_frames(TEST_MOVIE_ID)) == 1
    assert (odb.get_movie_trackpoints(movie_id= TEST_MOVIE_ID)
            == [{'frame_number': Decimal(0), 'x':Decimal(10), 'y':Decimal(20), 'label':'name1'},
                {'frame_number': Decimal(0), 'x':Decimal(45), 'y':Decimal(55), 'label':'name2'}])
    assert odb.last_tracked_movie_frame(movie_id=TEST_MOVIE_ID)==0
    ddbo.put_movie_frame({"movie_id":TEST_MOVIE_ID,
                         "frame_number":1,
                         "frame_urn":"s3://bogus/frame1"})

    # Give it some trackpoints
    odb.put_frame_trackpoints(movie_id=TEST_MOVIE_ID, frame_number=1,
                              trackpoints=[Trackpoint(x=20, y=30, label='name3'),
                                           Trackpoint(x=65, y=85, label='name4')])
    assert odb.last_tracked_movie_frame(movie_id=TEST_MOVIE_ID)==1

    # Make an API key
    api_key = odb.make_new_api_key( email = TEST_USER_EMAIL)
    assert odb.is_api_key(api_key)
    user = odb.validate_api_key(api_key)
    # normalize DynamoDB Decimals for comparison; user has courses after register_email
    user_normalized = {k: (int(v) if isinstance(v, Decimal) else v) for k, v in user.items()}
    if user_normalized != expected_user:
        print("\n--- odb.validate_api_key(api_key) (normalized) ---")
        print(json.dumps(user_normalized, indent=2, default=str))
        print("\n--- expected_user ---")
        print(json.dumps(expected_user, indent=2, default=str))
    assert user_normalized == expected_user
    a2   = ddbo.get_api_key_dict(api_key)
    assert a2['enabled'] == 1
    assert a2['use_count'] == 1
    assert a2['created'] >= start_time
    assert a2['last_used_at'] >= a2['first_used_at'] >= a2['created']

    # Delete the API key
    ddbo.del_api_key(api_key)
    a3   = ddbo.get_api_key_dict(api_key)
    assert a3 is None

    # rename the user
    new_email = TEST_USER_EMAIL+"-new"
    ddbo.rename_user(user_id=TEST_USER_ID, new_email=new_email)
    u1 = ddbo.get_user(TEST_USER_ID)
    u2 = ddbo.get_user_email(new_email)
    print("u1=",json.dumps(u1,indent=4,default=str))
    print("u2=",json.dumps(u2,indent=4,default=str))
    assert u1==u2
    assert u1['email'] == TEST_USER_EMAIL+"-new"

    user_ids_before = odb.course_enrollments(course_id=TEST_COURSE_ID)

    # Remove the student from the course
    odb.unregister_from_course(user_id=TEST_USER_ID, course_id=TEST_COURSE_ID)

    # Verify student no longer present
    user_ids_after = odb.course_enrollments(course_id=TEST_COURSE_ID)

    assert len(user_ids_before) == len(user_ids_after)+1

    # Try to delete the user without deleting the user's movies
    with pytest.raises(RuntimeError,match=r'.* has 1 outstanding movie.*'):
        ddbo.delete_user(TEST_USER_ID)

    # Now delete the user and their movies
    ddbo.delete_user(TEST_USER_ID, purge_movies=True)
    with pytest.raises(InvalidUser_Id):
        ddbo.get_user(TEST_USER_ID)

    # Delete the user's course
    odb.delete_course(course_id=TEST_COURSE_ID)


def test_get_movie_trackpoints_carries_marker_metadata(local_ddb):
    movie_id = create_trim_test_movie(local_ddb, total_frames=1)

    odb.put_frame_trackpoints(
        movie_id=movie_id,
        frame_number=0,
        trackpoints=[Trackpoint(x=10, y=20, label='Ruler 0mm', color='red', undeletable=True)],
    )

    assert odb.get_movie_trackpoints(movie_id=movie_id) == [
        {'frame_number': 0, 'x': 10, 'y': 20, 'label': 'Ruler 0mm', 'color': 'red', 'undeletable': True}
    ]


def test_rename_movie_marker_preserves_marker_metadata(local_ddb):
    movie_id = create_trim_test_movie(local_ddb, total_frames=2)
    odb.put_frame_trackpoints(
        movie_id=movie_id,
        frame_number=0,
        trackpoints=[
            Trackpoint(x=10, y=20, label='Ruler 0mm', color='red', undeletable=True, frame_number=0, status=0),
            Trackpoint(x=30, y=40, label='Apex', color='orange', frame_number=0),
        ],
    )
    odb.put_frame_trackpoints(
        movie_id=movie_id,
        frame_number=1,
        trackpoints=[
            Trackpoint(x=11, y=21, label='Ruler 0mm', color='red', undeletable=True, frame_number=1, status=1),
            Trackpoint(x=31, y=41, label='Apex', color='orange', frame_number=1),
        ],
    )

    result = odb.rename_movie_marker(
        movie_id=movie_id,
        old_label='Ruler 0mm',
        new_label='Ruler 30mm',
        needs_retracing=True,
    )

    assert result == {'frames_updated': 2, 'trackpoints_updated': 2}
    assert odb.get_movie_trackpoints(movie_id=movie_id) == [
        {'frame_number': 0, 'x': 10, 'y': 20, 'label': 'Ruler 30mm', 'color': 'red', 'undeletable': True, 'status': 0},
        {'frame_number': 0, 'x': 30, 'y': 40, 'label': 'Apex', 'color': 'orange'},
        {'frame_number': 1, 'x': 11, 'y': 21, 'label': 'Ruler 30mm', 'color': 'red', 'undeletable': True, 'status': 1},
        {'frame_number': 1, 'x': 31, 'y': 41, 'label': 'Apex', 'color': 'orange'},
    ]
    assert odb.get_movie(movie_id=movie_id)[odb.NEEDS_RETRACING] == 1


def test_rename_movie_marker_rejects_existing_target_label(local_ddb):
    movie_id = create_trim_test_movie(local_ddb, total_frames=1)
    odb.put_frame_trackpoints(
        movie_id=movie_id,
        frame_number=0,
        trackpoints=[
            Trackpoint(x=10, y=20, label='Ruler 0mm'),
            Trackpoint(x=30, y=40, label='Ruler 30mm'),
        ],
    )

    with pytest.raises(ValueError, match='marker label already exists'):
        odb.rename_movie_marker(movie_id=movie_id, old_label='Ruler 0mm', new_label='Ruler 30mm')


def test_rename_movie_marker_uses_marker_map_for_long_movies(local_ddb):
    total_frames = 101
    movie_id = create_trim_test_movie(local_ddb, total_frames=total_frames)
    for frame_number in range(total_frames):
        local_ddb.movie_frames.update_item(
            Key={MOVIE_ID: movie_id, odb.FRAME_NUMBER: frame_number},
            UpdateExpression='SET trackpoints=:trackpoints',
            ExpressionAttributeValues={
                ':trackpoints': [{'x': frame_number, 'y': frame_number + 1, 'label': 'Apex'}],
            },
        )

    result = odb.rename_movie_marker(movie_id=movie_id, old_label='Apex', new_label='Tip')

    assert result == {'frames_updated': total_frames, 'trackpoints_updated': total_frames}
    assert all(trackpoint['label'] == 'Tip' for trackpoint in odb.get_movie_trackpoints(movie_id=movie_id))
    marker_map = local_ddb.movie_frames.get_item(
        Key={MOVIE_ID: movie_id, odb.FRAME_NUMBER: odb.MOVIE_MARKER_MAP_FRAME_NUMBER},
    ).get('Item')
    assert marker_map[odb.MARKER_LABELS]['Tip']
    assert len(local_ddb.get_frames(movie_id)) == total_frames
    with pytest.raises(AssertionError):
        local_ddb.get_movie_frame(movie_id, odb.MOVIE_MARKER_MAP_FRAME_NUMBER)
    stored_frame = local_ddb.get_movie_frame(movie_id, 0)
    assert stored_frame['trackpoints'][0]['label'] == 'Apex'


def test_clear_movie_tracking_after_frame(local_ddb):
    ddbo = local_ddb
    course_id = f"retrace-course-{rand8()}"
    course_name = f"Retrace Course {rand8()}"
    course_key = f"retrace-key-{uuid.uuid4().hex[:16]}"
    user_email = f"retrace-{uuid.uuid4().hex[:8]}@example.com"
    user_name = "Retrace User"
    movie_id = odb.new_movie_id()
    user_id = odb.new_user_id()

    ddbo.put_course({
        COURSE_ID: course_id,
        'course_name': course_name,
        'course_key': course_key,
        'admins_for_course': [],
        'max_enrollment': 10,
    })
    ddbo.put_user({
        USER_ID: user_id,
        'email': user_email,
        'user_name': user_name,
        'created': int(time.time()),
        'enabled': 1,
        'admin_for_courses': [],
        'courses': [course_id],
        'primary_course_id': course_id,
        'primary_course_name': course_name,
    })
    ddbo.put_movie({
        MOVIE_ID: movie_id,
        COURSE_ID: course_id,
        USER_ID: user_id,
        'user_name': user_name,
        'title': 'Retrace test movie',
        'published': 0,
        'deleted': 0,
        'description': 'Retrace semantics test.',
        'movie_zipfile_urn': 's3://bogus/retrace.zip',
        'movie_data_urn': 's3://bogus/retrace.mov',
        LAST_FRAME_TRACKED: 2,
        'created_at': int(time.time()),
        'date_uploaded': int(time.time()),
        'fps': "29.92",
        'total_frames': 10,
        'total_bytes': 100,
        odb.TRACKPOINT_ORIGIN: odb.TRACKPOINT_ORIGIN_BOTTOM_LEFT,
    })

    for frame_number, label in enumerate(["frame0", "frame1", "frame2"]):
        ddbo.put_movie_frame({"movie_id": movie_id, "frame_number": frame_number, "frame_urn": f"s3://bogus/{frame_number}.jpg"})
        odb.put_frame_trackpoints(
            movie_id=movie_id,
            frame_number=frame_number,
            trackpoints=[Trackpoint(x=10 + frame_number, y=20 + frame_number, label=label)],
        )

    deleted = odb.clear_movie_tracking_after_frame(movie_id=movie_id, frame_number=0)
    assert deleted == 2
    assert odb.last_tracked_movie_frame(movie_id=movie_id) == 0
    assert odb.get_movie_trackpoints(movie_id=movie_id) == [
        {'frame_number': 0, 'x': 10, 'y': 20, 'label': 'frame0'}
    ]


def test_clear_movie_tracking_after_frame_respects_frame_end(local_ddb):
    movie_id = create_trim_test_movie(local_ddb, total_frames=4)
    for frame_number in range(4):
        odb.put_frame_trackpoints(
            movie_id=movie_id,
            frame_number=frame_number,
            trackpoints=[Trackpoint(x=10 + frame_number, y=20 + frame_number, label=f'frame{frame_number}')],
        )

    deleted = odb.clear_movie_tracking_after_frame(movie_id=movie_id, frame_number=0, frame_end=1)

    assert deleted == 1
    assert odb.get_movie_trackpoints(movie_id=movie_id) == [
        {'frame_number': 0, 'x': 10, 'y': 20, 'label': 'frame0'},
        {'frame_number': 2, 'x': 12, 'y': 22, 'label': 'frame2'},
        {'frame_number': 3, 'x': 13, 'y': 23, 'label': 'frame3'},
    ]


def test_movie_trim_defaults_validate_and_filter_trackpoints(local_ddb):
    movie_id = create_trim_test_movie(local_ddb, total_frames=3)
    metadata = odb.movie_metadata_with_trim_defaults(odb.get_movie(movie_id=movie_id))
    assert metadata[odb.TRIM_START_FRAME] == 0
    assert metadata[odb.TRIM_END_FRAME] == 2
    assert odb.TRIM_START_FRAME not in odb.get_movie(movie_id=movie_id)
    assert odb.TRIM_END_FRAME not in odb.get_movie(movie_id=movie_id)

    for frame_number in range(3):
        odb.put_frame_trackpoints(
            movie_id=movie_id,
            frame_number=frame_number,
            trackpoints=[Trackpoint(x=10 + frame_number, y=20 + frame_number, label=f'frame{frame_number}')],
        )

    assert odb.get_movie_trackpoints(movie_id=movie_id, frame_start=1, frame_end=1) == [
        {'frame_number': 1, 'x': 11, 'y': 21, 'label': 'frame1'}
    ]
    with pytest.raises(ValueError):
        odb.set_movie_trim_frame(movie_id=movie_id, prop=odb.TRIM_START_FRAME, frame_number=3)
    with pytest.raises(ValueError):
        odb.set_movie_trim_frame(movie_id=movie_id, prop=odb.TRIM_END_FRAME, frame_number=3)


def test_movie_trim_defaults_unknown_total_frames_omits_end(local_ddb):
    movie_id = create_trim_test_movie(local_ddb, total_frames=0)

    metadata = odb.movie_metadata_with_trim_defaults(odb.get_movie(movie_id=movie_id))

    assert metadata[odb.TRIM_START_FRAME] == 0
    assert odb.TRIM_END_FRAME not in metadata
    with pytest.raises(ValueError, match="total_frames is required"):
        odb.set_movie_trim_frame(movie_id=movie_id, prop=odb.TRIM_START_FRAME, frame_number=0)


def test_movie_trim_defaults_clamps_stale_end_frame(local_ddb):
    movie_id = create_trim_test_movie(local_ddb, total_frames=3, trim_start_frame=0, trim_end_frame=8)

    metadata = odb.movie_metadata_with_trim_defaults(odb.get_movie(movie_id=movie_id))

    assert metadata[odb.TRIM_END_FRAME] == 2


def test_trim_validation_rejects_negative_start_and_invalid_property(local_ddb):
    movie_id = create_trim_test_movie(local_ddb, total_frames=3)

    with pytest.raises(ValueError, match="trim_start_frame must be >= 0"):
        odb.validate_trim_bounds(trim_start_frame=-1, trim_end_frame=2, total_frames=3)
    with pytest.raises(ValueError, match="trim_start_frame must be <= trim_end_frame"):
        odb.validate_trim_bounds(trim_start_frame=2, trim_end_frame=1, total_frames=3)
    with pytest.raises(ValueError, match="invalid trim property"):
        odb.set_movie_trim_frame(movie_id=movie_id, prop="trim_middle_frame", frame_number=1)


def test_trim_validation_rejects_start_after_end():
    with pytest.raises(ValueError, match="trim_start_frame must be <= trim_end_frame"):
        odb.validate_trim_bounds(trim_start_frame=3, trim_end_frame=1, total_frames=10)


def test_set_movie_trim_start_copies_old_start_markers(local_ddb):
    movie_id = create_trim_test_movie(local_ddb, total_frames=5, trim_start_frame=2, trim_end_frame=4)
    odb.set_movie_metadata(movie_id=movie_id, movie_metadata={LAST_FRAME_TRACKED: 2})
    odb.put_frame_trackpoints(
        movie_id=movie_id,
        frame_number=2,
        trackpoints=[Trackpoint(x=12, y=22, label='apex')],
    )

    metadata = odb.set_movie_trim_frame(movie_id=movie_id, prop=odb.TRIM_START_FRAME, frame_number=0)

    assert metadata[odb.TRIM_START_FRAME] == 0
    assert odb.get_movie_trackpoints(movie_id=movie_id, frame_start=0, frame_end=0) == [
        {'frame_number': 0, 'x': 12, 'y': 22, 'label': 'apex'}
    ]
    assert not odb.get_movie_trackpoints(movie_id=movie_id, frame_start=1, frame_end=1)


def test_set_movie_trim_start_does_not_overwrite_existing_target_markers(local_ddb):
    movie_id = create_trim_test_movie(local_ddb, total_frames=5, trim_start_frame=2, trim_end_frame=4)
    odb.put_frame_trackpoints(
        movie_id=movie_id,
        frame_number=0,
        trackpoints=[Trackpoint(x=1, y=2, label='existing')],
    )
    odb.put_frame_trackpoints(
        movie_id=movie_id,
        frame_number=2,
        trackpoints=[Trackpoint(x=12, y=22, label='old-start')],
    )

    odb.set_movie_trim_frame(movie_id=movie_id, prop=odb.TRIM_START_FRAME, frame_number=0)

    assert odb.get_movie_trackpoints(movie_id=movie_id, frame_start=0, frame_end=0) == [
        {'frame_number': 0, 'x': 1, 'y': 2, 'label': 'existing'}
    ]


def test_set_movie_trim_start_without_old_markers_does_not_synthesize_seed(local_ddb):
    movie_id = create_trim_test_movie(local_ddb, total_frames=5, trim_start_frame=2, trim_end_frame=4)

    metadata = odb.set_movie_trim_frame(movie_id=movie_id, prop=odb.TRIM_START_FRAME, frame_number=0)

    assert metadata[odb.TRIM_START_FRAME] == 0
    assert not odb.get_movie_trackpoints(movie_id=movie_id, frame_start=0, frame_end=0)
    assert not odb.get_movie_trackpoints(movie_id=movie_id, frame_start=1, frame_end=1)


def test_delete_user_removes_course_enrollment(local_ddb):
    ddbo = local_ddb
    course_id = f"delete-course-{rand8()}"
    course_name = f"Delete Course {rand8()}"
    course_key = f"delete-key-{uuid.uuid4().hex[:16]}"
    user_email = f"delete-user-{uuid.uuid4().hex[:8]}@example.com"
    user_name = "Delete User"
    movie_id = odb.new_movie_id()

    ddbo.put_course({
        COURSE_ID: course_id,
        'course_name': course_name,
        'course_key': course_key,
        'admins_for_course': [],
        'max_enrollment': 10,
    })

    user_id = odb.register_email(user_email, user_name, course_id=course_id)[USER_ID]
    assert user_id in odb.course_enrollments(course_id=course_id)
    ddbo.put_movie({
        MOVIE_ID: movie_id,
        COURSE_ID: course_id,
        USER_ID: user_id,
        'user_name': user_name,
        'title': 'Delete-user test movie',
        'published': 0,
        'deleted': 0,
        'description': 'Delete-user purge test.',
        'movie_zipfile_urn': 's3://bogus/delete.zip',
        'movie_data_urn': 's3://bogus/delete.mov',
        LAST_FRAME_TRACKED: 0,
        'created_at': int(time.time()),
        'date_uploaded': int(time.time()),
        'fps': "29.92",
        'total_frames': 1,
        'total_bytes': 100,
    })
    assert len(ddbo.get_movies_for_user_id(user_id)) == 1

    with pytest.raises(RuntimeError, match=r'.* has 1 outstanding movie.*'):
        ddbo.delete_user(user_id)

    ddbo.delete_user(user_id, purge_movies=True)

    assert ddbo.get_movies_for_user_id(user_id) == []
    assert user_id not in odb.course_enrollments(course_id=course_id)
    odb.delete_course(course_id=course_id)


def test_delete_user_raises_if_no_email(local_ddb):
    """delete_user raises RuntimeError when the user record has no email attribute (line 577 coverage)."""
    ddbo = local_ddb
    course_id = f"noemail-course-{rand8()}"
    course_key = f"noemail-key-{uuid.uuid4().hex[:16]}"
    user_email = f"noemail-user-{uuid.uuid4().hex[:8]}@example.com"

    ddbo.put_course({
        COURSE_ID: course_id,
        'course_name': f"NoEmail Course {rand8()}",
        'course_key': course_key,
        'admins_for_course': [],
        'max_enrollment': 10,
    })

    user_id = odb.register_email(user_email, "NoEmail User", course_id=course_id)[USER_ID]

    # Strip the email attribute directly from the users table to exercise the defensive check
    ddbo.users.update_item(
        Key={USER_ID: user_id},
        UpdateExpression='REMOVE #e',
        ExpressionAttributeNames={'#e': EMAIL},
    )

    with pytest.raises(RuntimeError, match=EMAIL):
        ddbo.delete_user(user_id)

    # Cleanup: delete_user raised before the transaction, so user and unique_emails still exist
    ddbo.users.delete_item(Key={USER_ID: user_id})
    ddbo.unique_emails.delete_item(Key={EMAIL: user_email})
    odb.delete_course(course_id=course_id)


def test_delete_user_api_keys_pagination(local_ddb, mocker):
    """delete_user handles DynamoDB pagination in the API keys query (line 547 coverage)."""
    ddbo = local_ddb
    course_id = f"paginate-course-{rand8()}"
    course_key = f"paginate-key-{uuid.uuid4().hex[:16]}"
    user_email = f"paginate-user-{uuid.uuid4().hex[:8]}@example.com"

    ddbo.put_course({
        COURSE_ID: course_id,
        'course_name': f"Paginate Course {rand8()}",
        'course_key': course_key,
        'admins_for_course': [],
        'max_enrollment': 10,
    })

    user_id = odb.register_email(user_email, "Paginate User", course_id=course_id)[USER_ID]

    # Mock query to return a fake LastEvaluatedKey on the first call, forcing the pagination
    # branch (line 547: kwargs['ExclusiveStartKey'] = last_evaluated_key).
    def mock_query(**kwargs):
        if 'ExclusiveStartKey' not in kwargs:
            # First call: simulate a paginated result with no items on this page
            return {'Items': [], 'Count': 0, 'LastEvaluatedKey': {API_KEY: 'pagination-sentinel'}}
        # Second call (pagination branch exercised): empty final page
        return {'Items': [], 'Count': 0}

    mocker.patch.object(ddbo.api_keys, 'query', side_effect=mock_query)

    ddbo.delete_user(user_id)
    assert user_id not in odb.course_enrollments(course_id=course_id)
    odb.delete_course(course_id=course_id)


def test_normalize_fpm_valid_values():
    assert odb.normalize_fpm(None) is None
    assert odb.normalize_fpm('') is None
    assert odb.normalize_fpm('   ') is None
    assert odb.normalize_fpm('30') == '30'
    assert odb.normalize_fpm('  0.5 ') == '0.5'


def test_normalize_fpm_rejects_invalid():
    with pytest.raises(ValueError, match="fpm must be a number"):
        odb.normalize_fpm('abc')
    with pytest.raises(ValueError, match="fpm must be greater than 0"):
        odb.normalize_fpm('0')
    with pytest.raises(ValueError, match="fpm must be greater than 0"):
        odb.normalize_fpm('-1')
    with pytest.raises(ValueError, match="fpm must be <="):
        odb.normalize_fpm('99999')


def test_create_new_movie_stores_fpm(local_ddb):
    course_id = f"fpm-course-{rand8()}"
    local_ddb.put_course({
        COURSE_ID: course_id,
        'course_name': 'FPM Course',
        'course_key': f"k-{uuid.uuid4().hex[:12]}",
        'admins_for_course': [],
        'max_enrollment': 10,
    })
    user_id = odb.new_user_id()
    local_ddb.put_user({
        USER_ID: user_id,
        'email': f"fpm-{uuid.uuid4().hex[:8]}@example.com",
        'user_name': 'FPM User',
        'created': int(time.time()),
        'enabled': 1,
        'admin_for_courses': [],
        'courses': [course_id],
        'primary_course_id': course_id,
        'primary_course_name': 'FPM Course',
    })
    movie_id = odb.create_new_movie(user_id=user_id, course_id=course_id, title='t', description='d', fpm='20')
    assert odb.get_movie(movie_id=movie_id)[odb.FPM] == '20'
