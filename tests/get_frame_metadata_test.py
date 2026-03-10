import copy

from app import tracker
from app.odb import API_KEY, MOVIE_ID


def test_get_frame_does_not_extract_full_metadata_for_each_request(client, new_movie, monkeypatch):
    """
    Regression test for large-movie get-frame timeouts.

    The /api/get-frame endpoint should not call tracker.extract_movie_metadata just to
    return a single frame; metadata extraction is expensive for large movies and is
    handled elsewhere (e.g. get-movie-metadata). This test will fail on the old
    implementation because api_get_frame_jpeg unconditionally calls
    tracker.extract_movie_metadata.
    """
    cfg = copy.copy(new_movie)
    movie_id = cfg[MOVIE_ID]
    api_key = cfg[API_KEY]

    called = {"count": 0}

    def fake_extract_movie_metadata(*, movie_data):
        # If this is ever called during /api/get-frame, we fail the test.
        called["count"] += 1
        raise RuntimeError("extract_movie_metadata should not be called from api_get_frame")

    monkeypatch.setattr(tracker, "extract_movie_metadata", fake_extract_movie_metadata)

    resp = client.post(
        "/api/get-frame",
        data={"api_key": api_key, "movie_id": str(movie_id), "frame_number": "0"},
    )

    # Desired behaviour: we successfully redirect to the JPEG object without
    # recomputing full movie metadata.
    assert resp.status_code == 302
    assert resp.location is not None
    assert called["count"] == 0
