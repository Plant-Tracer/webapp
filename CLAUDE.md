# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Plant Tracer is a Flask-based web application for uploading, managing, and annotating plant growth time-lapse videos at https://app.planttracer.com/. It has a Python/Flask backend, a JavaScript frontend (jQuery loaded globally, with ES modules importing `$` from `utils.js`), DynamoDB for structured data, and S3 for video/frame storage.

## Common Commands

```bash
# Linting
make lint          # Python (pylint, threshold 10.0) + JS/HTML (eslint)
make pylint        # Python only
make eslint        # JS/HTML only
make black         # Format Python (line-length 127)
make mypy          # Type checking (optional)

# Testing
make check         # Full CI: lint + pytest + jscoverage
make pytest        # Python tests (requires local DynamoDB + Minio running)
make pytest-coverage  # Python tests with HTML coverage in htmlcov/
make jscoverage    # JavaScript Jest tests with coverage
npm test           # JS tests directly
npm run test-debug # JS tests with verbose output

# Run a single Python test module
AWS_REGION=local PYTHONPATH="lambda-resize/src:src" poetry run pytest tests/endpoint_test.py -v

# Local development
python3 bin/local_services.py minio start       # Start Minio (S3 emulator, ports 9000/9001)
python3 bin/local_services.py dynamodb start    # Start DynamoDB Local (port 8000)
make make-local-bucket                   # Create local S3 bucket
make make-local-demo                     # Create demo course and DB tables
make run-local-debug                     # Flask dev server at localhost:8080
```

## Architecture

### Backend (`src/app/`)
- `flask_app.py` — app factory and route registration
- `flask_api.py` — API Blueprint with REST endpoints (register, upload, list, etc.)
- `odb.py` — DynamoDB abstraction layer (courses, users, api_keys, movies)
- `odb_movie_data.py` — movie/frame data in DB
- `schema.py` — DynamoDB table definitions
- `odbmaint.py` — DB creation/maintenance
- `auth.py`, `apikey.py` — authentication
- `s3_presigned.py` — S3 presigned URLs and uploads
- `mailer.py` — email via SMTP or AWS SES
- `tracker.py` — plant motion tracking (VM only; Lambda uses vendored copy)

Route handlers should be thin; put business logic in `odb.py`, `mailer.py`, `s3_presigned.py`, etc.

### Frontend (`src/app/static/`, `src/app/templates/`)
`$` is jQuery. Browser pages load jQuery globally, and ES modules import `$` from `utils.js`, which re-exports the global jQuery instance.

### Data Storage
- **S3**: movies, frames, ZIP files. The bucket is always **pre-existing** and **outlives the CloudFormation stack** as the long-term archive. Because the bucket outlives DynamoDB, research/attribution metadata must also be written **into the MP4 file** (see `src/app/mp4_metadata_lib.py`, `docs/MOVIE_METADATA.rst`).
- **DynamoDB**: tables prefixed by `DYNAMODB_TABLE_PREFIX` (e.g. `demo-`). Schema in `src/app/schema.py`; creation in `src/app/odbmaint.py`. CLI: `src/dbutil.py` (`--createdb`, `--makelink`, etc.).
- Lambda is invoked via its HTTP API, **not** via S3 bucket notifications.

### Lambda (`lambda-resize/`)
A separate Poetry project. App code from the main package is vendored into `resize_app/src/app/` via `make -C lambda-resize vend-app` before linting/testing. Imports in Lambda code use `from .src.app import odb` style — do not change these to import the top-level `app` package.

## Testing Strategy

Tests run against **real local services** (DynamoDB Local + Minio), not mocks. Fixtures in `tests/conftest.py` and `tests/fixtures/` handle setup automatically.

- Use `make pytest` / `make check` rather than running `pytest` directly — the Makefile sets the correct environment.
- If running `pytest` directly, always set `AWS_REGION=local` and `PYTHONPATH="lambda-resize/src:src"`.
- When AWS credential errors appear in tests, **do not change code** — first verify the environment is set correctly.
- Tests must **fail** when prerequisites are missing. Do not make tests skip or pass silently — that is the project owner's decision.
- Write function-style tests only (`def test_*()`); no test classes.

## Coding Standards

### Python
- Python 3.12+; Pylint must pass at threshold 10.0 before committing (`poetry run pylint src/app/...`).
- Black (line-length 127), isort (profile black).
- All imports at the **top level** of the file — never inside functions (except `if __name__ == "__main__":` blocks). Never add `# pylint: disable=import-outside-toplevel`.
- Prefix intentionally unused parameters with `_` (e.g. `_event`); do not use `# pylint: disable=unused-argument`.
- Logging: `logger.info("msg %s", var)` style, not f-strings.
- Prefer minimal, focused diffs. Avoid duplicating existing logic or large-scale rewrites when making a targeted fix.
- `pyproject.toml` uses PEP 621 `[project]` table — do not use deprecated `[tool.poetry]` keys for name/version/description/authors/scripts.

### JavaScript
- `src/app/static/utils.js` is a shim that re-exports the global jQuery instance for ES modules.
- `make eslint` lints `src/app/static/` and `src/app/templates/`.
- Jest tests live in `jstests/`; run with `NODE_PATH=src/app/static`.

## Key Environment Variables

See `docs/EnvironmentVariables.rst` for the full list.

| Variable | Purpose |
|---|---|
| `AWS_REGION=local` | Use Minio/DynamoDB Local instead of real AWS |
| `PLANTTRACER_S3_BUCKET` | S3 bucket name (required) |
| `DYNAMODB_TABLE_PREFIX` | Table prefix, e.g. `demo-` (required) |
| `AWS_ENDPOINT_URL_S3` | Override S3 endpoint (Minio in dev) |
| `AWS_ENDPOINT_URL_DYNAMODB` | Override DynamoDB endpoint (local in dev) |
| `DEMO_COURSE_ID` | Enable demo mode |
| `PLANTTRACER_CREDENTIALS` | Path to SMTP/IMAP credentials ini file |

## Adding Routes and DB Functionality

- New API/web routes: add to `flask_api.py` (API Blueprint) or via `flask_app.py`; add Jinja2 templates under `src/app/templates/`; add tests in `tests/`.
- New DB functionality: extend `src/app/odb.py` or `odb_movie_data.py`; update `schema.py` for new tables/attributes; add tests in `tests/` (e.g. `odb_test.py`, `db_object_test.py`).
- Email: templates in `src/app/templates/email_*.html`; sending in `mailer.py`.

## CI/CD

`.github/workflows/ci-cd.yml` runs lint, pytest, and JS tests on push/PR to main/dev, on both macOS and Ubuntu with Python 3.12. Local equivalent: `make check`.
