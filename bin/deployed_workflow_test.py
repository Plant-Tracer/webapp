#!/usr/bin/env python3
"""Exercise deployed create, S3 upload, EventBridge processing, and tracing."""

import argparse
import hashlib
import logging
import time
from pathlib import Path

import requests
from pydantic import BaseModel

from app import odb, odb_movie_data
from app.schema import Trackpoint


API_KEY_FIELD = "api_key"
MOVIE_ID_FIELD = "movie_id"
NEW_MOVIE_PATH = "api/new-movie"
TRACE_MOVIE_PATH = "resize-api/v1/trace-movie"


class PresignedPost(BaseModel):
    """S3 POST returned by the deployed Flask API."""

    url: str
    fields: dict[str, str]


class NewMovieResponse(BaseModel):
    """Successful new-movie response."""

    error: bool
    movie_id: str
    presigned_post: PresignedPost
    upload_completion_mode: str


def wait_for_movie(ddbo, movie_id, predicate, *, timeout, phase):
    """Poll one DynamoDB movie row until a phase-specific predicate succeeds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        movie = ddbo.get_movie(movie_id)
        if predicate(movie):
            return movie
        time.sleep(2)
    raise TimeoutError(f"timed out waiting for deployed movie {movie_id} to finish {phase}")


def ensure_test_identity(*, stack_name):
    """Create or reuse the deployment test course, user, and API key."""
    course_id = f"{stack_name}-deployment-test"
    email = f"planttracer-deployment-test+{stack_name}@planttracer.com"
    try:
        odb.lookup_course_by_id(course_id=course_id)
    except odb.InvalidCourse_Id:
        odb.create_course(
            course_id=course_id,
            course_name=f"{stack_name} deployment workflow test",
            course_key=f"{stack_name}-deployment-workflow",
        )
    user_id = odb.register_email(
        email=email,
        user_name=f"{stack_name} deployment test",
        course_id=course_id,
    )[odb.USER_ID]
    api_key = odb.make_new_api_key_for_user_id(user_id=user_id)
    return course_id, user_id, api_key


def run_workflow(*, endpoint, stack_name, movie_path, timeout):
    """Run the deployed workflow and remove the test movie on success."""
    ddbo = odb.DDBO()
    course_id, _user_id, api_key = ensure_test_identity(stack_name=stack_name)
    movie_bytes = movie_path.read_bytes()
    response = requests.post(
        f"{endpoint.rstrip('/')}/{NEW_MOVIE_PATH}",
        data={
            API_KEY_FIELD: api_key,
            "title": f"deployment test {int(time.time())}",
            "description": "automated post-deploy EventBridge workflow test",
            "movie_data_sha256": hashlib.sha256(movie_bytes).hexdigest(),
            "movie_data_length": len(movie_bytes),
            "fpm": "30",
        },
        timeout=30,
    )
    response.raise_for_status()
    created = NewMovieResponse.model_validate(response.json())
    if created.error or created.upload_completion_mode != "eventbridge":
        raise RuntimeError("deployed new-movie did not select EventBridge completion")

    movie_id = created.movie_id
    upload = requests.post(
        created.presigned_post.url,
        data=created.presigned_post.fields,
        files={"file": (movie_path.name, movie_bytes, "video/mp4")},
        timeout=timeout,
    )
    upload.raise_for_status()
    uploaded_movie = wait_for_movie(
        ddbo,
        movie_id,
        lambda movie: bool(movie.get(odb.RESIZED_AT)),
        timeout=timeout,
        phase="upload processing",
    )
    if uploaded_movie.get(odb.MOVIE_STATUS) != odb.MOVIE_STATE_READY:
        raise RuntimeError(f"movie {movie_id} is not ready after upload processing")

    odb.put_frame_trackpoints(
        movie_id=movie_id,
        frame_number=0,
        trackpoints=[
            Trackpoint(
                x=max(1, int(uploaded_movie[odb.WIDTH]) // 2),
                y=max(1, int(uploaded_movie[odb.HEIGHT]) // 2),
                label="Apex",
                frame_number=0,
            )
        ],
    )
    traced = requests.post(
        f"{endpoint.rstrip('/')}/{TRACE_MOVIE_PATH}",
        headers={"x-api-key": api_key},
        json={MOVIE_ID_FIELD: movie_id, "frame_start": 0, "frame_end": 2},
        timeout=30,
    )
    traced.raise_for_status()
    wait_for_movie(
        ddbo,
        movie_id,
        lambda movie: movie.get(odb.MOVIE_STATUS) == odb.MOVIE_STATE_TRACING_COMPLETED,
        timeout=timeout,
        phase="tracing",
    )
    odb_movie_data.purge_movie(movie_id=movie_id)
    ddbo.batch_delete_movie_ids([movie_id])
    logging.info("deployed workflow passed for stack=%s course=%s", stack_name, course_id)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--stack-name", required=True)
    parser.add_argument("--movie", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    if not args.movie.is_file():
        raise SystemExit(f"movie fixture does not exist: {args.movie}")
    run_workflow(
        endpoint=args.endpoint,
        stack_name=args.stack_name,
        movie_path=args.movie,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
