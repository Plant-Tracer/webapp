# Plant Tracer Webapp - Design Document for Cursor and Copilot

This document provides an overview of the Plant Tracer webapp codebase to help AI coding assistants (Cursor, Copilot) understand the system architecture, design decisions, and coding conventions.

## System Overview

The Plant Tracer webapp is a Flask-based web application for uploading, managing, and analyzing plant growth videos. The application runs at `https://app.planttracer.com/` and provides both a web interface and REST API.

### Architecture Components

1. **Backend**: Python Flask application (`src/app/flask_app.py`)
   - REST API endpoints (`src/app/flask_api.py`)
   - Database abstraction layer (`src/app/odb.py`)
   - Authentication system (`src/app/auth.py`, `src/app/apikey.py`)
   - S3 integration for file storage (`src/app/s3_presigned.py`)

2. **Frontend**: JavaScript client-side code (`src/app/static/`)
   - Canvas-based movie player and annotation tools
   - Custom lightweight DOM utility (`utils.js`) providing jQuery-like API (jQuery has been completely eliminated)
   - ES6 modules for modern JavaScript

3. **Data Storage**:
   - **Amazon S3**: Movies, frames, ZIP files
   - **Amazon DynamoDB**: Course data, user accounts, movie metadata, annotations

4. **Future Lambda Functions** (not yet working):
   - `lambda-resize/`: S3 watcher for resizing uploaded images
   - `lambda-camera/`: Camera interface for mobile devices

## Testing Strategy

### Local Services (No Mocking)

**Critical Design Decision**: We do NOT mock AWS services. Instead, we use real local implementations:

- **DynamoDBLocal**: Amazon's official DynamoDB emulator (`bin/DynamoDBLocal.jar`)
  - Runs on `http://localhost:8010/`
  - Used in both local development and GitHub Actions CI/CD
  - Started via `bin/local_dynamodb_control.bash`

- **Minio**: Full-featured S3-compatible object storage (`bin/minio`)
  - Runs on `http://localhost:9100/`
  - Used in both local development and GitHub Actions CI/CD
  - Started via `bin/local_minio_control.bash`

This approach ensures tests run against real service implementations, catching integration issues that mocks would miss.

### Test Types

1. **Python Unit Tests** (`tests/*_test.py`):
   - Use pytest with fixtures from `tests/conftest.py`
   - Fixtures automatically set up local DynamoDB and Minio
   - No environment variables needed - fixtures handle configuration

2. **JavaScript Unit Tests** (`jstests/*.test.js`):
   - Jest-based tests running in jsdom environment
   - Coverage collected via `npm run coverage`
   - Outputs to `coverage/coverage-final.json`

3. **Browser Integration Tests** (`tests/*_browser_test.py`, `tests/canvas_movie_controller_test.py`):
   - Selenium WebDriver with Chromium
   - Flask server runs in background thread
   - Tests JavaScript execution in real browser
   - **Issue**: JavaScript coverage from these tests is NOT currently collected

### Coverage Collection

- **Python**: Collected via `pytest --cov` → `coverage.xml`
- **JavaScript (Jest)**: Collected via `npm run coverage` → `coverage/coverage-final.json`
- **JavaScript (Chromium)**: **NOT CURRENTLY COLLECTED** - this is a known gap

Both coverage files are uploaded to codecov.io in CI/CD.

## Code Style and Conventions

### Type Annotations

**Preference**: Use type annotations when possible. The project uses:
- Python 3.13+ type hints
- Pyright for type checking (configured in `pyproject.toml`)
- Type checking mode: `basic` (not strict)

### Code Organization

- **Source code**: `src/app/`
- **Tests**: `tests/`
- **JavaScript tests**: `jstests/`
- **Static assets**: `src/app/static/`
- **Templates**: `src/app/templates/`

### Key Files

- `Makefile`: Main build and test orchestration
- `pyproject.toml`: Python dependencies and tool configuration
- `package.json`: JavaScript dependencies and Jest configuration
- `tests/conftest.py`: Shared pytest fixtures
- `.github/workflows/ci-cd.yml`: GitHub Actions CI/CD pipeline

## Development Workflow

### Local Setup

1. Install dependencies: `make install-ubuntu` or `make install-macos`
2. Start local services: `make start_local_dynamodb` and `make start_local_minio`
3. Create demo data: `make make-local-demo`
4. Run server: `make run-local-demo-debug`

### Running Tests

- **All tests**: `make pytest`
- **With coverage**: `make coverage` (runs both Python and JavaScript coverage)
- **JavaScript only**: `make jscoverage`
- **Linting**: `make lint`

## Future Lambda Functions

Two Lambda functions are planned but not yet working:

1. **lambda-resize**: 
   - Watches S3 for uploaded movies
   - Resizes images automatically
   - Located in `lambda-resize/`
   - Uses AWS SAM for deployment

2. **lambda-camera**:
   - Mobile camera interface
   - Self-contained Lambda at separate domain
   - Located in `lambda-camera/`
   - Uses AWS SAM for deployment

These are separate from the main Flask app and have their own deployment pipelines.

## Important Notes for AI Assistants

1. **Do NOT mock DynamoDB or S3** - use the local services
2. **Type annotations are preferred** but not strictly required
3. **JavaScript coverage from Chromium tests is missing** - this needs to be fixed
4. **Tests should be self-contained** - fixtures handle all setup
5. **jQuery has been completely eliminated** - replaced with custom lightweight `$` utility in `utils.js`
6. **Local services run on fixed ports** - see `Makefile` for endpoints

## Environment Variables

Key environment variables (see `docs/EnvironmentVariables.rst` for full list):
- `PLANTTRACER_S3_BUCKET`: S3 bucket name
- `DYNAMODB_TABLE_PREFIX`: Table prefix (e.g., "demo-")
- `DEMO_COURSE_ID`: Course ID for demo mode
- `AWS_ENDPOINT_URL_S3`: Override for local Minio
- `AWS_ENDPOINT_URL_DYNAMODB`: Override for local DynamoDB

Fixtures in `tests/conftest.py` automatically configure these for tests.

