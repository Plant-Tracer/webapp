"""HTTP transfer tests for the standard-library movie-data client."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading

from app import odb_movie_data


def test_http_read_and_streaming_copy_use_real_local_server(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"plant-tracer" * 100_000)
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/{source.name}"
        assert odb_movie_data.read_object(url) == source.read_bytes()
        destination = tmp_path / "destination.bin"
        odb_movie_data.copy_object_to_path(url, str(destination))
        assert destination.read_bytes() == source.read_bytes()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
