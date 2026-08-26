"""Cross-platform static HTTP handler for browser module tests."""

from http.server import SimpleHTTPRequestHandler


class JavaScriptModuleHandler(SimpleHTTPRequestHandler):
    """Serve JavaScript modules with a MIME type browsers will execute."""

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".mjs": "text/javascript",
    }
