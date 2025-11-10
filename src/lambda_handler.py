"""
Create a lambda_handler for a flask program.
"""

import logging
from apig_wsgi import make_lambda_handler
from app.flask_app import app

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)
lambda_app = make_lambda_handler(app)
