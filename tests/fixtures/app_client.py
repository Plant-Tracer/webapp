import pytest
import deploy.bottle_app as bottle_app

@pytest.fixture
def client():
    app = bottle_app.app
    app.config['TESTING'] = True
    with app.app_context():
        with app.test_client() as client:
            client.environ_base['REMOTE_ADDR'] = '10.0.0.1'
            yield client
