from pathlib import Path
import subprocess

import cv2
import imageio_ffmpeg
import numpy as np

from resize_app import tracer
from resize_app.src.app.schema import Trackpoint

# pylint: disable=no-member

TEST_MOVIE = Path(__file__).resolve().parents[2] / "tests/data/2019-07-31 plantmovie short.mov"
ANALYSIS_FRAME_HEIGHT = 480
NATIVE_FRAME_HEIGHT = 360
FRAME_HEIGHT_DIFFERENCE = ANALYSIS_FRAME_HEIGHT - NATIVE_FRAME_HEIGHT


def test_trace_movie_keeps_corrected_plantmovie_markers():
    frame_trackpoints = {}
    initial_trackpoints = [
        Trackpoint(x=455, y=ANALYSIS_FRAME_HEIGHT - (13 + FRAME_HEIGHT_DIFFERENCE),
                   label="Ruler 0mm", frame_number=0, undeletable=True),
        Trackpoint(x=396, y=ANALYSIS_FRAME_HEIGHT - (5 + FRAME_HEIGHT_DIFFERENCE),
                   label="Ruler 10mm", frame_number=0, undeletable=True),
        Trackpoint(x=370, y=ANALYSIS_FRAME_HEIGHT - (62 + FRAME_HEIGHT_DIFFERENCE),
                   label="Apex", frame_number=0),
    ]

    tracer.trace_movie_v2(
        movie_url=TEST_MOVIE,
        frame_start=0,
        trackpoints=initial_trackpoints,
        callback=lambda obj: frame_trackpoints.update({obj.frame_number: obj.frame_trackpoints}),
    )

    expected_labels = {"Ruler 0mm", "Ruler 10mm", "Apex"}
    assert frame_trackpoints
    assert all({point.label for point in points} == expected_labels
               for points in frame_trackpoints.values())


def test_trace_movie_moves_known_plant_feature():
    frame_trackpoints = {}

    tracer.trace_movie_v2(
        movie_url=TEST_MOVIE,
        frame_start=0,
        trackpoints=[Trackpoint(x=370, y=298, label="Apex", frame_number=0)],
        callback=lambda obj: frame_trackpoints.update({obj.frame_number: obj.frame_trackpoints}),
    )

    final_apex = frame_trackpoints[max(frame_trackpoints)][0]
    assert final_apex.x < 365
    assert final_apex.y < 292


def test_trace_movie_writes_a_decodable_h264_derivative(tmp_path):
    output_path = tmp_path / "traced.mp4"

    tracer.trace_movie_v2(
        movie_url=TEST_MOVIE,
        frame_start=0,
        trackpoints=[Trackpoint(x=370, y=298, label="Apex", frame_number=0)],
        movie_traced_path=output_path,
        callback=None,
    )

    capture = cv2.VideoCapture(str(output_path))
    try:
        success, frame = capture.read()
    finally:
        capture.release()
    assert success
    assert frame is not None
    description = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(output_path)],
        check=False,
        capture_output=True,
        text=True,
    ).stderr
    assert "Video: h264" in description


def test_preserve_missing_trackpoints_copies_every_missing_marker():
    previous_trackpoints = [
        Trackpoint(x=1, y=2, label="Apex", frame_number=4),
        Trackpoint(x=10, y=20, label="Ruler 0mm", frame_number=4, color="red", undeletable=True),
        Trackpoint(x=30, y=40, label="Ruler10mm", frame_number=4),
        Trackpoint(x=50, y=60, label="Tip", frame_number=4),
    ]
    output_trackpoints = [
        Trackpoint(x=2, y=3, label="Apex", frame_number=5),
        Trackpoint(x=31, y=41, label="Ruler10mm", frame_number=5),
    ]

    result = tracer.preserve_missing_trackpoints(
        previous_trackpoints=previous_trackpoints,
        output_trackpoints=output_trackpoints,
        frame_number=5,
    )

    assert result == [
        Trackpoint(x=2, y=3, label="Apex", frame_number=5),
        Trackpoint(x=31, y=41, label="Ruler10mm", frame_number=5),
        Trackpoint(x=10, y=20, label="Ruler 0mm", frame_number=5, color="red", undeletable=True),
        Trackpoint(x=50, y=60, label="Tip", frame_number=5),
    ]


def test_cv2_trace_frame_carries_every_marker_cv2_drops(monkeypatch):
    previous_trackpoints = [
        Trackpoint(x=1, y=2, label="Apex", frame_number=4, color="orange"),
        Trackpoint(x=10, y=20, label="Ruler 0mm", frame_number=4, color="red", undeletable=True),
        Trackpoint(x=30, y=40, label="Ruler 10mm", frame_number=4, color="red", undeletable=True),
        Trackpoint(x=50, y=60, label="Tip", frame_number=4, color="blue"),
    ]

    def fake_optical_flow(_gray_frame_prev, _gray_frame, _input_points, _unused, **_kwargs):
        points = np.array([
            [2, 3],
            [11, 21],
            [31, 41],
            [51, 61],
        ], dtype=np.float32)
        status = np.array([[1], [0], [1], [0]], dtype=np.uint8)
        return points, status, None

    monkeypatch.setattr(tracer.cv2, "calcOpticalFlowPyrLK", fake_optical_flow)

    result = tracer.cv2_trace_frame(
        gray_frame_prev=np.zeros((8, 8), dtype=np.uint8),
        gray_frame=np.zeros((8, 8), dtype=np.uint8),
        trackpoints=previous_trackpoints,
        frame_number=5,
    )

    assert result == [
        Trackpoint(x=2, y=3, label="Apex", frame_number=5, color="orange"),
        Trackpoint(x=31, y=41, label="Ruler 10mm", frame_number=5, color="red", undeletable=True),
        Trackpoint(x=10, y=20, label="Ruler 0mm", frame_number=5, color="red", undeletable=True),
        Trackpoint(x=50, y=60, label="Tip", frame_number=5, color="blue"),
    ]


def test_cv2_trace_frame_preserves_all_markers_when_cv2_errors(monkeypatch):
    class FakeCv2Error(Exception):
        pass

    previous_trackpoints = [
        Trackpoint(x=1, y=2, label="Apex", frame_number=4, color="orange"),
        Trackpoint(x=10, y=20, label="Ruler 0mm", frame_number=4, color="red", undeletable=True),
    ]

    def fake_optical_flow(_gray_frame_prev, _gray_frame, _input_points, _unused, **_kwargs):
        raise FakeCv2Error("optical flow failed")

    monkeypatch.setattr(tracer.cv2, "error", FakeCv2Error)
    monkeypatch.setattr(tracer.cv2, "calcOpticalFlowPyrLK", fake_optical_flow)

    result = tracer.cv2_trace_frame(
        gray_frame_prev=np.zeros((8, 8), dtype=np.uint8),
        gray_frame=np.zeros((8, 8), dtype=np.uint8),
        trackpoints=previous_trackpoints,
        frame_number=5,
    )

    assert result == [
        Trackpoint(x=1, y=2, label="Apex", frame_number=5, color="orange"),
        Trackpoint(x=10, y=20, label="Ruler 0mm", frame_number=5, color="red", undeletable=True),
    ]


def test_update_trackpoint_segments_adds_lines_for_matching_labels_only():
    segments = []

    tracer.update_trackpoint_segments(
        previous_trackpoints=[
            Trackpoint(x=1, y=2, label="Apex", frame_number=0),
            Trackpoint(x=5, y=6, label="Other", frame_number=0),
        ],
        current_trackpoints=[
            Trackpoint(x=3, y=4, label="Apex", frame_number=1),
            Trackpoint(x=7, y=8, label="Different", frame_number=1),
        ],
        segments=segments,
    )

    assert segments == [
        tracer.TrackpointSegment(label="Apex", x1=1, y1=2, x2=3, y2=4),
    ]


def test_cv2_label_frame_draws_trackpoint_segments_before_markers():
    frame = np.zeros((12, 12, 3), dtype=np.uint8)

    tracer.cv2_label_frame(
        frame=frame,
        trackpoints=[Trackpoint(x=9, y=6, label="Apex", frame_number=1)],
        trackpoint_segments=[
            tracer.TrackpointSegment(label="Apex", x1=2, y1=6, x2=9, y2=6),
        ],
        colors_by_label={"Apex": tracer.ORANGE},
    )

    assert frame[6, 5].tolist() == list(tracer.ORANGE)
    assert frame[6, 9].tolist() == list(tracer.ORANGE)


def test_trackpoint_colors_prefer_marker_color_property():
    colors = tracer.trackpoint_colors([
        Trackpoint(x=1, y=2, label="Apex", color="#0096ff"),
        Trackpoint(x=3, y=4, label="Base", color="#0096ff"),
        Trackpoint(x=5, y=6, label="Ruler 0mm", color="#0096ff"),
        Trackpoint(x=7, y=8, label="Tip"),
    ])

    assert colors["Apex"] == tracer.ORANGE
    assert colors["Base"] == tracer.BRIGHT_BLUE
    assert colors["Ruler 0mm"] == tracer.RED
    assert colors["Tip"] == tracer.MAGENTA


def test_future_path_opacity_width_and_past_overlap():
    """Future pixels are half-opacity/thin; past segments cover them completely."""
    points = {number: [Trackpoint(x=x, y=40, label='Apex', frame_number=number)]
              for number, x in enumerate((10, 40, 70))}
    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    overlay = tracer.trace_path_overlay(frame, points, 0, 2, {'Apex': tracer.ORANGE})
    tracer.cv2_label_frame(frame=frame, trackpoints=[], path_overlay=overlay,
                           colors_by_label={'Apex': tracer.ORANGE}, trackpoint_segments=[
                               tracer.TrackpointSegment(label='Apex', x1=10, y1=40, x2=40, y2=40)])
    assert frame[40, 55].tolist() == [0, 82, 128]
    assert not frame[39, 55].any()
    assert not frame[41, 55].any()
    assert frame[40, 25].tolist() == list(tracer.ORANGE)
    assert frame[39, 25].tolist() == list(tracer.ORANGE)


def test_render_only_download_includes_future_paths_inside_trim(tmp_path):
    source, output = tmp_path / 'source.mp4', tmp_path / 'traced.mp4'
    writer = tracer.H264Writer(source, fps=15)
    for _ in range(5):
        writer.append_data(np.zeros((480, 640, 3), dtype=np.uint8))
    writer.close()
    points = [Trackpoint(x=x, y=200, label='Apex', frame_number=number)
              for number, x in enumerate((20, 100, 300, 500, 600))]
    points += [Trackpoint(x=x, y=350, label='Gap', frame_number=number)
               for number, x in ((1, 100), (3, 500))]
    tracer.trace_movie_v2(movie_url=source, frame_start=0, trackpoints=points,
                          render_only=True, movie_traced_path=output, callback=None,
                          movie_traced_frame_range=tracer.TracedMovieFrameRange(start=1, end=3))
    capture = cv2.VideoCapture(str(output))
    decoded = []
    while True:
        success, frame = capture.read()
        if not success:
            break
        decoded.append(frame)
    capture.release()
    assert len(decoded) == 3
    future_red = decoded[0][197:204, 350:450, 2].astype(int).sum()
    past_red = decoded[-1][197:204, 350:450, 2].astype(int).sum()
    assert future_red > 5000  # Future segment is present in the first downloaded frame.
    assert past_red > 3 * future_red  # Wider and fully opaque after reaching it.
    for frame in decoded:
        assert frame[195:205, 45:65].max() < 10  # Before trim start.
        assert frame[195:205, 545:565].max() < 10  # After trim end.
        assert frame[345:355, 250:350].max() < 10  # Missing marker frame is not bridged.


def test_new_tracing_renders_computed_future_positions(tmp_path):
    """New tracking must finish before the first export frame is annotated."""
    source, output = tmp_path / 'moving.mp4', tmp_path / 'traced.mp4'
    patch = np.random.default_rng(7).integers(0, 256, (32, 32, 1), dtype=np.uint8).repeat(3, axis=2)
    writer = tracer.H264Writer(source, fps=15)
    for number in range(6):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[104:136, 64 + number * 8:96 + number * 8] = patch
        writer.append_data(frame)
    writer.close()
    tracked, rendered = [], []
    points = tracer.trace_movie_v2(
        movie_url=source, frame_start=0,
        trackpoints=[Trackpoint(x=80, y=120, label='Apex', frame_number=0)],
        movie_traced_path=output, callback=tracked.append, render_callback=rendered.append)
    assert abs(float(points[-1].x) - 120) < 1
    assert [obj.frame_number for obj in tracked] == list(range(6))
    assert [obj.frame_number for obj in rendered] == list(range(6))
    capture = cv2.VideoCapture(str(output))
    success, first = capture.read()
    capture.release()
    assert success
    # This region is black in source frame zero and well outside its current marker.
    assert first[117:124, 105:113, 2].astype(int).sum() > 400


def test_download_label_uses_capture_time_and_original_zero_based_frame(tmp_path):
    """A trimmed download keeps original frame indices and uses capture, not playback time."""
    output = tmp_path / 'timed.mp4'
    tracer.trace_movie_v2(
        movie_url=TEST_MOVIE, frame_start=1, frame_end=2,
        trackpoints=[Trackpoint(x=370, y=298, label="Apex", frame_number=0)],
        movie_traced_path=output,
        movie_traced_frame_range=tracer.TracedMovieFrameRange(start=2, end=2, seconds_per_frame=30),
        callback=None,
    )
    capture = cv2.VideoCapture(str(output))
    success, decoded = capture.read()
    assert not capture.read()[0]
    capture.release()
    assert success
    reference = np.zeros_like(decoded)
    tracer.cv2_label_frame(frame=reference, trackpoints=[], frame_label="2  60 s")
    # Blue pixels establish export styling; white glyph pixels distinguish the exact label.
    region = decoded[:35, -140:].astype(int)
    assert np.any((region[:, :, 0] > 150) & (region[:, :, 2] < 100))
    glyphs = np.all(reference[:35, -140:] > 200, axis=2)
    assert glyphs.sum() > 100
    assert np.mean(region[glyphs]) > 175
