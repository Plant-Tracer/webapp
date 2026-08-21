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
- DynamoDB/S3 maintenance CLI: `poetry run dbutil`
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

## AWS Stack Quickstart

These commands assume that AWS authentication and `AWS_REGION` are already set,
the branch is clean and pushed, and the deployment's pre-existing S3 bucket and
other guided parameters are available. Replace the angle-bracketed values.

Create a new stack with a new, stack-specific DynamoDB database:

```bash
DYNAMODB_TABLE_PREFIX=<stack>- poetry run dbutil createdb && STACK=<stack> make sam-build sam-deploy-guided
```

The first deployment must use `sam-deploy-guided`. It collects required values
such as the pre-existing S3 bucket, domain settings, and mail behavior, then
writes them to the ignored per-stack file `samconfigs/<stack>.toml`. Subsequent
`sam-deploy` runs are non-interactive and reuse that file; they refuse to deploy
a stack whose saved configuration does not yet exist.
Both deployment targets configure and verify CORS and EventBridge delivery on
the selected pre-existing S3 bucket before running their status and workflow
checks.

Create a new stack using an existing DynamoDB database:

```bash
DYNAMODB_TABLE_PREFIX=<existing-prefix>- STACK=<stack> make sam-build sam-deploy-guided
```

Create a test course and make `simsong@acm.org` its administrator (the stack
and its DynamoDB tables must already exist):

```bash
AWS_REGION=us-east-1 STACK_NAME=dev COURSE_CREATE_FLAGS="--course_id dev-test --course_name 'Dev Test Course' --admin_email simsong@acm.org --admin_name 'Simson Garfinkel'" make sam-course-create
```

`sam-course-create` reads the stack's DynamoDB prefix and application URL,
creates or verifies the course and administrator, and sends the administrator a
login email unless the stack has `MailerDryRun=true`.

Delete and replace a stack under the same name, retaining its DynamoDB database
and saved SAM configuration:

```bash
STACK=<stack> make sam-delete && STACK=<stack> make sam-build sam-deploy
```

Shut down and delete a stack:

```bash
STACK=<stack> make sam-delete
```

`sam-delete` waits 10 seconds before proceeding. Deleting a stack does not
delete its external DynamoDB tables or the pre-existing S3 movie bucket. Table
names are defined in `etc/dynamodb_tables.json`; the application selects the
set whose prefix matches the stack's `DynamoDBTablePrefix` parameter.

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
