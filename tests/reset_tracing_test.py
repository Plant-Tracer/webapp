"""Range resets against real DynamoDB Local, including stale delivery fencing."""

import os
import time
import threading
from decimal import Decimal

import pytest
from pydantic import ValidationError

from resize_app import async_work, lambda_tracing_handler, local_queue, reset_tracing

from app import local_lambda_debug, odb
from app.schema import Trackpoint
from app.constants import C


def _seed_movie(cfg, count=205):
    ddbo = odb.DDBO()
    movie_id = cfg[odb.MOVIE_ID]
    ddbo.update_movie(movie_id, {odb.TOTAL_FRAMES: count, odb.UPLOADED_AT: int(time.time()),
                                odb.MOVIE_STATUS: odb.MOVIE_STATE_READY})
    with ddbo.movie_frames.batch_writer() as writer:
        for frame in range(count):
            writer.put_item(Item={odb.MOVIE_ID: movie_id, odb.FRAME_NUMBER: frame,
                                  odb.FRAME_URN: f"s3://{os.environ[C.PLANTTRACER_S3_BUCKET]}/{movie_id}/frame-{frame}",
                                  reset_tracing.TRACKPOINTS: [Trackpoint(x=10, y=20, label="Old").model_dump()]})
    return ddbo


def _start_job(cfg, *, start=1, end=203, seed=4):
    ddbo = odb.DDBO()
    movie_id = cfg[odb.MOVIE_ID]
    lock = ddbo.acquire_movie_trace_lock(movie=ddbo.get_movie(movie_id),
                                        started_by_user_id=cfg[odb.USER_ID], started_by_user_name="Test")
    job = async_work.ResetJob(movie_id=movie_id, job_id=lock.job_id, frame_start=start,
                              frame_end=end, seed_frame=seed,
                              trackpoints=[Trackpoint(x=Decimal("10.2"), y=Decimal("20.7"), label="Apex").model_dump()])
    ddbo.update_movie(movie_id, {reset_tracing.RESET_JOB_ID: job.job_id,
                                reset_tracing.RESET_NEXT_FRAME: start,
                                reset_tracing.RESET_END_FRAME: end,
                                reset_tracing.RESET_STATE: reset_tracing.RUNNING,
                                odb.NEEDS_RETRACING: 1})
    return job


def test_reset_range_resumes_and_preserves_frame_data(new_movie_record):
    ddbo = _seed_movie(new_movie_record)
    job = _start_job(new_movie_record)
    original = ddbo.get_movie(job.movie_id)
    reset_tracing.reset_batch(ddbo, job, original)
    checkpoint = ddbo.get_movie(job.movie_id)
    assert checkpoint[reset_tracing.RESET_NEXT_FRAME] == 81
    assert ddbo.get_movie_frame(job.movie_id, 81)[reset_tracing.TRACKPOINTS]
    # A duplicate of the first batch cannot advance the cursor or repeat its writes.
    reset_tracing.reset_batch(ddbo, job, original)
    assert ddbo.get_movie(job.movie_id)[reset_tracing.RESET_NEXT_FRAME] == 81
    lambda_tracing_handler.process_job(job)
    movie = ddbo.get_movie(job.movie_id)
    assert reset_tracing.progress(movie, job.job_id).state == reset_tracing.COMPLETED
    assert odb.movie_trace_lock_from_record(movie) is None
    assert movie[odb.NEEDS_RETRACING] == 1
    assert movie[odb.LAST_FRAME_TRACKED] == 204
    frames = {int(frame[odb.FRAME_NUMBER]): frame for frame in ddbo.get_frames(job.movie_id)}
    for number in range(205):
        assert frames[number][odb.FRAME_URN] == f"s3://{os.environ[C.PLANTTRACER_S3_BUCKET]}/{job.movie_id}/frame-{number}"
        if number in (0, 204):
            assert frames[number][reset_tracing.TRACKPOINTS][0]['label'] == 'Old'
        elif number == 4:
            point = frames[number][reset_tracing.TRACKPOINTS][0]
            assert (point['x'], point['y'], point['label']) == (Decimal('10.2'), Decimal('20.7'), 'Apex')
            assert point[odb.FRAME_NUMBER] == 4
        else:
            assert reset_tracing.TRACKPOINTS not in frames[number]
    # A late delivery after new user edits must be a complete no-op.
    odb.put_frame_trackpoints(movie_id=job.movie_id, frame_number=20,
                             trackpoints=[Trackpoint(x=9, y=8, label='New edit')])
    reset_tracing.reset_batch(ddbo, job, original)
    lambda_tracing_handler.process_job(job)
    assert ddbo.get_movie_frame(job.movie_id, 20)[reset_tracing.TRACKPOINTS][0]['label'] == 'New edit'


def test_reset_expired_lease_and_replacement_worker_cannot_write(new_movie_record):
    ddbo = _seed_movie(new_movie_record, count=5)
    job = _start_job(new_movie_record, start=0, end=4, seed=0)
    snapshot = ddbo.get_movie(job.movie_id)
    ddbo.update_movie(job.movie_id, {odb.TRACE_LOCK_EXPIRES_AT: 1})
    assert reset_tracing.progress(ddbo.get_movie(job.movie_id), job.job_id).state == 'expired'
    reset_tracing.reset_batch(ddbo, job, snapshot)
    replacement = _start_job(new_movie_record, start=0, end=4, seed=0)
    reset_tracing.reset_batch(ddbo, job, snapshot)
    assert ddbo.get_movie_frame(job.movie_id, 2)[reset_tracing.TRACKPOINTS]
    reset_tracing.process(replacement)
    movie = ddbo.get_movie(job.movie_id)
    assert movie[odb.LAST_FRAME_TRACKED] == 0
    assert reset_tracing.progress(movie, job.job_id).state == 'superseded'


def test_reopened_analysis_permanently_fences_expired_reset(new_movie_record):
    ddbo = _seed_movie(new_movie_record, count=5)
    job = _start_job(new_movie_record, start=0, end=4, seed=0)
    old_snapshot = ddbo.get_movie(job.movie_id)
    ddbo.update_movie(job.movie_id, {odb.TRACE_LOCK_EXPIRES_AT: 1})
    lease = ddbo.acquire_movie_analysis_lock(movie=ddbo.get_movie(job.movie_id),
                                             started_by_user_id=new_movie_record[odb.USER_ID],
                                             started_by_user_name='New browser')
    assert odb.TRACE_JOB_ID not in ddbo.get_movie(job.movie_id)
    odb.put_frame_trackpoints(movie_id=job.movie_id, frame_number=2,
                             trackpoints=[Trackpoint(x=9, y=8, label='New edit')])
    ddbo.release_movie_analysis_lock(movie_id=job.movie_id, lease_id=lease.lease_id,
                                     user_id=new_movie_record[odb.USER_ID])
    # Even a transaction prepared before expiry has permanently lost its job token.
    reset_tracing.reset_batch(ddbo, job, old_snapshot)
    assert ddbo.get_movie_frame(job.movie_id, 2)[reset_tracing.TRACKPOINTS][0]['label'] == 'New edit'


def test_reset_http_range_and_validation(new_movie_record, monkeypatch):
    ddbo = _seed_movie(new_movie_record, count=180)
    movie_id = new_movie_record[odb.MOVIE_ID]
    client = local_lambda_debug.bridge_app.test_client()
    headers = {'x-api-key': new_movie_record[odb.API_KEY]}
    payload = async_work.ResetRequest(movie_id=movie_id, frame_start=0, frame_end=179, seed_frame=5,
                                      trackpoints=[Trackpoint(x=50, y=50, label='Apex').model_dump()]).model_dump(mode='json')
    url = '/resize-api/v1/reset-tracing'
    assert client.post(url, json=payload).status_code == 401
    invalid = {**payload, 'frame_end': 180}
    assert client.post(url, json=invalid, headers=headers).status_code == 400
    assert odb.movie_trace_lock_from_record(ddbo.get_movie(movie_id)) is None
    lease = ddbo.acquire_movie_analysis_lock(movie=ddbo.get_movie(movie_id),
                                             started_by_user_id=new_movie_record[odb.USER_ID],
                                             started_by_user_name='Test')
    assert client.post(url, json=payload, headers=headers).status_code == 409
    payload[odb.ANALYSIS_LEASE_ID] = lease.lease_id
    monkeypatch.setenv('TRACING_QUEUE_MODE', 'local')
    local_queue.start_worker(processor=lambda_tracing_handler.process_local_queue_message)
    try:
        response = client.post(url, json=payload, headers=headers)
        assert response.status_code == 202, response.data
        job_id = response.json['job_id']
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            status = client.get(url, query_string={odb.MOVIE_ID: movie_id, 'job_id': job_id}, headers=headers)
            assert status.status_code == 200, status.data
            if status.json['state'] != 'running':
                break
            time.sleep(0.05)
        assert status.json['state'] == 'completed'
        assert ddbo.get_movie(movie_id)[odb.LAST_FRAME_TRACKED] == 5
        assert not ddbo.get_movie_frame(movie_id, 179).get(reset_tracing.TRACKPOINTS)
        assert client.get(url, query_string={odb.MOVIE_ID: movie_id, 'job_id': job_id}).status_code == 403
    finally:
        local_queue.stop_worker()


def test_reset_continuation_uses_durable_cursor(new_movie_record, monkeypatch):
    ddbo = _seed_movie(new_movie_record)
    job = _start_job(new_movie_record, start=0, end=204, seed=0)
    monkeypatch.setenv('TRACING_QUEUE_MODE', 'local')
    completed = threading.Event()
    cursors = []

    def process_continuation(message):
        cursors.append(ddbo.get_movie(job.movie_id)[reset_tracing.RESET_NEXT_FRAME])
        lambda_tracing_handler.process_local_queue_message(message)
        completed.set()

    local_queue.start_worker(processor=process_continuation)
    try:
        reset_tracing.process(job, max_batches=1)
        assert completed.wait(20)
        assert cursors == [80]
        assert reset_tracing.progress(ddbo.get_movie(job.movie_id), job.job_id).state == 'completed'
        assert not ddbo.get_movie_frame(job.movie_id, 204).get(reset_tracing.TRACKPOINTS)
    finally:
        local_queue.stop_worker()


@pytest.mark.parametrize('start,end,seed', [(-1, 10, 0), (10, 9, 10), (0, 10, 11), (0, 50000, 0)])
def test_reset_rejects_invalid_ranges(start, end, seed):
    with pytest.raises(ValidationError):
        async_work.ResetRequest(movie_id='mtest', frame_start=start, frame_end=end, seed_frame=seed,
                                trackpoints=[Trackpoint(x=0, y=0, label='Apex').model_dump()])
