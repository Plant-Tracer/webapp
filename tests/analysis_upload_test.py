"""New uploads publish a validated playback MP4 and trace without ZIP artifacts."""
# pylint: disable=no-member

import hashlib

import cv2
import numpy as np
import pytest

from resize_app import movie_glue
from resize_app.analysis_mp4 import AnalysisMp4Options, rotate_frame, scale_frame
from resize_app.video_writer import H264Writer
from app import odb, odb_movie_data, s3_presigned
from app.schema import AnalysisMp4, Trackpoint


@pytest.mark.parametrize('width,height', [(640, 480), (480, 640), (1280, 960)])
@pytest.mark.parametrize('rotation', [0, 90, 270])
@pytest.mark.parametrize('source_frame', [0, 2])
def test_uploaded_mp4_is_rotated_scaled_complete_and_traceable(client, new_movie_record, tmp_path,
                                                              width, height, rotation, source_frame):
    """Compare decoded pixels, durable metadata, first-frame access and actual tracing."""
    movie_id = new_movie_record[odb.MOVIE_ID]
    source = tmp_path / 'source.mp4'
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:height // 2, :width // 2] = (230, 30, 30)
    frame[:height // 2, width // 2:] = (30, 230, 30)
    frame[height // 2:, :width // 2] = (30, 30, 230)
    frame[height // 2:, width // 2:] = (230, 230, 30)
    writer = H264Writer(source, fps=8)
    try:
        for _ in range(4):
            writer.append_data(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        writer.close()
    original = source.read_bytes()
    ddbo = odb.DDBO()
    ddbo.update_movie(movie_id, {odb.MOVIE_ROTATION: rotation})
    odb_movie_data.set_movie_data(movie_id=movie_id, movie_data=original)
    movie_glue.process_uploaded_movie(movie_id=movie_id)
    movie = ddbo.get_movie(movie_id)
    analysis = AnalysisMp4.model_validate(movie[odb.ANALYSIS_MP4])
    pixels = odb_movie_data.read_object(analysis.urn)
    output = tmp_path / 'analysis.mp4'
    output.write_bytes(pixels)
    expected = scale_frame(rotate_frame(frame, rotation), AnalysisMp4Options(max_width=640, max_height=640))
    assert (analysis.height, analysis.width) == expected.shape[:2]
    assert analysis.frame_count == movie[odb.TOTAL_FRAMES] == 4
    assert analysis.sha256 == hashlib.sha256(pixels).hexdigest()
    assert movie[odb.FRAME_HEIGHT_PX] == analysis.height
    assert analysis.urn != movie[odb.MOVIE_DATA_URN]
    assert odb_movie_data.read_object(movie[odb.MOVIE_DATA_URN]) == original
    capture = cv2.VideoCapture(str(output))
    try:
        assert capture.get(cv2.CAP_PROP_FPS) == 15
        for _ in range(4):
            success, decoded = capture.read()
            assert success
            # All four quadrants establish direction as well as rotated dimensions.
            for y in (analysis.height // 4, 3 * analysis.height // 4):
                for x in (analysis.width // 4, 3 * analysis.width // 4):
                    assert np.max(np.abs(decoded[y, x].astype(int) - expected[y, x].astype(int))) < 20
            assert np.any(np.all(decoded[:35, -45:] > 170, axis=2))  # burned-in frame label
        assert not capture.read()[0]
    finally:
        capture.release()
    params = {odb.MOVIE_ID: movie_id, odb.API_KEY: new_movie_record[odb.API_KEY]}
    metadata = client.post('/api/get-movie-metadata', data=params).get_json()['metadata']
    assert metadata[odb.ANALYSIS_MP4_URL]
    first = movie_glue.get_movie_url_and_rotation(api_key=params[odb.API_KEY], movie_id=movie_id)
    assert first.rotation == 0 and not first.transform
    assert '_scaled.mp4' in first.signed_url
    # An upload retry must retain the same validated derivative and source.
    movie_glue.process_uploaded_movie(movie_id=movie_id)
    assert ddbo.get_movie(movie_id)[odb.ANALYSIS_MP4] == movie[odb.ANALYSIS_MP4]
    odb.put_frame_trackpoints(movie_id=movie_id, frame_number=source_frame,
                             trackpoints=[Trackpoint(x=analysis.width // 2, y=analysis.height // 2, label='Apex')])
    assert movie_glue.run_tracing(movie_id=movie_id, frame_start=source_frame)
    traced = ddbo.get_movie(movie_id)
    assert traced[odb.LAST_FRAME_TRACKED] == 3
    assert traced[odb.MOVIE_TRACED_URN]
    traced_path = tmp_path / 'traced.mp4'
    traced_path.write_bytes(odb_movie_data.read_object(traced[odb.MOVIE_TRACED_URN]))
    capture = cv2.VideoCapture(str(traced_path))
    try:
        for _ in range(source_frame):
            assert capture.grab()
        success, traced_frame = capture.read()
        assert success
        # Traced output has marker overlays but no burned-in frame numbers.
        assert not np.any(np.all(traced_frame[:35, -45:] > 170, axis=2))
        assert np.max(np.abs(traced_frame[analysis.height // 2, analysis.width // 2].astype(int)
                             - expected[analysis.height // 2, analysis.width // 2].astype(int))) > 30
    finally:
        capture.release()
    assert not traced.get(odb.MOVIE_ZIPFILE_URN)
    bucket, source_key = s3_presigned.parse_s3_urn(urn=movie[odb.MOVIE_DATA_URN])
    objects = s3_presigned.s3_client().list_objects_v2(Bucket=bucket, Prefix=source_key.rsplit('.', 1)[0])
    assert not any('zip' in item['Key'] for item in objects.get('Contents', []))
    assert odb_movie_data.read_object(movie[odb.MOVIE_DATA_URN]) == original


def test_failed_recode_keeps_original_and_does_not_publish_derivative(new_movie_record):
    movie_id = new_movie_record[odb.MOVIE_ID]
    original = b'not a valid video'
    odb_movie_data.set_movie_data(movie_id=movie_id, movie_data=original)
    with pytest.raises((ValueError, RuntimeError)):
        movie_glue.process_uploaded_movie(movie_id=movie_id)
    movie = odb.DDBO().get_movie(movie_id)
    assert not movie.get(odb.ANALYSIS_MP4)
    assert movie[odb.MOVIE_STATUS] != odb.MOVIE_STATE_READY
    assert odb_movie_data.read_object(movie[odb.MOVIE_DATA_URN]) == original
