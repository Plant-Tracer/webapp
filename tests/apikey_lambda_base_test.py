from flask import Flask

from app import apikey
from app.constants import C


def test_get_lambda_api_base_prefers_explicit_override(monkeypatch):
    monkeypatch.setenv(C.PLANTTRACER_LAMBDA_API_BASE, "http://127.0.0.1:9001")
    monkeypatch.setenv("HOSTNAME", "ignored-host")
    monkeypatch.setenv("DOMAIN", "ignored.example.com")

    assert apikey.get_lambda_api_base() == "http://127.0.0.1:9001/"


def test_get_lambda_api_base_falls_back_to_hostname_and_domain(monkeypatch):
    monkeypatch.delenv(C.PLANTTRACER_LAMBDA_API_BASE, raising=False)
    monkeypatch.setenv("HOSTNAME", "stack-name")
    monkeypatch.setenv("DOMAIN", "planttracer.com")

    assert apikey.get_lambda_api_base() == "https://stack-name-lambda.planttracer.com/"


def test_in_demo_mode_enabled_by_demo_mode_env(monkeypatch):
    monkeypatch.setenv(C.DEMO_MODE, "1")
    monkeypatch.delenv(C.DEMO_COURSE_ID, raising=False)
    app = Flask(__name__)

    with app.test_request_context("/", base_url="https://stack-name.planttracer.com"):
        assert apikey.in_demo_mode() is True


def test_in_demo_mode_enabled_by_demo_hostname(monkeypatch):
    monkeypatch.delenv(C.DEMO_MODE, raising=False)
    monkeypatch.delenv(C.DEMO_COURSE_ID, raising=False)
    app = Flask(__name__)

    with app.test_request_context("/", base_url="https://stack-name-demo.planttracer.com"):
        assert apikey.in_demo_mode() is True


def test_demo_course_id_alone_does_not_enable_demo_mode(monkeypatch):
    monkeypatch.delenv(C.DEMO_MODE, raising=False)
    monkeypatch.setenv(C.DEMO_COURSE_ID, "demo-course")
    app = Flask(__name__)

    with app.test_request_context("/", base_url="https://stack-name.planttracer.com"):
        assert apikey.in_demo_mode() is False
