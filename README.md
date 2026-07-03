[![CI (pip)](https://github.com/Plant-Tracer/webapp/actions/workflows/continuous-integration-pip.yml/badge.svg)](https://github.com/Plant-Tracer/webapp/actions/workflows/ci-cd.yml)
[![codecov](https://codecov.io/gh/Plant-Tracer/webapp/graph/badge.svg?token=YRMITDBBJ1)](https://codecov.io/gh/Plant-Tracer/webapp)
<a href="https://scan.coverity.com/projects/plant-tracer-webapp">
  <img alt="Coverity Scan Build Status"
       src="https://scan.coverity.com/projects/29728/badge.svg"/>
</a>

# Plant Tracer Webapp

This repository implements the Plant Tracer Flask web application and the
lambda-resize video-processing service.

Production app: <https://prod.planttracer.com/>

## Code

- Flask backend: `src/app/`
- Browser JavaScript and static assets: `src/app/static/`
- Jinja templates: `src/app/templates/`
- DynamoDB/S3 maintenance CLI: `src/dbutil.py`
- Lambda video/frame/tracking service: `lambda-resize/`
- Python tests: `tests/` and `lambda-resize/tests/`
- JavaScript tests: `jstests/`
- Documentation: `docs/`

Browser pages load jQuery globally. ES modules import `$` from
`src/app/static/utils.js`, which re-exports the global jQuery instance.

## Storage

- S3 stores original movies, traced movies, ZIP files, and frame artifacts.
- DynamoDB stores users, courses, API keys, movie metadata, frame trackpoints,
  and audit logs.
- The S3 bucket is pre-existing and outlives the CloudFormation stack.
- Research-use and attribution metadata must also be written into the MP4 file
  so archived movies remain self-describing.

Local development uses MinIO for S3 and DynamoDB Local for DynamoDB.

## Local Development

Install dependencies:

```bash
make install-macos   # macOS
# or
make install-ubuntu  # Ubuntu
```

Start local services and seed demo data:

```bash
make start-local-services
make make-local-demo
```

Run locally:

```bash
make run-local-lambda-debug
make run-local-debug
```

Flask runs at `http://localhost:8080`. The local Lambda bridge runs at
`http://127.0.0.1:9811`.

Demo mode:

```bash
make run-local-demo-debug
```

## Validation

Use Makefile targets:

```bash
make lint
make pytest
make jscoverage
make check
```

`make pytest` starts/uses local DynamoDB and MinIO through the project fixtures
and Makefile environment. Do not run raw pytest for normal validation unless you
also reproduce the Makefile environment.

## Key Environment Variables

See `docs/Development/EnvironmentVariables.rst`.

Common local values are supplied by the Makefile:

- `AWS_REGION=local`
- `AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000/`
- `AWS_ENDPOINT_URL_S3=http://localhost:9000/`
- `PLANTTRACER_S3_BUCKET=planttracer-local`
- `DYNAMODB_TABLE_PREFIX=demo-`
- `PLANTTRACER_LAMBDA_API_BASE=http://127.0.0.1:9811/`

## Documentation

Build docs after editing anything under `docs/`:

```bash
poetry run sphinx-build -W --keep-going -b html docs docs/_build/html
```

Developer entry points:

- `docs/Development/DeveloperSetup.rst`
- `docs/Development/Local Development and Github Actions.rst`
- `docs/Development/BackupRestore.rst`
- `docs/Development/FlaskAPI.md`
- `docs/Development/ClientLambdaAPI.md`
- `docs/Development/TechDebt.rst`
