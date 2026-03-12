"""
Tracking env for a compact Lambda: DynamoDB and S3 via boto3 only.
No Flask, no flask_api. Imports table/attribute names from odb.
"""

import os
import urllib.parse
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from .constants import C
from .odb import (
    MOVIES,
    FRAMES,
    MOVIE_ID,
    FRAME_NUMBER,
    COURSE_ID,
    LAST_FRAME_TRACKED,
    MOVIE_DATA_URN,
)
from . import tracker


def _table_prefix():
    prefix = os.environ.get(C.DYNAMODB_TABLE_PREFIX, "").strip()
    if prefix and not prefix.endswith("-"):
        prefix = prefix + "-"
    return prefix or ""


def _fix_value(prop, value):
    """Convert value for DynamoDB/movie metadata (minimal fix_movie_prop_value)."""
    if value is None:
        return None
    if prop in (
        "published", "deleted", "version", "last_frame_tracked", "research_use",
        "credit_by_name", "date_uploaded", "total_bytes", "total_frames",
        "width", "height", "rotation_steps",
    ):
        return int(value)
    if prop == "fps":
        return str(value)
    return value


def _fix_movie(raw):
    """Convert DynamoDB item to Python types (minimal fix_movie)."""
    return {k: _fix_value(k, v) for k, v in raw.items()}


def _s3_client():
    region = os.environ.get(C.AWS_REGION)
    endpoint = os.environ.get(C.AWS_ENDPOINT_URL_S3)
    return boto3.Session().client("s3", region_name=region, endpoint_url=endpoint)


def _dynamodb():
    region = os.environ.get(C.AWS_REGION)
    endpoint = os.environ.get(C.AWS_ENDPOINT_URL_DYNAMODB)
    return boto3.resource("dynamodb", region_name=region, endpoint_url=endpoint)


class LambdaTrackingEnv(tracker.TrackingEnv):
    """Implements the tracking env interface using boto3 only (no Flask/odb)."""

    def __init__(self):
        self._ddb = _dynamodb()
        self._prefix = _table_prefix()
        self._movies = self._ddb.Table(self._prefix + MOVIES)
        self._movie_frames = self._ddb.Table(self._prefix + FRAMES)
        self._bucket = os.environ.get(C.PLANTTRACER_S3_BUCKET, "")
        if not self._bucket or self._bucket.startswith("s3:"):
            raise RuntimeError(f"{C.PLANTTRACER_S3_BUCKET} must be set and not start with s3://")

    def get_movie_data(self, movie_id):
        movie = self._movies.get_item(Key={MOVIE_ID: movie_id}, ConsistentRead=True).get("Item")
        if not movie or not movie.get(MOVIE_DATA_URN):
            raise ValueError(f"No movie_data_urn for movie_id={movie_id}")
        urn = movie[MOVIE_DATA_URN]
        parsed = urllib.parse.urlparse(urn)
        if parsed.scheme != "s3":
            raise ValueError(f"Unsupported URN scheme: {urn}")
        key = parsed.path.lstrip("/")
        resp = _s3_client().get_object(Bucket=parsed.netloc, Key=key)
        return resp["Body"].read()

    def get_movie_metadata(self, movie_id):
        item = self._movies.get_item(Key={MOVIE_ID: movie_id}, ConsistentRead=True).get("Item")
        if not item:
            raise ValueError(f"Movie not found: {movie_id}")
        return _fix_movie(dict(item))

    def get_movie_trackpoints(self, movie_id):
        out = []
        kwargs = {
            "KeyConditionExpression": Key(MOVIE_ID).eq(movie_id),
        }
        last_key = None
        while True:
            if last_key:
                kwargs["ExclusiveStartKey"] = last_key
            resp = self._movie_frames.query(**kwargs)
            for frame in resp.get("Items", []):
                fn = frame.get(FRAME_NUMBER)
                if fn is not None and isinstance(fn, Decimal):
                    fn = int(fn)
                for tp in frame.get("trackpoints", []):
                    x, y = tp.get("x"), tp.get("y")
                    if isinstance(x, Decimal):
                        x = int(x) if x % 1 == 0 else float(x)
                    if isinstance(y, Decimal):
                        y = int(y) if y % 1 == 0 else float(y)
                    out.append({"frame_number": fn, "x": x, "y": y, "label": tp.get("label", "")})
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
        return out

    def put_frame_trackpoints(self, *, movie_id, frame_number, trackpoints):
        # Serialize for DynamoDB (Decimal for numbers)
        serialized = []
        for tp in trackpoints or []:
            serialized.append({
                "x": Decimal(str(tp.get("x", 0))),
                "y": Decimal(str(tp.get("y", 0))),
                "label": str(tp.get("label", "")),
            })
        self._movie_frames.update_item(
            Key={MOVIE_ID: movie_id, FRAME_NUMBER: frame_number},
            UpdateExpression="SET trackpoints = :val",
            ExpressionAttributeValues={":val": serialized},
        )
        movie = self._movies.get_item(Key={MOVIE_ID: movie_id}, ConsistentRead=True).get("Item")
        if movie:
            current = movie.get(LAST_FRAME_TRACKED)
            if current is None:
                new_val = frame_number
            else:
                new_val = max(int(current) if isinstance(current, Decimal) else current, frame_number)
            self._movies.update_item(
                Key={MOVIE_ID: movie_id},
                UpdateExpression="SET last_frame_tracked = :v",
                ExpressionAttributeValues={":v": new_val},
            )

    def set_metadata(self, *, user_id, movie_id, prop, value):
        # pylint: disable=unused-argument
        value = _fix_value(prop, value)
        self._movies.update_item(
            Key={MOVIE_ID: movie_id},
            UpdateExpression="SET #p = :v",
            ExpressionAttributeNames={"#p": prop},
            ExpressionAttributeValues={":v": value},
        )

    def set_movie_metadata(self, *, user_id, movie_id, movie_metadata):
        # pylint: disable=unused-argument
        for prop in ("fps", "width", "height", "total_frames", "total_bytes"):
            if prop in movie_metadata:
                self.set_metadata(user_id=user_id, movie_id=movie_id, prop=prop, value=movie_metadata[prop])

    def write_object(self, *, urn, data):
        parsed = urllib.parse.urlparse(urn)
        if parsed.scheme != "s3":
            raise ValueError(f"Unsupported URN: {urn}")
        _s3_client().put_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"), Body=data)

    def write_object_from_path(self, *, urn, path):
        parsed = urllib.parse.urlparse(urn)
        if parsed.scheme != "s3":
            raise ValueError(f"Unsupported URN: {urn}")
        with open(path, "rb") as f:
            _s3_client().put_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"), Body=f)

    def make_object_name(self, *, course_id, movie_id, ext, frame_number=None):
        if frame_number is None:
            return C.MOVIE_TEMPLATE.format(course_id=course_id, movie_id=movie_id, ext=ext)
        return C.FRAME_TEMPLATE.format(
            course_id=course_id, movie_id=movie_id, frame_number=frame_number, ext=ext
        )

    def make_urn(self, *, object_name):
        return f"s3://{self._bucket}/{object_name}"

    def course_id_for_movie_id(self, movie_id):
        item = self._movies.get_item(Key={MOVIE_ID: movie_id}).get("Item")
        if not item:
            raise ValueError(f"Movie not found: {movie_id}")
        return item.get(COURSE_ID, "")

    def update_movie(self, movie_id, updates):
        for attr, val in updates.items():
            val = _fix_value(attr, val)
            self._movies.update_item(
                Key={MOVIE_ID: movie_id},
                UpdateExpression="SET #p = :v",
                ExpressionAttributeNames={"#p": attr},
                ExpressionAttributeValues={":v": val},
            )
