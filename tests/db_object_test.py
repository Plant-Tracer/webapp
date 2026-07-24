"""
Tests the DB object storage layer
"""
import uuid
import hashlib

import boto3
import pytest

from app import s3_presigned
from app import odb_movie_data
from app import odb
from app.constants import logger

# Fixtures are imported in conftest.py

s3client = boto3.client('s3')

def test_runtime_s3_object_keys_are_deterministic():
    movie_key = s3_presigned.movie_object_key(
        deployment_id="prod",
        course_id="c1",
        movie_id="m2",
    )

    assert movie_key == "movies/prod/c1/m2.mov"
    assert s3_presigned.traced_movie_object_key(
        source_movie_object_key=movie_key,
    ) == "movies/prod/c1/m2_traced.mov"
    assert s3_presigned.analysis_zip_object_key(
        source_movie_object_key=movie_key,
    ) == "movies/prod/c1/m2_zipfile.mov"
    assert s3_presigned.frame_object_key(
        deployment_id="prod",
        course_id="c1",
        movie_id="m2",
        frame_number=3,
    ) == "movies/prod/c1/m2/000003.jpg"
    assert s3_presigned.movie_object_key(
        deployment_id="prod",
        course_id="legacy/course",
        movie_id="m2",
    ) == "movies/prod/legacy/course/m2.mov"


def test_upload_staging_keys_are_isolated_by_deployment():
    prod_key = s3_presigned.upload_staging_object_key(
        deployment_id="prod",
        course_id="c1",
        movie_id="m2",
    )
    demo_key = s3_presigned.upload_staging_object_key(
        deployment_id="demo",
        course_id="c1",
        movie_id="m2",
    )

    assert prod_key == "uploads/prod/c1/m2.mov"
    assert demo_key == "uploads/demo/c1/m2.mov"
    assert prod_key != demo_key


def test_object_key_components_cannot_escape_their_prefix():
    for name, build_key in (
        (
            "course_id",
            lambda: s3_presigned.movie_object_key(
                deployment_id="prod",
                course_id="",
                movie_id="m2",
            ),
        ),
        (
            "movie_id",
            lambda: s3_presigned.movie_object_key(
                deployment_id="prod",
                course_id="c1",
                movie_id=None,
            ),
        ),
        (
            "deployment_id",
            lambda: s3_presigned.upload_staging_object_key(
                deployment_id="",
                course_id="c1",
                movie_id="m2",
            ),
        ),
    ):
        with pytest.raises(ValueError, match=name):
            build_key()

    with pytest.raises(ValueError, match="deployment_id"):
        s3_presigned.upload_staging_object_key(
            deployment_id="prod/other",
            course_id="c1",
            movie_id="m2",
        )
    with pytest.raises(ValueError, match="non-negative"):
        s3_presigned.frame_object_key(
            deployment_id="prod",
            course_id="c1",
            movie_id="m2",
            frame_number=-1,
        )


def test_course_object_keys_can_be_reassigned_without_changing_the_suffix():
    assert s3_presigned.replace_course_object_key(
        object_key="movies/prod/course-1/movie-2/000003.jpg",
        from_course_id="course-1",
        to_course_id="course-3",
    ) == "movies/prod/course-3/movie-2/000003.jpg"

    with pytest.raises(ValueError, match="does not contain"):
        s3_presigned.replace_course_object_key(
            object_key="movies/prod/course-10/movie-2.mov",
            from_course_id="course-1",
            to_course_id="course-3",
        )


def test_make_urn_rejects_missing_or_malformed_bucket(monkeypatch):
    monkeypatch.delenv("PLANTTRACER_S3_BUCKET", raising=False)
    with pytest.raises(RuntimeError, match="is not set"):
        s3_presigned.make_urn(object_name="course-1/movie-2.mov")
    with pytest.raises(RuntimeError, match="should not start"):
        s3_presigned.make_urn(
            object_name="course-1/movie-2.mov",
            bucket="s3://movies",
        )
    with pytest.raises(ValueError, match="Invalid scheme"):
        s3_presigned.make_urn(
            object_name="course-1/movie-2.mov",
            bucket="movies",
            scheme="https",
        )


def test_parse_s3_urn_rejects_non_s3_and_incomplete_urns():
    with pytest.raises(RuntimeError, match="Unknown scheme"):
        s3_presigned.parse_s3_urn(urn="https://movies/course/movie.mov")
    with pytest.raises(ValueError, match="Invalid S3 URN"):
        s3_presigned.parse_s3_urn(urn="s3://movies")


def test_derived_movie_urns_preserve_legacy_bucket_path_and_extension():
    legacy_urn = "s3://legacy-bucket/archive/c1/m2.mp4"

    assert s3_presigned.traced_movie_urn(
        movie_data_urn=legacy_urn,
    ) == "s3://legacy-bucket/archive/c1/m2_traced.mp4"
    assert s3_presigned.analysis_zip_urn(
        movie_data_urn=legacy_urn,
    ) == "s3://legacy-bucket/archive/c1/m2_zipfile.mp4"

def test_make_urn(local_s3):
    name = s3_presigned.movie_object_key(
        deployment_id="local",
        course_id="c1",
        movie_id="m2",
    )
    a = s3_presigned.make_urn(object_name=name)
    assert a.endswith("/movies/local/c1/m2.mov")

def test_write_read_delete_object(local_s3):
    DATA = str(uuid.uuid4()).encode('utf-8')
    hasher = hashlib.sha256()
    hasher.update(DATA)
    # DATA_SHA256 = hasher.hexdigest()

    course_id = 'bogus'
    movie_id = odb.new_movie_id()
    name = s3_presigned.movie_object_key(
        deployment_id="local",
        course_id=course_id,
        movie_id=movie_id,
    )
    urn  = s3_presigned.make_urn(object_name=name)
    try:
        odb_movie_data.write_object(urn=urn, object_data=DATA)
    except s3client.exceptions.NoSuchBucket as e:
        logger.error("urn=%s error: %s",urn,e)
        raise RuntimeError() from e

    obj_data = odb_movie_data.read_object(urn=urn)
    assert obj_data == DATA

    odb_movie_data.delete_object(urn=urn)
    assert odb_movie_data.read_object(urn=urn) is None


def test_legacy_movie_urn_remains_readable(local_s3):
    legacy_urn = s3_presigned.make_urn(object_name="legacy/c1/m2.mp4")
    movie_data = b"legacy movie bytes"

    odb_movie_data.write_object(urn=legacy_urn, object_data=movie_data)
    try:
        assert odb_movie_data.read_object(urn=legacy_urn) == movie_data
    finally:
        odb_movie_data.delete_object(urn=legacy_urn)


def test_create_movie_frame_persists_namespaced_bytes(new_movie):
    movie_id = new_movie[odb.MOVIE_ID]
    frame_data = b"jpeg frame bytes"

    frame_urn = odb_movie_data.create_new_movie_frame(
        movie_id=movie_id,
        frame_number=7,
        frame_data=frame_data,
    )

    assert frame_urn.endswith(f"/{new_movie[odb.COURSE_ID]}/{movie_id}/000007.jpg")
    assert odb_movie_data.read_object(urn=frame_urn) == frame_data
    assert odb.DDBO().get_movie_frame(movie_id, 7)[odb.FRAME_URN] == frame_urn
