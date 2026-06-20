import pytest
from pydantic import ValidationError

from app.constants import logger
from app import schema


def test_movie_schema():
    m = schema.Movie(
        movie_id="mtest",
        title="ttest",
        description="dtest",
        created_at=1,
        user_id="utest",
        user_name="utest2",
        course_id="ctest",
        published=0,
        deleted=0,
    )

    schema.validate_movie_field("width", 0)
    assert schema.validate_movie_field("trim_start_frame", "0") == 0
    assert schema.validate_movie_field("trim_end_frame", "10") == 10
    with pytest.raises(AttributeError):
        schema.validate_movie_field("unknown", 0)

    with pytest.raises(ValidationError):
        m = schema.Movie(
            movie_id="mtest",
            title="ttest",
            description="dtest",
            created_at=0,
            user_id="utest",
            user_name="utest2",
            course_id="ctest",
            published=0,
        )
    logger.debug("m=%s", m)


def test_user_schema():
    u = schema.User(
        user_id="utest",
        email="etest",
        user_name="utest",
        created=0,
        enabled=0,
        admin_for_courses=[],
        primary_course_id="p",
        primary_course_name="c",
        courses=["p"],
    )

    schema.validate_user_field("created", 0)
    with pytest.raises(AttributeError):
        schema.validate_user_field("unknown", 0)

    with pytest.raises(ValidationError):
        m = schema.Movie(
            movie_id="mtest",
            title="ttest",
            description="dtest",
            created_at=0,
            user_id="utest",
            user_name="utest2",
            course_id="ctest",
            published=0,
        )
        logger.debug("m=%s", m)
    logger.debug("u=%s", u)


def test_trackpoint_schema_accepts_undeletable_flag():
    trackpoint = schema.Trackpoint(x=1, y=2, label="Ruler 0mm", undeletable=True)

    assert trackpoint.undeletable is True
