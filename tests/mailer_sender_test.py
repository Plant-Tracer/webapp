from app import mailer
from app.constants import C


def test_server_from_header_defaults(monkeypatch):
    monkeypatch.delenv(C.SERVER_EMAIL, raising=False)
    monkeypatch.delenv(C.SERVER_EMAIL_NAME, raising=False)

    assert mailer.get_server_email() == "admin@planttracer.com"
    assert mailer.get_server_email_name() == "Plant Tracer"
    assert mailer.get_server_from_header() == "Plant Tracer <admin@planttracer.com>"


def test_server_from_header_uses_configured_name_and_address(monkeypatch):
    monkeypatch.setenv(C.SERVER_EMAIL, "sender@example.com")
    monkeypatch.setenv(C.SERVER_EMAIL_NAME, "Plant Tracer Demo")

    assert mailer.get_server_from_header() == "Plant Tracer Demo <sender@example.com>"


def test_send_links_uses_named_from_header_in_dry_run(monkeypatch, capsys):
    monkeypatch.setenv("MAILER_DRY_RUN", "true")
    monkeypatch.setenv(C.SERVER_EMAIL, "sender@example.com")
    monkeypatch.setenv(C.SERVER_EMAIL_NAME, "Plant Tracer Demo")
    monkeypatch.delenv(C.SMTPCONFIG_JSON, raising=False)
    monkeypatch.delenv(C.SMTPCONFIG_ARN, raising=False)
    monkeypatch.delenv(C.PLANTTRACER_CREDENTIALS, raising=False)

    mailer.send_links(
        email="student@example.com",
        planttracer_endpoint="https://demo.planttracer.com",
        new_api_key="a123456789012345678901234567890bc",
    )

    assert "From: Plant Tracer Demo <sender@example.com>" in capsys.readouterr().err
