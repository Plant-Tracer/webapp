import pytest

from app import flask_app

@pytest.fixture(scope="session")
def client():
    """Redirects disallowed by default."""
    app = flask_app.app
    app.config['TESTING'] = True
    with app.app_context():
        with app.test_client() as client:
            client.environ_base['REMOTE_ADDR'] = '10.0.0.1'
            yield client
