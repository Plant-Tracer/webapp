"""Fixtures for browser-only checks that do not require the Flask test stack."""

pytest_plugins = ("browser_tests.chrome",)
