# Developer Setup Mac

This page is the supported macOS local workflow for Plant Tracer.

## Install Tools

Install Xcode command-line tools, Homebrew, and required packages:

```bash
xcode-select --install
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install awscli ffmpeg lsof node poetry python openjdk
brew install --cask google-chrome
```

Ensure OpenJDK is on your path if Homebrew asks you to add it:

```bash
echo 'export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"' >> ~/.zshrc
echo 'export CPPFLAGS="-I/opt/homebrew/opt/openjdk/include"' >> ~/.zshrc
source ~/.zshrc
```

## Clone And Install

```bash
git clone https://github.com/Plant-Tracer/webapp.git webapp
cd webapp
make install-macos
```

The Makefile creates `.venv` through Poetry and installs JavaScript dependencies
with `npm ci`.

## Local Services

Start all local service dependencies:

```bash
make start-local-services
make make-local-demo
```

Services:

| Service | Endpoint | Purpose |
|---------|----------|---------|
| DynamoDB Local | `http://localhost:8000/` | metadata store |
| MinIO | `http://localhost:9000/` | S3-compatible object store |
| Mailpit | `http://localhost:8025/` | local email web UI |

The Makefile sets local AWS values such as `AWS_REGION=local`,
`AWS_ENDPOINT_URL_DYNAMODB`, `AWS_ENDPOINT_URL_S3`, `PLANTTRACER_S3_BUCKET`, and
`DYNAMODB_TABLE_PREFIX`.

## Run The App

Normal local development needs Flask plus the local lambda-resize bridge:

```bash
make run-local-lambda-debug
make run-local-debug
```

On macOS, `make run-local-debug` attempts to start the local Lambda debug server
in another Terminal window if it is not already running.

Flask listens on `http://localhost:8080`. The local Lambda bridge listens on
`http://127.0.0.1:9811`.

Demo mode:

```bash
make run-local-demo-debug
```

## Validate

```bash
make lint
make pytest
make jscoverage
make check
```

## Inspect Local Data

```bash
make list-local-buckets
make dump-demo-tables
AWS_REGION=local poetry run python src/dbutil.py report
```

## Cleanup

```bash
make stop-local-services
make delete-local
make wipe-local
```

`delete-local` removes local artifacts. `wipe-local` recreates the local bucket
after removing local artifacts.
