from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_upload_preview_links_to_analyze():
    upload_template = read("src/app/templates/upload.html")
    upload_js = read("src/app/static/planttracer.js")

    assert "id='process_movie_link'><strong>Open Analyze</strong>" in upload_template
    assert "$('#process_movie_link').attr('href', `/analyze?movie_id=${movie_id}`)" in upload_js


def test_removed_tracker_test_references_do_not_reappear():
    assert "tracker_test.py" not in read("tests/Makefile")
    assert "tracker_test.py" not in read("tests/README.md")
