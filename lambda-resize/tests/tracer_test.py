import numpy as np

from resize_app import tracer
from resize_app.src.app.schema import Trackpoint


def test_preserve_missing_undeletable_trackpoints_copies_only_missing_undeletable():
    previous_trackpoints = [
        Trackpoint(x=1, y=2, label="Apex", frame_number=4),
        Trackpoint(x=10, y=20, label="Ruler 0mm", frame_number=4, color="red", undeletable=True),
        Trackpoint(x=30, y=40, label="Ruler10mm", frame_number=4),
    ]
    output_trackpoints = [
        Trackpoint(x=2, y=3, label="Apex", frame_number=5),
        Trackpoint(x=31, y=41, label="Ruler10mm", frame_number=5),
    ]

    result = tracer.preserve_missing_undeletable_trackpoints(
        previous_trackpoints=previous_trackpoints,
        output_trackpoints=output_trackpoints,
        frame_number=5,
    )

    assert result == [
        Trackpoint(x=2, y=3, label="Apex", frame_number=5),
        Trackpoint(x=31, y=41, label="Ruler10mm", frame_number=5),
        Trackpoint(x=10, y=20, label="Ruler 0mm", frame_number=5, color="red", undeletable=True),
    ]


def test_cv2_trace_frame_copies_ruler_marker_when_cv2_drops_it(monkeypatch):
    previous_trackpoints = [
        Trackpoint(x=1, y=2, label="Apex", frame_number=4, color="orange"),
        Trackpoint(x=10, y=20, label="Ruler 0mm", frame_number=4, color="red", undeletable=True),
        Trackpoint(x=30, y=40, label="Ruler 10mm", frame_number=4, color="red", undeletable=True),
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
        Trackpoint(x=2, y=3, label="Apex", frame_number=5, color="orange"),
        Trackpoint(x=31, y=41, label="Ruler 10mm", frame_number=5, color="red", undeletable=True),
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
