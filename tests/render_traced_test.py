"""Render-only downloads against real DynamoDB, MinIO, and encoded MP4s."""
# pylint: disable=no-member

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import pytest
from botocore.exceptions import ClientError

from resize_app import async_work, lambda_tracing_handler, local_queue, recode, render_traced, tracer

from app import local_lambda_debug, odb, odb_movie_data
from app.movie_render import render_input_values, render_key
from app.schema import Trackpoint
from .recode_test import seed_legacy


def seed_render(cfg, tmp_path):
    """Saved points deliberately start after zero; rendering cannot require a trace seed."""
    ddbo = seed_legacy(cfg, tmp_path)
    movie_id = cfg[odb.MOVIE_ID]
    for frame in (1, 2, 3):
        odb.put_frame_trackpoints(movie_id=movie_id, frame_number=frame,
                                 trackpoints=[Trackpoint(x=100 + frame * 10, y=200, label='Saved', frame_number=frame)],
                                 needs_retracing=True)
    ddbo.update_movie(movie_id, {odb.TRIM_START_FRAME: 1, odb.TRIM_END_FRAME: 2, odb.FPM: '60'})
    return ddbo


def test_download_renders_trim_once_and_keeps_saved_data(new_movie_record, tmp_path, monkeypatch):
    cfg = new_movie_record
    ddbo = seed_render(cfg, tmp_path)
    movie_id = cfg[odb.MOVIE_ID]
    before = ddbo.get_movie(movie_id)
    frames = ddbo.get_frames(movie_id)
    jobs, errors = [], []
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def processor(body):
        jobs.append(body)
        entered.set()
        try:
            if not release.wait(10):
                raise TimeoutError('test did not release worker')
            lambda_tracing_handler.process_local_queue_message(body)
        except (RuntimeError, ValueError, ClientError) as exc:  # propagate worker errors to the test thread
            errors.append(exc)
        finally:
            finished.set()

    monkeypatch.setenv('TRACING_QUEUE_MODE', 'local')
    local_queue.start_worker(processor=processor)
    try:
        request = render_traced.RenderRequest(movie_id=movie_id)
        with ThreadPoolExecutor(max_workers=6) as pool:
            replies = list(pool.map(lambda _: render_traced.prepare(api_key=cfg[odb.API_KEY], request=request), range(6)))
        assert all(not reply.ready and reply.message == render_traced.MESSAGE for reply in replies)
        assert entered.wait(5)
        lock = ddbo.get_active_movie_trace_lock(movie_id)
        assert lock.purpose == 'render_traced'
        with pytest.raises(odb.MovieTracingLocked):
            ddbo.acquire_movie_trace_lock(movie=before, started_by_user_id=cfg[odb.USER_ID], started_by_user_name='test')
        with pytest.raises(odb.MovieAnalysisLocked):
            ddbo.acquire_movie_analysis_lock(movie=before, started_by_user_id=cfg[odb.USER_ID], started_by_user_name='test')
        with pytest.raises(ValueError, match='edited or traced'):
            recode.reserve(ddbo.get_movie(movie_id))
        release.set()
        assert finished.wait(30)
        assert not errors
        assert len(jobs) == 1
        after = ddbo.get_movie(movie_id)
        assert ddbo.get_frames(movie_id) == frames
        for prop in (odb.NEEDS_RETRACING, odb.LAST_FRAME_TRACKED, odb.TOTAL_FRAMES, odb.MOVIE_DATA_URN, odb.MOVIE_STATUS):
            assert after[prop] == before[prop]
        assert not ddbo.get_active_movie_trace_lock(movie_id)
        assert after[odb.TRACED_RENDER_KEY] == render_key(after)
        movie_bytes = odb_movie_data.read_object(after[odb.MOVIE_TRACED_URN])
        path = tmp_path / 'download.mp4'
        path.write_bytes(movie_bytes)
        capture = cv2.VideoCapture(str(path))
        try:
            output = []
            while True:
                success, frame = capture.read()
                if not success:
                    break
                output.append(frame)
            assert len(output) == 2
            assert output[0].shape == (480, 640, 3)
            # Saved frame-1 marker is drawn at (110, 480-200), not retracked.
            assert not np.allclose(output[0][275:286, 105:116], [0, 255, 0], atol=8)
            # Original frames 1 and 2 are green and blue. Rendering does not renumber or replace them.
            assert np.max(np.abs(output[0][400, 50].astype(int) - [0, 255, 0])) < 8
            assert np.max(np.abs(output[1][400, 50].astype(int) - [255, 0, 0])) < 8
        finally:
            capture.release()
        client = local_lambda_debug.bridge_app.test_client()
        url = '/resize-api/v1/download-traced'
        assert client.post(url, json=request.model_dump()).status_code == 401
        response = client.post(url, json=request.model_dump(), headers={'x-api-key': cfg[odb.API_KEY]})
        assert response.status_code == 200 and response.get_json()['ready']
        assert len(jobs) == 1
        lambda_tracing_handler.process_local_queue_message(jobs[0])
        assert ddbo.get_movie(movie_id) == after
        # Trimming alone does no background work and keeps the old export reference.
        odb.set_movie_trim_frame(movie_id=movie_id, prop=odb.TRIM_END_FRAME, frame_number=3)
        assert len(jobs) == 1
        assert ddbo.get_movie(movie_id)[odb.MOVIE_TRACED_URN] == after[odb.MOVIE_TRACED_URN]
        finished.clear()
        response = client.post(url, json=request.model_dump(), headers={'x-api-key': cfg[odb.API_KEY]})
        assert response.status_code == 202 and not response.get_json()['ready']
        assert finished.wait(30)
        assert not errors and len(jobs) == 2
        updated = ddbo.get_movie(movie_id)
        assert updated[odb.MOVIE_TRACED_URN] != after[odb.MOVIE_TRACED_URN]
        assert updated[odb.TRACED_RENDER_KEY] == render_key(updated)
        assert ddbo.get_frames(movie_id) == frames
    finally:
        release.set()
        local_queue.stop_worker(timeout=30)


def test_render_lease_transfer_expiry_and_input_fencing(new_movie_record, tmp_path):
    cfg = new_movie_record
    ddbo = seed_render(cfg, tmp_path)
    movie_id = cfg[odb.MOVIE_ID]
    movie = ddbo.get_movie(movie_id)
    editor = ddbo.acquire_movie_analysis_lock(movie=movie, started_by_user_id=cfg[odb.USER_ID], started_by_user_name='test')
    with pytest.raises(odb.MovieTracingLocked):
        ddbo.acquire_movie_work_lock(movie=movie, purpose='render_traced', started_by_user_id=cfg[odb.USER_ID], started_by_user_name='test')
    lock = ddbo.acquire_movie_work_lock(movie=movie, purpose='render_traced', started_by_user_id=cfg[odb.USER_ID],
                                      started_by_user_name='test', analysis_lease_id=editor.lease_id)
    assert not ddbo.get_active_movie_analysis_lock(movie_id)
    assert ddbo.claim_movie_trace_lock(movie_id=movie_id, job_id=lock.job_id)
    assert not ddbo.claim_movie_trace_lock(movie_id=movie_id, job_id=lock.job_id)
    ddbo.update_movie(movie_id, {odb.TRIM_END_FRAME: 3})
    with pytest.raises(ClientError):
        ddbo.finish_movie_trace(movie_id=movie_id, job_id=lock.job_id,
                               updates={odb.TRACED_RENDER_KEY: render_key(movie)}, expected_inputs=render_input_values(movie))
    ddbo.update_movie(movie_id, {odb.TRACE_LOCK_EXPIRES_AT: int(time.time()) - 1})
    replacement = ddbo.acquire_movie_work_lock(movie=ddbo.get_movie(movie_id), purpose='render_traced',
                                              started_by_user_id=cfg[odb.USER_ID], started_by_user_name='test')
    with pytest.raises(ClientError):
        ddbo.finish_movie_trace(movie_id=movie_id, job_id=lock.job_id, updates={odb.TRACED_RENDER_KEY: 'stale'})
    render_traced.process(async_work.RenderTracedJob(movie_id=movie_id, job_id=lock.job_id))
    assert ddbo.get_active_movie_trace_lock(movie_id).job_id == replacement.job_id


def test_render_freshness_tracks_trim_markers_names_and_capture_time(new_movie_record, tmp_path):
    cfg = new_movie_record
    ddbo = seed_render(cfg, tmp_path)
    movie_id = cfg[odb.MOVIE_ID]
    previous = render_key(ddbo.get_movie(movie_id))
    for prop, value in ((odb.TRIM_END_FRAME, 3), (odb.FPM, '30')):
        ddbo.update_movie(movie_id, {prop: value})
        current = render_key(ddbo.get_movie(movie_id))
        assert current != previous
        previous = current
    odb.rename_movie_marker(movie_id=movie_id, old_label='Saved', new_label='Renamed')
    current = render_key(ddbo.get_movie(movie_id))
    assert current != previous
    odb.delete_movie_marker(movie_id=movie_id, label='Renamed')
    assert render_key(ddbo.get_movie(movie_id)) != current


def test_render_only_rejects_truncated_source(new_movie_record, tmp_path):
    seed_render(new_movie_record, tmp_path)
    with pytest.raises(ValueError, match='ended before'):
        tracer.trace_movie_v2(movie_url=str(tmp_path / 'legacy.mp4'), frame_start=0,
                              trackpoints=[], render_only=True, movie_traced_path=tmp_path / 'short.mp4',
                              movie_traced_frame_range=tracer.TracedMovieFrameRange(start=0, end=5))
