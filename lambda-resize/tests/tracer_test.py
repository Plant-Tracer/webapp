import numpy as np

from resize_app import tracer
from resize_app.src.app.schema import Trackpoint


def test_preserve_missing_ruler_trackpoints_copies_only_missing_rulers():
    previous_trackpoints = [
        Trackpoint(x=1, y=2, label="Apex", frame_number=4),
        Trackpoint(x=10, y=20, label="Ruler 0mm", frame_number=4),
        Trackpoint(x=30, y=40, label="Ruler10mm", frame_number=4),
    ]
    output_trackpoints = [
        Trackpoint(x=2, y=3, label="Apex", frame_number=5),
        Trackpoint(x=31, y=41, label="Ruler10mm", frame_number=5),
    ]

    result = tracer.preserve_missing_ruler_trackpoints(
        previous_trackpoints=previous_trackpoints,
        output_trackpoints=output_trackpoints,
        frame_number=5,
    )

    assert result == [
        Trackpoint(x=2, y=3, label="Apex", frame_number=5),
        Trackpoint(x=31, y=41, label="Ruler10mm", frame_number=5),
        Trackpoint(x=10, y=20, label="Ruler 0mm", frame_number=5),
    ]


def test_cv2_trace_frame_copies_ruler_marker_when_cv2_drops_it(monkeypatch):
    previous_trackpoints = [
        Trackpoint(x=1, y=2, label="Apex", frame_number=4),
        Trackpoint(x=10, y=20, label="Ruler 0mm", frame_number=4),
        Trackpoint(x=30, y=40, label="Ruler 10mm", frame_number=4),
    ]

    def fake_optical_flow(_gray_frame_prev, _gray_frame, _input_points, _unused, **_kwargs):
        points = np.array([
            [2, 3],
            [11, 21],
            [31, 41],
        ], dtype=np.float32)
        status = np.array([[1], [0], [1]], dtype=np.uint8)
        return points, status, None

    monkeypatch.setattr(tracer.cv2, "calcOpticalFlowPyrLK", fake_optical_flow)

    result = tracer.cv2_trace_frame(
        gray_frame_prev=np.zeros((8, 8), dtype=np.uint8),
        gray_frame=np.zeros((8, 8), dtype=np.uint8),
        trackpoints=previous_trackpoints,
        frame_number=5,
    )

    assert result == [
        Trackpoint(x=2, y=3, label="Apex", frame_number=5),
        Trackpoint(x=31, y=41, label="Ruler 10mm", frame_number=5),
        Trackpoint(x=10, y=20, label="Ruler 0mm", frame_number=5),
    ]
