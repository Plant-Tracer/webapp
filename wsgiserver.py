"""
https://www.electricmonk.nl/log/2016/02/15/multithreaded-dev-web-server-for-the-python-bottle-web-framework/
Simple multithreaded WSGI HTTP server.
"""

from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn

# pylint: disable=missing-class-docstring
class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True

# pylint: disable=too-few-public-methods
class Server:
    def __init__(self, wsgi_app, listen='127.0.0.1', port=8080):
        self.wsgi_app = wsgi_app
        self.listen = listen
        self.port = port
        self.server = make_server(self.listen, self.port, self.wsgi_app,
                                  ThreadingWSGIServer)

    def serve_forever(self):
        print(f"Connect to server on http://{self.listen}:{self.port}/")
        self.server.serve_forever()
