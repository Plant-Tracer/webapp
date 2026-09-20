"""On-demand recoding against real DynamoDB, MinIO, and the local worker."""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from resize_app import lambda_tracing_handler, local_queue, recode
from app import apikey, local_lambda_debug, odb, odb_movie_data, s3_presigned
from app.schema import Trackpoint
from tests.fixtures.analysis_mp4_fixture import write_four_color_movie
from .selenium_utils import authenticate_browser


def seed_legacy(cfg, tmp_path):
    """A previously traced movie without an analysis descriptor."""
    movie_id = cfg[odb.MOVIE_ID]
    path = tmp_path / 'legacy.mp4'
    write_four_color_movie(path, width=640, height=480)
    odb_movie_data.set_movie_data(movie_id=movie_id, movie_data=path.read_bytes())
    ddbo = odb.DDBO()
    ddbo.update_movie(movie_id, {odb.RESIZED_AT: 1, odb.WIDTH: 640, odb.HEIGHT: 480,
                                odb.FRAME_HEIGHT_PX: 480, odb.TOTAL_FRAMES: 4,
                                odb.MOVIE_STATUS: odb.MOVIE_STATE_TRACING_COMPLETED,
                                odb.LAST_FRAME_TRACKED: 3})
    ddbo.put_movie_frame({odb.MOVIE_ID: movie_id, odb.FRAME_NUMBER: 2,
                          'trackpoints': [Trackpoint(x=21, y=34, label='Saved').model_dump()]})
    return ddbo


def test_recode_single_reservation_fences_duplicates_and_preserves_data(new_movie_record, tmp_path):
    cfg = new_movie_record
    ddbo = seed_legacy(cfg, tmp_path)
    movie_id = cfg[odb.MOVIE_ID]
    before = ddbo.get_movie(movie_id)
    frames = ddbo.get_frames(movie_id)
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = list(pool.map(lambda _: recode.reserve(before), range(6)))
    job, = [job for job in jobs if job]
    client = local_lambda_debug.bridge_app.test_client()
    url = '/resize-api/v1/prepare-analysis'
    assert client.post(url, json={'movie_id': movie_id}).status_code == 401
    response = client.post(url, json={'movie_id': movie_id}, headers={'x-api-key': cfg[odb.API_KEY]})
    assert response.status_code == 202
    assert response.get_json()['message'] == recode.MESSAGE
    with pytest.raises(odb.MovieAnalysisLocked):
        ddbo.acquire_movie_analysis_lock(movie=ddbo.get_movie(movie_id),
                                         started_by_user_id=cfg[odb.USER_ID], started_by_user_name='Test')
    with pytest.raises(odb.MovieTracingLocked):
        ddbo.acquire_movie_trace_lock(movie=ddbo.get_movie(movie_id),
                                      started_by_user_id=cfg[odb.USER_ID], started_by_user_name='Test')
    lambda_tracing_handler.process_job(job)
    after = ddbo.get_movie(movie_id)
    assert after[odb.ANALYSIS_MP4]
    assert after[odb.MOVIE_STATUS] == odb.MOVIE_STATE_TRACING_COMPLETED
    assert after[odb.LAST_FRAME_TRACKED] == 3
    assert ddbo.get_frames(movie_id) == frames
    assert odb_movie_data.read_object(after[odb.MOVIE_DATA_URN]) == (tmp_path / 'legacy.mp4').read_bytes()
    lambda_tracing_handler.process_job(job)
    assert ddbo.get_movie(movie_id) == after
    assert client.post(url, json={'movie_id': movie_id},
                       headers={'x-api-key': cfg[odb.API_KEY]}).get_json()['ready']


def test_recode_missing_object_uses_real_queue(new_movie_record, tmp_path, monkeypatch):
    ddbo = seed_legacy(new_movie_record, tmp_path)
    movie_id = new_movie_record[odb.MOVIE_ID]
    job = recode.reserve(ddbo.get_movie(movie_id))
    recode.process(job)
    original = ddbo.get_movie(movie_id)
    urn = original[odb.ANALYSIS_MP4]['urn']
    bucket, key = s3_presigned.parse_s3_urn(urn=urn)
    s3_presigned.s3_client().delete_object(Bucket=bucket, Key=key)
    monkeypatch.setenv('TRACING_QUEUE_MODE', 'local')
    local_queue.start_worker(processor=lambda_tracing_handler.process_local_queue_message)
    try:
        result = recode.prepare(api_key=new_movie_record[odb.API_KEY], request=recode.RecodeRequest(movie_id=movie_id))
        assert not result.ready
        deadline = time.monotonic() + 30
        while not ddbo.get_movie(movie_id).get(odb.ANALYSIS_MP4) and time.monotonic() < deadline:
            time.sleep(.05)
        assert odb_movie_data.read_object(ddbo.get_movie(movie_id)[odb.ANALYSIS_MP4]['urn'])
        assert ddbo.get_movie(movie_id)[odb.LAST_FRAME_TRACKED] == 3
    finally:
        local_queue.stop_worker(timeout=30)


@pytest.mark.selenium
def test_recode_browser_shows_pending_without_editing_lease(chrome_driver, live_server,
                                                           new_movie_record, tmp_path, monkeypatch):
    ddbo = seed_legacy(new_movie_record, tmp_path)
    movie_id = new_movie_record[odb.MOVIE_ID]
    monkeypatch.setenv('TRACING_QUEUE_MODE', 'local')
    local_queue.start_worker(processor=lambda_tracing_handler.process_local_queue_message)
    try:
        authenticate_browser(chrome_driver, live_server, new_movie_record[odb.API_KEY])
        chrome_driver.get(f'{live_server}/analyze?movie_id={movie_id}')
        WebDriverWait(chrome_driver, 30).until(
            lambda driver: driver.find_element(By.ID, 'status-big').text == recode.MESSAGE)
        assert ddbo.get_active_movie_analysis_lock(movie_id) is None
        WebDriverWait(chrome_driver, 30).until(lambda _: ddbo.get_movie(movie_id).get(odb.ANALYSIS_MP4))
        assert ddbo.get_frames(movie_id)[0]['trackpoints'][0]['label'] == 'Saved'
    finally:
        local_queue.stop_worker(timeout=30)


def test_recode_stale_job_and_failure_are_bounded(new_movie_record, tmp_path):
    ddbo = seed_legacy(new_movie_record, tmp_path)
    movie_id = new_movie_record[odb.MOVIE_ID]
    old = recode.reserve(ddbo.get_movie(movie_id))
    ddbo.update_movie(movie_id, {odb.PROCESSING_EXPIRES_AT: 1})
    current = recode.reserve(ddbo.get_movie(movie_id))
    snapshot = ddbo.get_movie(movie_id)
    recode.process(old)
    assert ddbo.get_movie(movie_id) == snapshot
    # A source-dimension conflict must preserve coordinates and stop automatic retries.
    ddbo.movies.update_item(Key={odb.MOVIE_ID: movie_id},
                           UpdateExpression='SET #width=:width',
                           ExpressionAttributeNames={'#width': odb.WIDTH},
                           ExpressionAttributeValues={':width': 800})
    with pytest.raises(recode.odb.MovieGeometryFinalized):
        recode.process(current)
    failed = ddbo.get_movie(movie_id)
    with pytest.raises(ValueError, match='Recoding failed'):
        recode.reserve(failed)
    recode.process(current)
    assert ddbo.get_movie(movie_id) == failed


def test_analyze_link_selects_movie_course(client, new_movie):
    other = f'other-{uuid.uuid4()}'
    odb.create_course(course_id=other, course_name='Other', course_key=f'key-{uuid.uuid4()}')
    try:
        user = odb.DDBO().get_user(new_movie[odb.USER_ID])
        odb.register_email(email=user[odb.EMAIL], user_name='Test', course_id=other)
        client.set_cookie(apikey.cookie_name(), new_movie[odb.API_KEY])
        assert client.patch('/api/default-course', json={odb.COURSE_ID: other}).status_code == 200
        response = client.get('/analyze', query_string={odb.MOVIE_ID: new_movie[odb.MOVIE_ID]})
        assert response.status_code == 302
        assert parse_qs(urlparse(response.location).query)[odb.COURSE_ID] == [new_movie[odb.COURSE_ID]]
        assert client.get(response.location).status_code == 200
        # Explicitly wrong course context is still rejected by the API.
        assert client.post('/api/acquire-movie-analysis-lease', data={
            odb.API_KEY: new_movie[odb.API_KEY], odb.MOVIE_ID: new_movie[odb.MOVIE_ID],
            odb.COURSE_ID: other}).status_code == 409
    finally:
        odb.delete_course(course_id=other)
