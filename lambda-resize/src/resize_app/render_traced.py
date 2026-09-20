"""On-demand traced MP4 rendering; never run tracking or change saved points."""

import tempfile
import time
from pathlib import Path

from botocore.exceptions import ClientError
from pydantic import BaseModel

from . import async_work, movie_glue, tracer
from .analysis_mp4 import AnalysisMp4Options
from .src.app import mp4_metadata_lib, odb, s3_presigned
from .src.app.movie_render import render_input_values, render_key
from .src.app.odb_movie_data import write_object_from_path
from .src.app.schema import Trackpoint

MESSAGE = 'Re-rendering; download the traced movie in a few minutes.'


class RenderRequest(BaseModel):
    """Server-selected source and trim; the client supplies no output parameters."""

    movie_id: str
    analysis_lease_id: str | None = None


class RenderResponse(BaseModel):
    """Either a current download or one already-reserved background render."""

    ready: bool = False
    url: str | None = None
    message: str = MESSAGE
    error: bool = False


def prepare(*, api_key, request: RenderRequest):
    """Resolve a current export, or reserve one job before sending an event."""
    ddbo, user_id, movie = movie_glue.validate_movie_access(api_key=api_key, movie_id=request.movie_id)
    if not odb.movie_is_available(movie) or not movie.get(odb.TOTAL_FRAMES):
        raise ValueError('Movie upload processing is not complete.')
    lock = odb.movie_trace_lock_from_record(movie)
    if lock:
        if lock.purpose == 'render_traced':
            return RenderResponse()
        raise odb.MovieTracingLocked('Movie work is in progress. Try the download again later.')
    if movie.get(odb.PROCESSING_EXPIRES_AT, 0) > time.time():
        raise odb.MovieTracingLocked('The untraced MP4 is being rendered. Try again later.')
    urn = movie.get(odb.MOVIE_TRACED_URN)
    if urn and movie.get(odb.TRACED_RENDER_KEY) == render_key(movie):
        if s3_presigned.object_exists(urn):
            return RenderResponse(ready=True, url=s3_presigned.make_signed_url(urn=urn), message='')
    try:
        lock = ddbo.acquire_movie_work_lock(
            movie=movie, purpose='render_traced', started_by_user_id=user_id,
            started_by_user_name=ddbo.get_user(user_id)[odb.USER_NAME],
            analysis_lease_id=request.analysis_lease_id)
    except odb.MovieTracingLocked:
        current = ddbo.get_active_movie_trace_lock(request.movie_id)
        if current and current.purpose == 'render_traced':
            return RenderResponse()
        raise
    job = async_work.RenderTracedJob(movie_id=request.movie_id, job_id=lock.job_id)
    try:
        async_work.enqueue_job(job)
    except Exception:
        ddbo.finish_movie_trace(movie_id=job.movie_id, job_id=job.job_id,
                               updates={odb.RENDER_FAILED_AT: int(time.time()),
                                        odb.RENDER_FAILURE_SUMMARY: 'Could not queue rendering. Request the download again.'})
        raise
    return RenderResponse()


def process(job: async_work.RenderTracedJob):
    """Claim once, render a stable snapshot, and conditionally publish a new object."""
    ddbo = odb.DDBO()
    if not ddbo.claim_movie_trace_lock(movie_id=job.movie_id, job_id=job.job_id):
        return
    try:
        movie = ddbo.get_movie(job.movie_id)
        if movie.get(odb.WORK_PURPOSE) != 'render_traced':
            raise ValueError('Job does not own a traced rendering lease')
        frame_height = movie.get(odb.FRAME_HEIGHT_PX)
        if not frame_height:
            raise ValueError('Open Analyze to prepare the untraced MP4 before downloading.')
        points = [Trackpoint(**point) for point in odb.get_movie_trackpoints(movie_id=job.movie_id)]
        if movie.get(odb.TRACKPOINT_ORIGIN) == odb.TRACKPOINT_ORIGIN_BOTTOM_LEFT:
            points = odb.flip_trackpoints_y(points, int(frame_height))
        first, last = odb.movie_trim_bounds(movie)
        heartbeat_at = time.monotonic()

        def progress(_frame):
            nonlocal heartbeat_at
            if time.monotonic() - heartbeat_at >= 30:
                ddbo.heartbeat_movie_trace_lock(movie_id=job.movie_id, job_id=job.job_id)
                heartbeat_at = time.monotonic()

        source = s3_presigned.make_signed_url(urn=movie[odb.MOVIE_DATA_URN])
        with tempfile.TemporaryDirectory(prefix='traced-render-') as directory:
            path = Path(directory) / 'traced.mp4'
            tracer.trace_movie_v2(
                movie_url=source, frame_start=0, trackpoints=points, render_only=True,
                movie_traced_path=path,
                render_source=(source, AnalysisMp4Options(rotation=movie_glue.movie_rotation(movie),
                                                        frame_height=int(frame_height))),
                movie_traced_frame_range=tracer.TracedMovieFrameRange(
                    start=first, end=last,
                    seconds_per_frame=(60 / float(movie[odb.FPM]) if float(movie.get(odb.FPM) or 0) > 0 else None)),
                callback=progress,
                comment=mp4_metadata_lib.build_comment(movie.get(odb.RESEARCH_USE, 0) or 0,
                                                      movie.get(odb.CREDIT_BY_NAME, 0) or 0,
                                                      movie.get(odb.ATTRIBUTION_NAME)))
            if movie.get(odb.FPM):
                mp4_metadata_lib.set_fpm(str(path), movie[odb.FPM])
            ddbo.heartbeat_movie_trace_lock(movie_id=job.movie_id, job_id=job.job_id)
            urn = s3_presigned.traced_movie_urn(movie_data_urn=movie[odb.MOVIE_DATA_URN], render_id=job.job_id)
            write_object_from_path(urn=urn, path=path)
            ddbo.finish_movie_trace(
                movie_id=job.movie_id, job_id=job.job_id, expected_inputs=render_input_values(movie),
                updates={odb.MOVIE_TRACED_URN: urn, odb.TRACED_RENDER_KEY: render_key(movie),
                         odb.RENDER_FAILED_AT: None, odb.RENDER_FAILURE_SUMMARY: None})
    except Exception as exc:
        movie_glue.LOGGER.exception('Traced rendering failed movie_id=%s', job.movie_id)
        try:
            ddbo.finish_movie_trace(movie_id=job.movie_id, job_id=job.job_id,
                                   updates={odb.RENDER_FAILED_AT: int(time.time()),
                                            odb.RENDER_FAILURE_SUMMARY: str(exc)[:500]})
        except ClientError:
            movie_glue.LOGGER.info('Discarding stale render failure movie_id=%s job_id=%s', job.movie_id, job.job_id)
        raise
