# Coding Standards

This document is the repository-wide coding standard for Plant Tracer.

## Core Rules

- Keep code compact, correct, and current.
- Update relevant documentation when behavior, workflows, routes, schemas, or environment variables change.
- Use the Makefile as the entry point for local runs, tests, linting, packaging, and deployment.
- Keep route handlers thin. Put business logic in `odb.py`, `odb_movie_data.py`, `mailer.py`, `s3_presigned.py`, `config_check.py`, or a focused helper module.
- Avoid compatibility wrappers and duplicate source modules unless they are required for a deployed interface.

## Python

- Target Python 3.12 as declared in `pyproject.toml`.
- Keep imports at the top of each file except in `if __name__ == "__main__":` blocks.
- Use Pydantic models for internal structures. When external APIs require dicts, keep keys in named symbols rather than repeating string literals.
- Use `logger.info("message %s", value)` style logging, not f-strings.
- Prefix intentionally unused parameters with `_`.
- Keep diffs focused. Do not refactor unrelated code while fixing a narrow issue.

## JavaScript

- Browser pages load jQuery globally.
- ES modules import `$` from `src/app/static/utils.js`, which re-exports the global jQuery instance.
- Keep browser globals documented in `src/app/templates/base.html` and the relevant developer docs.
- Prefer one shared helper for repeated API calls and error handling.

## Storage And Services

- DynamoDB tests use DynamoDB Local.
- S3 tests use MinIO.
- Do not use mocks for DynamoDB or S3 when local real-service tests are practical.
- The S3 bucket is pre-existing and outlives the CloudFormation stack.
- Lambda is invoked through its HTTP API and SQS/local queue path, not S3 bucket notifications.

## Testing

- Tests must check real logic or behavior.
- Do not add pro-forma tests that only inflate coverage.
- Avoid mocking unless a real local-service or browser-path test is impractical.
- Write function-style Python tests (`def test_*()`), not test classes.
- Use Make targets: `make pytest`, `make jscoverage`, `make lint`, and `make check`.

## Documentation

- Keep `docs/Development/FlaskAPI.md` aligned with `src/app/flask_api.py`.
- Keep `docs/Development/ClientLambdaAPI.md` aligned with `lambda-resize/src/resize_app/main.py`.
- Keep `docs/Development/EnvironmentVariables.rst` aligned with `src/app/constants.py`, `src/app/apikey.py`, `src/app/mailer.py`, and the Makefile.
- After editing docs, verify with:

```bash
poetry run sphinx-build -W --keep-going -b html docs docs/_build/html
```
