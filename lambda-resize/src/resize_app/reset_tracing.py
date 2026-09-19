"""Bounded, checkpointed removal of annotations without deleting frame data."""

import time
from typing import Annotated

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from pydantic import BaseModel, ConfigDict, Field

from . import async_work, local_queue, movie_glue
from .src.app import odb
from .src.app.constants import C

RESET_JOB_ID = "reset_job_id"
RESET_NEXT_FRAME = "reset_next_frame"
RESET_END_FRAME = "reset_end_frame"
RESET_STATE = "reset_state"
TRACKPOINTS = "trackpoints"
ITEMS = "Items"
LAST_KEY = "LastEvaluatedKey"
EXCLUSIVE_START_KEY = "ExclusiveStartKey"
UPDATE = "Update"
LABEL = "label"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
PAGE_SIZE = 80  # Leave room for the movie checkpoint and seed in a 100-item transaction.
MAX_BATCHES = 100
WORK_SECONDS = 60


class DynamoUpdate(BaseModel):
    """Typed DynamoDB transaction update; dictionaries are API expression maps."""

    model_config = ConfigDict(populate_by_name=True)
    table: Annotated[str, Field(alias="TableName")]
    key: Annotated[dict, Field(alias="Key")]
    expression: Annotated[str, Field(alias="UpdateExpression")]
    names: Annotated[dict, Field(alias="ExpressionAttributeNames")]
    values: Annotated[dict | None, Field(alias="ExpressionAttributeValues")] = None
    condition: Annotated[str | None, Field(alias="ConditionExpression")] = None

    def transaction(self):
        """Serialize exactly the external DynamoDB API fields."""
        return {UPDATE: self.model_dump(by_alias=True, exclude_none=True)}


class ResetProgress(BaseModel):
    """Small status response that never scans frames or signs S3 URLs."""

    error: bool = False
    job_id: str
    state: str
    next_frame: int
    frame_end: int


def progress(movie, job_id):
    """Report replaced/expired jobs explicitly instead of polling forever."""
    state = movie.get(RESET_STATE, FAILED)
    if movie.get(RESET_JOB_ID) != job_id:
        state = "superseded"
    elif state == RUNNING and (movie.get(odb.TRACE_JOB_ID) != job_id
                              or movie.get(odb.TRACE_LOCK_EXPIRES_AT, 0) <= time.time()):
        state = "expired"
    return ResetProgress(job_id=job_id, state=state,
                         next_frame=int(movie.get(RESET_NEXT_FRAME, 0)),
                         frame_end=int(movie.get(RESET_END_FRAME, 0)))


def enqueue(job):
    """Use the same local/EventBridge transport as tracing."""
    if movie_glue.async_queue_mode() == "local":
        local_queue.enqueue_message(job.model_dump())
    else:
        async_work.publish_job(job)


def prepare(*, api_key, request: async_work.ResetRequest):
    """Validate before taking the exclusive movie lease; queue one range job."""
    if api_key == C.DEMO_MODE_API_KEY:
        raise ValueError("Reset tracing is not available in demo mode")
    ddbo, user_id, movie = movie_glue.validate_movie_access(
        api_key=api_key, movie_id=request.movie_id, require_edit=True)
    if not odb.movie_is_available(movie):
        raise ValueError("Movie upload processing is not complete")
    if request.frame_end >= int(movie.get(odb.TOTAL_FRAMES, 0)):
        raise ValueError("Reset range exceeds the movie's frame count")
    if movie.get(odb.TRACKPOINT_ORIGIN) != odb.TRACKPOINT_ORIGIN_BOTTOM_LEFT:
        raise ValueError("Open Analyze to initialize the movie's coordinate system first")
    lock = ddbo.acquire_movie_trace_lock(
        movie=movie, started_by_user_id=user_id,
        started_by_user_name=ddbo.get_user(user_id)[odb.USER_NAME],
        analysis_lease_id=request.analysis_lease_id)
    job = async_work.ResetJob(**request.model_dump(), job_id=lock.job_id)
    try:
        ddbo.movies.update_item(
            Key={odb.MOVIE_ID: request.movie_id},
            UpdateExpression="SET #reset=:job, #next=:start, #end=:end, #state=:running, #dirty=:dirty, #status=:ready",
            ConditionExpression="#trace=:job",
            ExpressionAttributeNames={"#reset": RESET_JOB_ID, "#next": RESET_NEXT_FRAME,
                                      "#end": RESET_END_FRAME, "#state": RESET_STATE,
                                      "#trace": odb.TRACE_JOB_ID, "#dirty": odb.NEEDS_RETRACING,
                                      "#status": odb.MOVIE_STATUS},
            ExpressionAttributeValues={":job": job.job_id, ":start": job.frame_start,
                                       ":end": job.frame_end, ":running": RUNNING, ":dirty": 1,
                                       ":ready": odb.MOVIE_STATE_READY})
        enqueue(job)
    except Exception:
        ddbo.finish_movie_trace(movie_id=job.movie_id, job_id=job.job_id,
                                updates={RESET_STATE: FAILED, odb.MOVIE_STATUS: odb.MOVIE_STATE_READY})
        raise
    return progress(ddbo.get_movie(job.movie_id), job.job_id)


def _last_preserved_frame(ddbo, job):
    """Find the last nonempty annotation outside the reset range, in bounded pages."""
    params = {
        "KeyConditionExpression": Key(odb.MOVIE_ID).eq(job.movie_id) & Key(odb.FRAME_NUMBER).gt(job.frame_end),
        "FilterExpression": Attr(TRACKPOINTS).size().gt(0),
        "ProjectionExpression": odb.FRAME_NUMBER,
        "ScanIndexForward": False, "Limit": 1000, "ConsistentRead": True,
    }
    while True:
        response = ddbo.movie_frames.query(**params)
        if response.get(ITEMS):
            return max(job.seed_frame, int(response[ITEMS][0][odb.FRAME_NUMBER]))
        if not response.get(LAST_KEY):
            return job.seed_frame
        params[EXCLUSIVE_START_KEY] = response[LAST_KEY]


def reset_batch(ddbo, job, movie):
    """Commit at most 80 frame changes and their checkpoint atomically.

    The job/lease/cursor condition fences concurrent deliveries and late workers.
    An interrupted or ambiguously acknowledged transaction can safely be retried.
    """
    cursor = int(movie[RESET_NEXT_FRAME])
    response = ddbo.movie_frames.query(
        KeyConditionExpression=Key(odb.MOVIE_ID).eq(job.movie_id)
        & Key(odb.FRAME_NUMBER).between(cursor, job.frame_end),
        FilterExpression=Attr(TRACKPOINTS).exists(),
        ProjectionExpression=odb.FRAME_NUMBER, Limit=PAGE_SIZE, ConsistentRead=True)
    next_frame = (int(response[LAST_KEY][odb.FRAME_NUMBER]) + 1
                  if response.get(LAST_KEY) else job.frame_end + 1)
    done = next_frame > job.frame_end
    updates = [DynamoUpdate(
        table=ddbo.movie_frames.name,
        key={odb.MOVIE_ID: job.movie_id, odb.FRAME_NUMBER: item[odb.FRAME_NUMBER]},
        expression="REMOVE #points", names={"#points": TRACKPOINTS}).transaction()
        for item in response.get(ITEMS, []) if item[odb.FRAME_NUMBER] != job.seed_frame]
    now = int(time.time())
    checkpoint = DynamoUpdate(
        table=ddbo.movies.name, key={odb.MOVIE_ID: job.movie_id},
        expression="SET #next=:next, #heartbeat=:now, #expires=:expires",
        condition="#job=:job AND #next=:cursor AND #expires>:now",
        names={"#job": odb.TRACE_JOB_ID, "#next": RESET_NEXT_FRAME,
               "#heartbeat": odb.TRACE_LOCK_HEARTBEAT_AT, "#expires": odb.TRACE_LOCK_EXPIRES_AT},
        values={":job": job.job_id, ":cursor": cursor, ":next": next_frame,
                ":now": now, ":expires": now + 15 * 60})
    if done:
        # Write the replacement and release the lease in the same transaction.
        marker_map = odb.get_movie_marker_map(movie_id=job.movie_id, create=False)
        points = [point.model_copy(update={odb.MARKER_ID: marker_map[odb.MARKER_LABELS].get(point.label)
                                          or f"reset-{job.job_id}-{index}"}).model_dump()
                  for index, point in enumerate(job.trackpoints)]
        for point in points:
            marker_map[odb.MARKERS][point[odb.MARKER_ID]] = {LABEL: point[LABEL]}
            marker_map[odb.MARKER_LABELS][point[LABEL]] = point[odb.MARKER_ID]
            marker_map[odb.MARKER_ALIASES][point[LABEL]] = point[odb.MARKER_ID]
        updates.append(DynamoUpdate(
            table=ddbo.movie_frames.name, key=odb.movie_marker_map_key(job.movie_id),
            expression="SET #markers=:markers, #labels=:labels, #aliases=:aliases, #origin=:origin",
            names={"#markers": odb.MARKERS, "#labels": odb.MARKER_LABELS, "#aliases": odb.MARKER_ALIASES,
                   "#origin": odb.ORIG_MOVIE},
            values={":markers": marker_map[odb.MARKERS], ":labels": marker_map[odb.MARKER_LABELS],
                    ":aliases": marker_map[odb.MARKER_ALIASES], ":origin": job.movie_id}).transaction())
        updates.append(DynamoUpdate(
            table=ddbo.movie_frames.name,
            key={odb.MOVIE_ID: job.movie_id, odb.FRAME_NUMBER: job.seed_frame},
            expression="SET #points=:points", names={"#points": TRACKPOINTS},
            values={":points": points}).transaction())
        checkpoint.expression = "SET #next=:next, #state=:complete, #status=:ready, #last=:last REMOVE #job, #expires, #heartbeat"
        checkpoint.names.update({"#state": RESET_STATE, "#status": odb.MOVIE_STATUS,
                                 "#last": odb.LAST_FRAME_TRACKED})
        checkpoint.values.pop(":expires")
        checkpoint.values.update({":complete": COMPLETED, ":ready": odb.MOVIE_STATE_READY,
                                  ":last": _last_preserved_frame(ddbo, job)})
    updates.append(checkpoint.transaction())
    try:
        ddbo.dynamodb.meta.client.transact_write_items(TransactItems=updates)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "TransactionCanceledException":
            raise
        # Only an actual cursor/owner change is a harmless duplicate, not throttling.
        current = ddbo.get_movie(job.movie_id)
        if (current.get(RESET_NEXT_FRAME) == cursor
                and progress(current, job.job_id).state == RUNNING):
            raise


def process(job: async_work.ResetJob, *, max_batches=MAX_BATCHES):
    """Yield after bounded work; retries resume the durable cursor, never restart."""
    ddbo = odb.DDBO()
    deadline = time.monotonic() + WORK_SECONDS
    for _ in range(min(max_batches, MAX_BATCHES)):
        movie = ddbo.get_movie(job.movie_id)
        if progress(movie, job.job_id).state != RUNNING:
            return
        if time.monotonic() >= deadline:
            break
        reset_batch(ddbo, job, movie)
    if progress(ddbo.get_movie(job.movie_id), job.job_id).state == RUNNING:
        # If publication fails, EventBridge/Lambda retries this same job and cursor.
        enqueue(job)
