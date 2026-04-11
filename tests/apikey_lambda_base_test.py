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
