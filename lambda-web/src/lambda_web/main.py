"""Lambda entry point for the Flask web application."""

from typing import Any

import apig_wsgi

from app.flask_app import app as flask_app

lambda_handler: Any = apig_wsgi.make_lambda_handler(flask_app)
