from pathlib import Path

import numpy as np

from resize_app import tracer
from resize_app.src.app.schema import Trackpoint


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
