from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_upload_preview_uses_trace_movie_link_name():
    upload_template = read("src/app/templates/upload.html")
    upload_js = read("src/app/static/planttracer.js")

    assert "id='trace_movie_link'" in upload_template
    assert "Trace the uploaded movie" in upload_template
    assert "trace_movie_link" in upload_js
    assert "track_movie_link" not in upload_template
    assert "track_movie_link" not in upload_js
    assert "Track the uploaded movie" not in upload_template


def test_removed_tracker_test_references_do_not_reappear():
    assert "tracker_test.py" not in read("tests/Makefile")
    assert "tracker_test.py" not in read("tests/README.md")
