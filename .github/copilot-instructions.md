# Copilot Instructions for Plant Tracer

## Project Overview

Plant Tracer is a Flask-based web application that lets students upload, track, and share time-lapse videos of plant motion. It runs at https://app.planttracer.com/ (and dev subdomains). The repo contains a Python/Flask backend and a JavaScript frontend (custom DOM utilities; jQuery has been removed).

## Technology Stack

- **Python**: 3.12+ (required; see `pyproject.toml`)
- **Framework**: Flask (web), gunicorn (production), or AWS Lambda
- **Storage**: Amazon S3 (movies, frames, zip files), Amazon DynamoDB (courses, users, annotations)
- **Package manager**: Poetry
- **Frontend**: JavaScript in `src/app/static/`; variables and templates in `src/app/templates/`
- **Key dependencies**: boto3, flask, jinja2, opencv-python-headless, requests; see `pyproject.toml` for full list

## Project Structure

```
webapp/
├── src/
│   ├── app/                    # Flask app and application code
│   │   ├── flask_app.py        # App factory and route registration
│   │   ├── flask_api.py        # API Blueprint (api_bp): register, resend-link, upload, list, etc.
│   │   ├── odb.py              # DynamoDB access (courses, users, api_keys, movies)
│   │   ├── odbmaint.py         # DB maintenance / creation
│   │   ├── odb_movie_data.py   # Movie/frame data in DB
│   │   ├── schema.py           # DynamoDB table definitions
│   │   ├── mailer.py           # Email via SMTP or AWS SES
│   │   ├── s3_presigned.py     # S3 signed URLs and presigned POST
│   │   ├── tracker.py          # Plant motion tracking
│   │   ├── templates/         # Jinja2 HTML + MIME email templates
│   │   └── static/            # CSS, JavaScript, images
│   ├── dbutil.py               # CLI: createdb, makelink, course creation, etc.
│   ├── demo.py                 # Demo mode helpers
│   └── lambda_handler.py       # Lambda entry (if used)
├── lambda-resize/              # Optional Lambda for image resizing (separate Poetry project)
├── tests/
│   ├── conftest.py            # Pytest fixtures (local_ddb, local_s3, new_course, api_key, new_movie, client, live_server)
│   ├── fixtures/              # local_aws.py, app_client.py, localmail_config.py
│   ├── test_*.py              # Test modules (function-style tests only)
│   └── jstests/               # JavaScript tests (e.g. npm test)
├── etc/                        # Config and ops (bootstrap.sh, service files, credentials stubs)
├── docs/                       # RST and MD docs (EnvironmentVariables.rst, DeveloperSetup*.md)
├── pyproject.toml             # Poetry config, pylint, pytest, pyright
└── Makefile                    # install-ubuntu, install-macos, lint, pytest, run-local-*, etc.
```

## Development Workflow

### Setup

```bash
# System deps (Ubuntu)
make install-ubuntu

# System deps (macOS)
make install-macos

# Creates .venv (Poetry in-project), installs deps, and on Linux sets up DynamoDB Local + Minio deps
# Then for local backend: install Minio and DynamoDB Local (see Makefile targets below)
```

### Running Locally

Local runs use Minio (S3) and DynamoDB Local unless `AWS_REGION` is set to a real region.

```bash
# One-time: start Minio + DynamoDB Local, create local bucket
python3 bin/local_services.py minio start
python3 bin/local_services.py dynamodb start
make make-local-bucket

# Create demo course and DB tables
make make-local-demo

# Run Flask dev server (with a pre-created magic link for demo@planttracer.com)
make run-local-debug
# Or demo mode only (DEMO_COURSE_ID=demo-course):
make run-local-demo-debug
```

Connect at http://localhost:8080 (or `LOCAL_HTTP_PORT`). See README.md and docs/DeveloperSetup_Mac.md for full flow.

### Linting and Type Checking

```bash
# Lint Python and JavaScript/HTML
make lint          # runs pylint + eslint (in src/app/static and src/app/templates)
make pylint        # Python only (threshold 10.0)
make eslint        # JS/HTML in app
make mypy          # Type checking (optional)
make black         # Format Python (line-length 127)
make black-check
make isort / isort-check
make flake         # flake8
```

### Testing

```bash
# Full check (lint + pytest + JS coverage)
make check

# Python tests only (requires .venv; use AWS_REGION=local for Minio/DynamoDB Local)
make pytest
make pytest-coverage   # coverage in htmlcov/

# JS tests
make jscoverage
```

Tests are pytest function-style (`def test_*()`); no test classes. Fixtures from `tests/conftest.py` and `tests/fixtures/` (e.g. `local_ddb`, `local_s3`, `new_course`, `api_key`, `new_movie`, `client`, `live_server`). See `.github/agents/FIXTURES_REFERENCE.md` for auth and `api_key` usage in browser tests.

### Database

- **DynamoDB**: Tables are prefixed with `DYNAMODB_TABLE_PREFIX` (e.g. `demo-`). Schema and creation in `src/app/schema.py` and `src/app/odbmaint.py`. CLI: `src/dbutil.py` (e.g. `createdb`, `makelink`).
- **S3**: Bucket in `PLANTTRACER_S3_BUCKET`; presigned URLs and uploads via `src/app/s3_presigned.py`.
- No SQL schema file; DynamoDB is schema-in-code.

## Coding Standards

### Python

- **Version**: 3.12+
- **Linter**: Pylint (fail-under 10.0). Config in `pyproject.toml` (many docstring/length checks disabled).
- **Formatting**: Black (line-length 127), isort (profile black).
- **Type hints**: Encouraged; mypy/pyright in basic mode.
- **Imports**: Standard library, then third-party, then local.
- **Logging**: Use `logger.info("msg %s", var)` style, not f-strings in logging (performance and level filtering).

### Tests

- Function-style only: `def test_*()`; no test classes or complex inheritance.
- Use fixtures from `conftest.py` and `fixtures/`; prefer local or in-file fixtures when appropriate.
- For browser/Selenium tests, always pass `api_key` (e.g. in URL or cookie). See FIXTURES_REFERENCE.md.

### Conventions

- Keep route handlers thin; put business logic in `odb.py`, `mailer.py`, `s3_presigned.py`, etc.
- DB and table logic: `src/app/odb.py`, `src/app/odbmaint.py`, `src/app/schema.py`.
- Environment variables: see `docs/EnvironmentVariables.rst`. Required: `PLANTTRACER_S3_BUCKET`, `DYNAMODB_TABLE_PREFIX`. For local: `AWS_REGION=local`, `AWS_ENDPOINT_URL_S3`, `AWS_ENDPOINT_URL_DYNAMODB` (Minio/DynamoDB Local). Optional: `DEMO_COURSE_ID`, `PLANTTRACER_CREDENTIALS` (email), etc.

## Common Tasks

### Adding a New API or Web Route

1. Add handler in `src/app/flask_api.py` (API Blueprint) or in the app module used by `src/app/flask_app.py`.
2. Add Jinja2 template under `src/app/templates/` if needed.
3. Add tests in `tests/` (e.g. `tests/endpoint_test.py` or a new `test_*.py`).
4. Update docs if adding a user-facing or deployment-relevant behavior.

### Adding Database Functionality

1. Add or extend functions in `src/app/odb.py` or `src/app/odb_movie_data.py`; update `src/app/schema.py` if adding tables or attributes.
2. Use `src/app/odbmaint.py` for one-off creation/migration logic if needed.
3. Add tests in `tests/` (e.g. `tests/odb_test.py`, `tests/db_object_test.py`).

### Email

- Templates: `src/app/templates/email_*.html` (MIME multipart with Jinja2).
- Sending: `src/app/mailer.py` (SMTP if configured, else AWS SES). No SQL; config via env and credentials file.

### Frontend (JavaScript)

- Main client code in `src/app/static/`; some variables come from pages rendered from `src/app/templates/`.
- Lint: `make eslint` (run from repo root; Makefile drives eslint in static and templates).
- Tests: `make jscoverage` / `npm test` with `NODE_PATH=src/app/static`.

## CI/CD

- **Workflows**: `.github/workflows/ci-cd.yml` (lint, pytest, JS tests on push/PR; matrix: macOS + Ubuntu).
- **Badges**: README references CI (e.g. continuous-integration-pip), codecov, Coverity.
- Local CI-like run: `make check` (lint + `AWS_REGION=local make pytest` + jscoverage).

## Configuration and Secrets

- **Env**: Required and optional variables documented in `docs/EnvironmentVariables.rst` and README.
- **Credentials**: Email (SMTP/IMAP) via `PLANTTRACER_CREDENTIALS` (ini file) or `SMTPCONFIG_ARN` / `SMTPCONFIG_JSON`.
- **AWS**: Use `AWS_REGION`, `AWS_ENDPOINT_URL_*` for local (Minio, DynamoDB Local) or real AWS.

## Resources

- **Poetry / tooling**: `pyproject.toml` (pylint, pytest, pyright, pytest options).
- **Make targets**: `Makefile` (no `make help`; read the file for targets like `install-macos`, `lint`, `pytest`, `run-local-debug`, `make-local-bucket`, `start_local_minio`, `start_local_dynamodb`).
- **Cursor rules**: `.cursor/rules/*.mdc` (e.g. Corridor MCP usage; no source changes unless requested).
- **Fixtures and auth**: `.github/agents/FIXTURES_REFERENCE.md`.
