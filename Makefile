# Makefile for Planttracer web application.
# - Local development
# - Creates CI/CD environment in GitHub
# - Manages deployemnt to AWS Linux
# - Updated to handle virtual environment
# - Simple CRUD management of local database instance for developers
#
# Environment variables:
# PLANTTRACER_CREDENTIALS - the config.ini file that includes [smtp] and [imap] configuration the your production system
#
# AWS stack quickstart (AWS authentication and AWS_REGION must already be set):
# New stack and new DynamoDB tables:
# DYNAMODB_TABLE_PREFIX=<stack>- uv run dbutil createdb && STACK=<stack> make sam-build sam-deploy-guided
# New stack using existing DynamoDB tables:
# DYNAMODB_TABLE_PREFIX=<existing-prefix>- STACK=<stack> make sam-build sam-deploy-guided
# Create a dev test course administered by simsong@acm.org:
# AWS_REGION=us-east-1 STACK_NAME=dev COURSE_CREATE_FLAGS="--course_id dev-test --course_name 'Dev Test Course' --admin_email simsong@acm.org --admin_name 'Simson Garfinkel'" make sam-course-create
# Replace a stack while retaining its external DynamoDB tables and S3 bucket:
# STACK=<stack> make sam-delete && STACK=<stack> make sam-build sam-deploy
# Shut down and delete a stack while retaining external DynamoDB and S3 data:
# STACK=<stack> make sam-delete
#
# A stack's first deployment must use sam-deploy-guided. It collects required
# deployment parameters and saves them in the ignored per-stack file
# samconfigs/<stack>.toml. Later sam-deploy runs are non-interactive and reuse
# that file; sam-deploy refuses to proceed when the saved config does not exist.
# Every deployment configures and verifies CORS and EventBridge delivery on the
# selected pre-existing S3 bucket before running status and workflow checks.

SHELL := /bin/bash
PYLINT_THRESHOLD := 10.0
TS_FILES := $(wildcard *.ts */*.ts)
JS_FILES := $(TS_FILES:.ts=.js)
LOCAL_BUCKET:=planttracer-local
LOCAL_HTTP_PORT=8080
LOCAL_LAMBDA_PORT=9811
LOCAL_LAMBDA_BASE=http://127.0.0.1:$(LOCAL_LAMBDA_PORT)/
DYNAMODB_LOCAL_ENDPOINT=http://localhost:8000/
MINIO_ENDPOINT=http://localhost:9000/
DBUTIL=src/dbutil.py
MAILPIT_SMTP_CONFIG={"SMTP_HOST":"127.0.0.1","SMTP_PORT":"1025","SMTP_NO_TLS":"1","SMTP_USERNAME":"","SMTP_PASSWORD":""}
LOCAL_AWS_ENV=env -u AWS_PROFILE -u AWS_DEFAULT_PROFILE AWS_REGION=local AWS_DEFAULT_REGION=local AWS_EC2_METADATA_DISABLED=true AWS_ACCESS_KEY_ID=minioadmin AWS_SECRET_ACCESS_KEY=minioadmin AWS_ENDPOINT_URL_DYNAMODB=$(DYNAMODB_LOCAL_ENDPOINT) AWS_ENDPOINT_URL_S3=$(MINIO_ENDPOINT) PLANTTRACER_S3_BUCKET=$(LOCAL_BUCKET) DYNAMODB_TABLE_PREFIX=demo- SMTPCONFIG_JSON='$(MAILPIT_SMTP_CONFIG)'
LOCAL_FLASK_ENV=$(LOCAL_AWS_ENV) PLANTTRACER_LAMBDA_API_BASE=$(LOCAL_LAMBDA_BASE)
LOCAL_NONDEMO_ENV=env -u DEMO_MODE -u DEMO_COURSE_ID $(LOCAL_FLASK_ENV)
LOCAL_DEMO_ENV=DEMO_MODE=1 DEMO_COURSE_ID=demo-course $(LOCAL_FLASK_ENV)
LOCAL_ADMIN_EMAIL=plantadmin@planttracer.com
FLASK_DEBUG_RUN=uv run flask --debug --app src.app.flask_app:app run --port $(LOCAL_HTTP_PORT) --with-threads
LOCAL_LAMBDA_PROBE=uv run python -c 'import socket, sys; s=socket.socket(); s.settimeout(0.2); sys.exit(0 if s.connect_ex(("127.0.0.1", $(LOCAL_LAMBDA_PORT))) == 0 else 1)'
LOCAL_LAMBDA_WAIT_SECONDS ?= 30

# STACK is the canonical selector. STACK_NAME is accepted as an operator-facing
# alias because it is also the CloudFormation/SAM term shown during deployment.
STACK_NAME_INPUT := $(if $(filter environment command line,$(origin STACK_NAME)),$(strip $(STACK_NAME)),)
DYNAMODB_TABLE_PREFIX_INPUT := $(if $(filter environment command line,$(origin DYNAMODB_TABLE_PREFIX)),$(strip $(DYNAMODB_TABLE_PREFIX)),)
ifneq ($(STACK_NAME_INPUT),)
override STACK := $(STACK_NAME_INPUT)
else
STACK ?=
endif
SAM_CONFIG_DIR ?= samconfigs
SAM_CONFIG ?= $(if $(STACK),$(SAM_CONFIG_DIR)/$(STACK).toml,samconfig.toml)
SAM_BUILD_DIR=.aws-sam/build
SAM_CONFIG_STACK_NAME = $(shell uv run sam-config-tool --samconfig "$(SAM_CONFIG)" stack-name 2>/dev/null)
SAM_CONFIG_DYNAMODB_TABLE_PREFIX = $(shell uv run sam-config-tool --samconfig "$(SAM_CONFIG)" parameter-override --name DynamoDBTablePrefix 2>/dev/null)
EFFECTIVE_STACK_NAME = $(if $(STACK),$(STACK),$(SAM_CONFIG_STACK_NAME))
APP_VERSION := $(shell uv run python -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')

# Only show events from the last N minutes (filter-log-events returns ascending order, so without this we get oldest events).
SAM_LOGS_LIMIT ?= 1000
SAM_LOGS_MINUTES ?= 15

# all of the tests below require a virtual python environment, LambdaDBLocal and the minio s3 emulator
# See below for the rules

REQ := .venv/pyvenv.cfg
LOCAL_TEST_REQ := .venv/pyvenv.cfg bin/DynamoDBLocal.jar bin/minio bin/mailpit

# files used by lambda
VEND_FILES := src/app/odb.py \
              src/app/schema.py \
              src/app/build_metadata.py \
              src/app/constants.py \
              src/app/mp4_metadata_lib.py \
              src/app/paths.py \
              src/app/odb_movie_data.py \
              src/app/s3_presigned.py

export DEBIAN_FRONTEND=noninteractive
export LOG_LEVEL ?= INFO

# if AWS_REGION is set, we use the live system. Otherwise use minio and DynamoDBlocal
ifeq ($(AWS_REGION),)
    $(warning AWS_REGION is not set. Defaulting to local MinIO/DynamoDB configuration.)
    export AWS_REGION                ?= local
endif
ifeq ($(AWS_REGION),local)
    REQ := $(REQ) bin/DynamoDBLocal.jar bin/minio bin/mailpit
    export AWS_ACCESS_KEY_ID         := minioadmin
    export AWS_SECRET_ACCESS_KEY     := minioadmin
    export AWS_ENDPOINT_URL_DYNAMODB := $(DYNAMODB_LOCAL_ENDPOINT)
    export AWS_ENDPOINT_URL_S3       := $(MINIO_ENDPOINT)
    export PLANTTRACER_S3_BUCKET=$(LOCAL_BUCKET)
endif

export PYLINTHOME ?= $(CURDIR)/.pylint.d

ifeq ($(AWS_REGION),local)
ifeq ($(DYNAMODB_TABLE_PREFIX),)
    $(info DYNAMODB_TABLE_PREFIX not set. Defaulting to demo-)
    export DYNAMODB_TABLE_PREFIX=demo-
endif
endif

.PHONY: dist distclean

.venv/pyvenv.cfg:
	@echo install .venv for the development environment
	poetry config virtualenvs.in-project true
	poetry install

dist: pyproject.toml
	@echo building the deloy wheel
	poetry build --format=wheel
	ls -l dist/

distclean:
	@echo removing all virtual environments
	/bin/rm -rf .venv */.venv */.aws-sam
	/bin/rm -rf .*cache */.*cache
	/bin/rm -rf _build

################################################################
# Main targets used by CI/CD system and developers
.PHONY: all check coverage tags admin-list admin-create course-create demo-course-create sam-course-create s3-eventbridge-status s3-eventbridge-enable

all:
	@echo verify syntax and then restart
	make lint
	make run-local

check:
	$(MAKE) lint
	$(MAKE) start-local-services
	$(MAKE) AWS_REGION=local pytest
	$(MAKE) jscoverage

coverage:
	$(MAKE) AWS_REGION=local pytest-coverage
	$(MAKE) AWS_REGION=local jscoverage

tags:
	etags src/app/*.py tests/*.py tests/fixtures/*.py src/app/static/*.js lambda-web/src/lambda_web/*.py lambda-resize/src/resize_app/*.py

admin-list:
	uv run python $(DBUTIL) admin-list

ADMIN_CREATE_FLAGS ?=
admin-create:
	uv run python $(DBUTIL) admin-create $(ADMIN_CREATE_FLAGS)

COURSE_CREATE_FLAGS ?=
course-create:
	uv run python $(DBUTIL) create-course --send-email $(COURSE_CREATE_FLAGS)

DEMO_COURSE_CREATE_FLAGS ?=
demo-course-create:
	uv run python $(DBUTIL) create-demo-course $(DEMO_COURSE_CREATE_FLAGS)

################################################################
## Program development: static analysis tools
##

## Use this targt for static analysis of the python files used for deployment
PYLINT_OPTS:=--output-format=parseable --fail-under=$(PYLINT_THRESHOLD) --verbose
lint: $(REQ)
	$(MAKE) pylint
	$(MAKE) eslint

pylint:
	$(MAKE) vend-lambda-resize
	$(MAKE) vend-lambda-web
	uv run pylint $(PYLINT_OPTS) browser_tests lambda-web/src/lambda_web lambda-web/tests lambda-resize src tests \
		bin/deployed_workflow_test.py etc/sam_config_tool.py etc/sam_config_writer.py *.py

## Mypy static analysis
mypy:
	mypy --show-error-codes --pretty --ignore-missing-imports --strict src tests

## flake
flake:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 . --count --exit-zero --max-complexity=55 --max-line-length=127 --statistics --ignore F403,F405,E203,E231,E252,W503

################################################################
.PHONY: dump.txt
dump.txt:
	/bin/rm -f dump.txt && touch dump.txt && tree . > dump.txt && \
	for fn in Makefile template.yaml lambda-resize/src/resize_app/*.py src/app/*.py src/app/*/{*.js,*.html}; do echo "== $$fn ==" >> dump.txt ; cat $$fn >> dump.txt; done



################################################################
## Program development: dynamic analysis
##

## These tests use fixtures that create DynamoDB Local and MinIO (when AWS_REGION=local, the default).
## PYTHONPATH includes lambda-resize/src so tests that use resize_app (tracer, lambda_tracing_handler) can load it.
## PYTHONPATH includes lambda-web/src so tests can exercise the Flask app through the Lambda-web adapter.
## Set LOG_LEVEL at start of CLI to change the log level.

pytest: $(LOCAL_TEST_REQ)
	$(MAKE) vend-lambda-resize
	$(MAKE) vend-lambda-web
	$(LOCAL_AWS_ENV) PYTHONPATH=.:src:lambda-web/src:lambda-resize/src:$$PYTHONPATH uv run pytest -vv --log-cli-level=$(LOG_LEVEL) tests lambda-web/tests lambda-resize/tests

pytest-coverage: $(LOCAL_TEST_REQ)
	$(MAKE) vend-lambda-resize
	$(MAKE) vend-lambda-web
	$(LOCAL_AWS_ENV) PYTHONPATH=.:src:lambda-web/src:lambda-resize/src:$$PYTHONPATH uv run pytest -vv --log-cli-level=$(LOG_LEVEL) --cov=src --cov=lambda-web/src/lambda_web --cov=lambda-resize/src --cov-report=xml --cov-report=html tests lambda-web/tests lambda-resize/tests
	@echo coverage report in htmlcov/

# This doesn't work yet...
pytest-selenium:
	uv run pytest -v --log-cli-level=$(LOG_LEVEL) tests/sitetitle_test.py

.PHONY: frame-step-browser-test
frame-step-browser-test: .venv/pyvenv.cfg
	uv run python -m pytest -v --log-cli-level=$(LOG_LEVEL) browser_tests/frame_step_browser_test.py

ANALYSIS_MP4_INPUT ?=
ANALYSIS_MP4_OUTPUT ?=
ANALYSIS_MP4_ROTATION ?= 0
ANALYSIS_MP4_MAX_WIDTH ?= 640
ANALYSIS_MP4_MAX_HEIGHT ?= 480

.PHONY: analysis-mp4-bundle analysis-mp4-browser-test
analysis-mp4-bundle: install-lambda-deps
	@test -n "$(ANALYSIS_MP4_INPUT)" || (echo "set ANALYSIS_MP4_INPUT=/path/to/movie.mp4"; exit 2)
	@test -n "$(ANALYSIS_MP4_OUTPUT)" || (echo "set ANALYSIS_MP4_OUTPUT=/path/to/new-bundle-directory"; exit 2)
	$(MAKE) vend-lambda-resize
	PYTHONPATH=lambda-resize/src:$$PYTHONPATH uv run python -m resize_app.analysis_mp4_cli \
		"$(ANALYSIS_MP4_INPUT)" "$(ANALYSIS_MP4_OUTPUT)" \
		--rotation "$(ANALYSIS_MP4_ROTATION)" \
		--max-width "$(ANALYSIS_MP4_MAX_WIDTH)" \
		--max-height "$(ANALYSIS_MP4_MAX_HEIGHT)"

analysis-mp4-browser-test: install-lambda-deps
	$(MAKE) vend-lambda-resize
	PYTHONPATH=.:lambda-resize/src:$$PYTHONPATH uv run pytest -v --log-cli-level=$(LOG_LEVEL) browser_tests/analysis_mp4_browser_test.py

# Set these during development to speed testing of the one function you care about:
TEST1MODULE=tests/endpoint_test.py
#TEST1FUNCTION="-k test_ver1"
pytest1:
	$(LOCAL_AWS_ENV) PYTHONPATH=.:src:lambda-web/src:lambda-resize/src:$$PYTHONPATH uv run pytest -v --log-cli-level=$(LOG_LEVEL) --maxfail=1 $(TEST1MODULE) $(TEST1FUNCTION)

################################################################
### Debug targets to develop and run locally.

start-local-services:
	$(MAKE) -j3 start_local_dynamodb start_local_minio start_local_mailpit

stop-local-services:
	$(MAKE) stop_local_dynamodb stop_local_minio stop_local_mailpit

wipe-local:
	@echo wiping all local artifacts and remaking the local bucket.
	$(MAKE) stop-local-services
	/bin/rm -rf var
	mkdir -p var
	$(MAKE) start-local-services
	$(MAKE) make-local-bucket

delete-local:
	@echo deleting all local artifacts
	$(MAKE) stop-local-services
	/bin/rm -rf var

make-local-demo:
	@echo creating local demo tables, course, and movies with the prefix demo-
	$(MAKE) start-local-services
	$(MAKE) make-local-bucket
	$(LOCAL_AWS_ENV) uv run python $(DBUTIL) createdb
	$(LOCAL_AWS_ENV) uv run python $(DBUTIL) create-demo-course
	$(LOCAL_AWS_ENV) uv run python $(DBUTIL) seed-demo-movies
	$(LOCAL_AWS_ENV) aws s3 ls --recursive s3://$(LOCAL_BUCKET)

ensure-local-lambda-debug:
	@if $(LOCAL_LAMBDA_PROBE); then \
		echo "Local lambda debug server already running on $(LOCAL_LAMBDA_BASE)"; \
	else \
		if [ "$$(uname -s)" = "Darwin" ]; then \
			echo "Starting local lambda debug server in a new macOS terminal window..."; \
			bash etc/open_local_lambda_terminal.sh "$(CURDIR)" "make run-local-lambda-debug"; \
		else \
			echo "Please start the local lambda debug server in another shell with: make run-local-lambda-debug"; \
		fi; \
		for attempt in $$(seq 1 $(LOCAL_LAMBDA_WAIT_SECONDS)); do \
			if $(LOCAL_LAMBDA_PROBE); then \
				exit 0; \
			fi; \
			sleep 1; \
		done; \
		echo "Local lambda debug server did not start on $(LOCAL_LAMBDA_BASE)."; \
		echo "Give the new terminal a moment, then run again or start it manually with: make run-local-lambda-debug"; \
		exit 1; \
	fi

run-local-lambda-debug:
	@echo running the local lambda debug server at $(LOCAL_LAMBDA_BASE)
	$(MAKE) vend-lambda-resize
	$(LOCAL_AWS_ENV) PYTHONPATH=lambda-resize/src:$$PYTHONPATH TRACING_QUEUE_MODE=local LOG_LEVEL=$(LOG_LEVEL) uv run python -m app.local_lambda_debug --host 127.0.0.1 --port $(LOCAL_LAMBDA_PORT)

run-local-debug:
	@echo run Flask locally against the local demo dataset, but not in demo mode
	$(MAKE) ensure-local-lambda-debug
	$(LOCAL_NONDEMO_ENV) uv run python $(DBUTIL) makelink $(LOCAL_ADMIN_EMAIL) --planttracer_endpoint http://localhost:$(LOCAL_HTTP_PORT)
	$(LOCAL_NONDEMO_ENV) $(FLASK_DEBUG_RUN)

run-local-demo-debug:
	@echo run Flask locally in demo mode, using local database and debug mode
	@echo connect to http://localhost:$(LOCAL_HTTP_PORT)
	$(MAKE) make-local-demo
	$(MAKE) ensure-local-lambda-debug
	$(LOCAL_DEMO_ENV) $(FLASK_DEBUG_RUN)

debug-dev-api:
	@echo Debug local JavaScript with remote server.
	@echo run bottle locally in debug mode, storing new data in S3, with the dev.planttracer.com database and API calls
	@echo This makes it easy to modify the JavaScript locally with the remote API support
	@echo And we should not require any of the variables -but we enable them just in case
	PLANTTRACER_API_BASE=https://dev.planttracer.com/ $(FLASK_DEBUG_RUN)

tracer-debug: vend-lambda-resize
	@echo just test the tracer...
	/bin/rm -f outfile.mp4
	PYTHONPATH=lambda-resize/src uv run python lambda-resize/src/lambda_resize_cli.py tracer --infile="tests/data/2019-07-12 circumnutation.mp4" --movie-traced=outfile.mp4
	open outfile.mp4

.PHONY: start-local-services stop-local-services wipe-local delete-local make-local-demo ensure-local-lambda-debug run-local-lambda-debug run-local-debug run-local-demo-debug debut-dev-api tracer-debug

################################################################
### JavaScript

eslint:
	if [ ! -d src/app/static ]; then echo no src/app/static ; exit 1 ; fi
	(cd src/app/static;make eslint)
	if [ ! -d src/app/templates ]; then echo no src/app/templates ; exit 1 ; fi
	(cd src/app/templates;make eslint)

jscoverage:
	NODE_ENV=test NODE_PATH=src/app/static npm run coverage
	NODE_PATH=src/app/static npm test

instrument-js:
	@echo "Instrumenting JavaScript files for browser coverage..."
	@NODE_ENV=test node scripts/instrument-js.js

browser-coverage-xml:
	@echo Converting browser coverage to XML...
	@if [ -f coverage/browser-coverage.json ]; then \
		uv run python -c "from tests.js_coverage_utils import convert_browser_coverage_to_xml; from pathlib import Path; convert_browser_coverage_to_xml(Path('coverage/browser-coverage.json'), Path('coverage/browser-coverage.xml'))"; \
		echo Browser coverage converted to coverage/browser-coverage.xml; \
	else \
		echo No browser coverage found; \
	fi

jstest-debug:
	NODE_PATH=src/app/static npm run test-debug


################################################################
# DynamoDBLocal
# Installations are used by the CI pipeline and by local developers
# See https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html for info about DynamoDB (local version)

# installation:
DDBL_DOWNLOAD_URL:=https://d1ni2b6xgvw0s0.cloudfront.net/v2.x/dynamodb_local_latest.zip
bin/dynamodb_local_latest.zip:
	test -f bin/dynamodb_local_latest.zip || curl $(DDBL_DOWNLOAD_URL) -o bin/dynamodb_local_latest.zip
	test -f bin/dynamodb_local_latest.zip || (echo could not download $(DDBL_DOWNLOAD_URL); exit 1)
	find bin -ls

bin/DynamoDBLocal.jar: bin/dynamodb_local_latest.zip
	(cd bin; unzip -uq dynamodb_local_latest.zip DynamoDBLocal.jar 'DynamoDBLocal_lib/*')
	touch bin/DynamoDBLocal.jar

# operation:
start_local_dynamodb: bin/DynamoDBLocal.jar
	uv run python bin/local_services.py dynamodb start

stop_local_dynamodb:  bin/DynamoDBLocal.jar
	uv run python bin/local_services.py dynamodb stop

list-tables:
	$(LOCAL_AWS_ENV) aws dynamodb list-tables

dump-demo-tables:
	for tn in "demo-api_keys" "demo-course_users" "demo-courses" "demo-logs" "demo-movie_frames" "demo-movies" "demo-unique_emails" "demo-users" ; do\
		echo $$tn:; \
		$(LOCAL_AWS_ENV) aws dynamodb describe-table --table-name $$tn ; \
		$(LOCAL_AWS_ENV) aws dynamodb scan --max-items 5 --table-name $$tn ; \
		done


.PHONY: start_local_dynamodb stop_local_dynamodb list-tables dump-demo-tables
################################################################
# Mailpit (local SMTP catcher -- see: https://github.com/axllent/mailpit)
# Accepts SMTP on port 1025; web UI at http://localhost:8025

MAILPIT_VERSION=latest
MAILPIT_LINUX_AMD64=https://github.com/axllent/mailpit/releases/latest/download/mailpit-linux-amd64.tar.gz
MAILPIT_LINUX_ARM64=https://github.com/axllent/mailpit/releases/latest/download/mailpit-linux-arm64.tar.gz
MAILPIT_DARWIN_ARM64=https://github.com/axllent/mailpit/releases/latest/download/mailpit-darwin-arm64.tar.gz
MAILPIT_DARWIN_AMD64=https://github.com/axllent/mailpit/releases/latest/download/mailpit-darwin-amd64.tar.gz

bin/mailpit:
	@echo downloading and installing mailpit
	mkdir -p bin
	uname -a
	arch
	if [ "$$(uname -s)" = "Linux" ] && [ "$$(uname -m)" = "amd64" -o "$$(uname -m)" = "x86_64" ] ; then \
		echo Linux amd64/x86_64 ; curl -fL $(MAILPIT_LINUX_AMD64) | tar -xz -C bin mailpit ; \
	elif [ "$$(uname -s)" = "Linux" ] && [ "$$(uname -m)" = "aarch64" -o "$$(uname -m)" = "arm64" ] ; then \
		echo Linux arm64 ; curl -fL $(MAILPIT_LINUX_ARM64) | tar -xz -C bin mailpit ; \
	elif [ "$$(uname -s)" = "Darwin" ] && [ "$$(uname -m)" = "arm64" ] ; then \
		echo Darwin arm64 ; curl -fL $(MAILPIT_DARWIN_ARM64) | tar -xz -C bin mailpit ; \
	elif [ "$$(uname -s)" = "Darwin" ] ; then \
		echo Darwin amd64 ; curl -fL $(MAILPIT_DARWIN_AMD64) | tar -xz -C bin mailpit ; \
	else \
		echo unknown os/architecture; exit 1; \
	fi
	chmod +x bin/mailpit
	ls -l bin/mailpit
	file bin/mailpit

start_local_mailpit: bin/mailpit
	uv run python bin/local_services.py mailpit start

stop_local_mailpit: bin/mailpit
	uv run python bin/local_services.py mailpit stop

.PHONY: start_local_mailpit stop_local_mailpit

################################################################
# Minio (S3 clone -- see: https://min.io/)
# Installations are used by the CI pipeline and by local developers

# Sources:
LINUX_BASE=https://dl.min.io/server/minio/release/linux-amd64
LINUX_BASE_MC=https://dl.min.io/client/mc/release/linux-amd64
LINUX_ARM_BASE=https://dl.min.io/server/minio/release/linux-arm64
LINUX_ARM_BASE_MC=https://dl.min.io/client/mc/release/linux-arm64
MACOS_AMD64_BASE=https://dl.min.io/server/minio/release/darwin-amd64
MACOS_ARM_BASE=https://dl.min.io/server/minio/release/darwin-arm64
MACOS_AMD64_BASE_MC=https://dl.min.io/client/mc/release/darwin-amd64
MACOS_ARM_BASE_MC=https://dl.min.io/client/mc/release/darwin-arm64
bin/minio:
	@echo downloading and installing minio
	mkdir -p bin
	uname -a
	arch
	if [ "$$(uname -s)" = "Linux" ] && [ "$$(uname -m)" = "amd64" ] ; then \
		echo Linux amd64 ; curl -fL $(LINUX_BASE)/minio -o bin/minio ; curl -fL $(LINUX_BASE_MC)/mc -o bin/mc ; \
	elif [ "$$(uname -s)" = "Linux" ] && [ "$$(uname -m)" = "x86_64" ] ; then \
		echo Linux x86_64 ; curl -fL $(LINUX_BASE)/minio -o bin/minio ; curl -fL $(LINUX_BASE_MC)/mc -o bin/mc ; \
	elif [ "$$(uname -s)" = "Linux" ] && [ "$$(uname -m)" = "aarch64" ] ; then \
		echo Linux aarch64 ; curl -fL $(LINUX_ARM_BASE)/minio -o bin/minio ; curl -fL $(LINUX_ARM_BASE_MC)/mc -o bin/mc ; \
	elif [ "$$(uname -s)" = "Linux" ] && [ "$$(uname -m)" = "arm64" ] ; then \
		echo Linux arm64 ; curl -fL $(LINUX_ARM_BASE)/minio -o bin/minio ; curl -fL $(LINUX_ARM_BASE_MC)/mc -o bin/mc ; \
	elif [ "$$(uname -s)" = "Darwin" ] && [ "$$(uname -m)" = "arm64" ] ; then \
		echo Darwin arm64 ; curl -fL $(MACOS_ARM_BASE)/minio -o bin/minio ; curl -fL $(MACOS_ARM_BASE_MC)/mc -o bin/mc ; \
	elif [ "$$(uname -s)" = "Darwin" ] ; then \
		echo Darwin amd64 ; curl -fL $(MACOS_AMD64_BASE)/minio -o bin/minio ; curl -fL $(MACOS_AMD64_BASE_MC)/mc -o bin/mc ; \
	else \
		echo unknown os/architecture; exit 1; \
	fi
	chmod +x bin/minio
	ls -l bin/minio
	file bin/minio
	if [ -f bin/mc ] ; then \
		chmod +x bin/mc ; \
		ls -l bin/mc ; \
		file bin/mc ; \
	fi

# operation:
start_local_minio: bin/minio
	uv run python bin/local_services.py minio start

stop_local_minio:  bin/minio
	uv run python bin/local_services.py minio stop

list-local-buckets:
	$(LOCAL_AWS_ENV) aws s3 ls

make-local-bucket:
	if $(LOCAL_AWS_ENV) aws s3 ls s3://$(LOCAL_BUCKET)/ >/dev/null 2>&1; then \
	 	echo $(LOCAL_BUCKET) exists ; \
	else \
		echo creating s3://$(LOCAL_BUCKET)/ ; \
		$(LOCAL_AWS_ENV) aws s3 mb s3://$(LOCAL_BUCKET)/ ; \
	fi
	echo local buckets:
	$(LOCAL_AWS_ENV) aws s3 ls

.PHONY: start_local_minio stop_local_minio list-local-buckets make-local-bucket

################################################################
# Includes ubuntu dependencies
# Note: on GitHub, install ffmpeg first with https://github.com/marketplace/actions/setup-ffmpeg
# Note: installing pipx and poetry may have problems here. It's better to install outside of the Makefile
install-ubuntu:
	@echo install-ubuntu
	sudo apt-get update
	which aws      || sudo snap install aws-cli --classic | cat # cat suppresses TTY junk
	which chromium || sudo apt-get install -y -qq chromium-browser chromium-chromedriver
	which curl     || sudo apt-get install -y -qq curl
	which ffmpeg   || sudo apt-get install -y -qq ffmpeg
	which lsof     || sudo apt-get install -y -qq lsof
	which node     || sudo apt-get install -y -qq nodejs
	node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major > 20 || (major === 20 && minor >= 8) ? 0 : 1)' || { curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -; sudo apt-get install -y -qq nodejs; }
	which npm      || sudo apt-get install -y -qq npm
	which zip      || sudo apt-get install -y -qq zip
	which java     || sudo apt-get install -y -qq openjdk-21-jre-headless
	@# npm deprecation warnings (WARN deprecated) from transitive deps can be ignored
	npm ci
	$(MAKE) $(REQ)
	@echo install-ubuntu done



# Includes MacOS dependencies managed through Brew
BREW_INSTALL=HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_ENV_HINTS=1 brew install
BREW_INSTALL_CASK=HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_ENV_HINTS=1 brew install --cask
install-macos:
	command -v aws >/dev/null || $(BREW_INSTALL) awscli
	if command -v chromium >/dev/null 2>&1 || command -v google-chrome >/dev/null 2>&1 || [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ] || [ -x "/Applications/Chromium.app/Contents/MacOS/Chromium" ]; then \
		echo "Chrome/Chromium is available"; \
	else \
		$(BREW_INSTALL_CASK) google-chrome ; \
	fi
	command -v ffmpeg >/dev/null || $(BREW_INSTALL) ffmpeg
	command -v lsof >/dev/null || $(BREW_INSTALL) lsof
	command -v node >/dev/null || $(BREW_INSTALL) node
	command -v npm >/dev/null || $(BREW_INSTALL) node
	command -v poetry >/dev/null || $(BREW_INSTALL) poetry
	command -v python3 >/dev/null || $(BREW_INSTALL) python
	npm ci
	npm install -g typescript webpack webpack-cli
	$(MAKE) $(REQ)

# Includes Windows dependencies
# restart the shell after installs are done
# choco install as administrator
# Note: development on windows is not currently supported
install-windows: .venv/pyvenv.cfg
	choco install -y make
	choco install -y ffmpeg
	choco install -y nodejs
	choco install -y chromium
	choco install -y poetry
	npm ci
	npm install -g typescript webpack webpack-cli
	$(MAKE) $(REQ)


################################################################
### Development server: run gunicorn with --reload (patches service file)
gunicorn-reload:
	@echo Patching planttracer.service to add gunicorn --reload...
	sudo sed -i 's|\(ExecStart=.*/gunicorn\) \(-[wb]\)|\1 --reload \2|' /etc/systemd/system/planttracer.service || true
	sudo systemctl daemon-reload
	sudo systemctl restart planttracer.service
	@echo planttracer.service restarted with --reload.

################################################################
### Cleanup

clean:
	find . -name '*~' -exec rm {} \;
	/bin/rm -rf __pycache__ */__pycache__

## What follows is under development

################################################################
# SAM Commands - for deploying on AWS Lambda. This is all under development

# Install for AWS Linux for running SAM
# Start with:
# sudo dfn install git && git clone --recursive https://github.com/Plant-Tracer/webapp && (cd webapp; make aws-install)
install-aws-sam-tools:
	echo install for AWS Linux, for making the lambda.
	echo note does not install ffmpeg currently
	(cd $HOME; \
	 	wget https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-x86_64.zip; \
		unzip aws-sam-cli-linux-x86_64.zip -d sam-installation; \
		sudo ./sam-installation/install )
	sudo dnf install -y docker
	sudo systemctl enable docker
	sudo systemctl start docker
	sudo dnf install -y python3.11
	sudo dnf install -y nodejs npm
	sudo dnf install -y make
	sudo dnf install -y cronie
	npm ci
	make $(REQ)


# Debug target to see exactly what permissions your current SSO role has
check-iam:
	@echo "Checking current caller identity..."
	@ROLE_ARN=$$(aws sts get-caller-identity --query Arn --output text); \
	echo "Current ARN: $$ROLE_ARN"; \
	if echo "$$ROLE_ARN" | grep -q "assumed-role"; then \
		ROLE_NAME=$$(echo "$$ROLE_ARN" | cut -d/ -f2); \
		echo "Detected SSO Role Name: $$ROLE_NAME"; \
		echo ""; \
		echo "=== Attached Managed Policies ==="; \
		aws iam list-attached-role-policies --role-name "$$ROLE_NAME" --output table --no-cli-pager; \
		echo ""; \
		echo "=== Inline Policy Names ==="; \
		INLINE_POLICIES=$$(aws iam list-role-policies --role-name "$$ROLE_NAME" --query 'PolicyNames' --output text); \
		echo "Found: $$INLINE_POLICIES"; \
		for policy in $$INLINE_POLICIES; do \
			echo ""; \
			echo "--- Content of Inline Policy: $$policy ---"; \
			aws iam get-role-policy --role-name "$$ROLE_NAME" --policy-name "$$policy" --query 'PolicyDocument' --output json --no-cli-pager; \
		done; \
	else \
		echo "You are not using an assumed role. Check your AWS_PROFILE."; \
	fi

################################################################
## lambda-resize

vend-lambda-resize:
	mkdir -p lambda-resize/src/resize_app/src/app
	rsync --verbose --archive $(VEND_FILES) \
		lambda-resize/src/resize_app/src/app/
	cp pyproject.toml lambda-resize/src/resize_app/src/app/pyproject.toml

# Install lambda group so root venv can run lambda-resize lint/tests (single pyproject).
install-lambda-deps: $(REQ)
	poetry install --with lambda

# lambda-resize: lint and test from root using root venv (deps from pyproject group lambda).
# install-lambda-deps ensures av (and other lambda deps) are in the venv so pylint can import them.
lambda-resize-lint: install-lambda-deps
	$(MAKE) vend-lambda-resize
	uv run ruff check --fix lambda-resize/src
	PYTHONPATH=lambda-resize/src uv run pylint lambda-resize/src

lambda-resize-check: lambda-resize-lint $(LOCAL_TEST_REQ)
	$(LOCAL_AWS_ENV) PYTHONPATH=.:src:lambda-resize/src:$$PYTHONPATH uv run pytest lambda-resize/tests -q --cov=lambda-resize/src --cov-report=term -o junit_family=legacy --log-cli-level=$(LOG_LEVEL)

################################################################
## lambda-web

vend-lambda-web:
	mkdir -p lambda-web/src/app
	rsync --verbose --archive --delete --delete-excluded \
		--exclude .DS_Store \
		--exclude __pycache__ \
		--exclude '*.pyc' \
		--exclude static-instrumented \
		src/app/ lambda-web/src/app/
	cp pyproject.toml lambda-web/src/app/pyproject.toml

# Install lambda-web group so root venv can run lambda-web lint/tests.
install-lambda-web-deps: $(REQ)
	poetry install --with lambda-web

lambda-web-lint: install-lambda-web-deps
	uv run ruff check --fix lambda-web/src/lambda_web lambda-web/tests
	PYTHONPATH=.:src:lambda-web/src uv run pylint lambda-web/src/lambda_web lambda-web/tests

lambda-web-check: lambda-web-lint
	$(MAKE) vend-lambda-web
	PYTHONPATH=.:src:lambda-web/src uv run pytest lambda-web/tests -q --cov=lambda-web/src/lambda_web --cov-report=term -o junit_family=legacy --log-cli-level=$(LOG_LEVEL)

.PHONY: lambda-resize/src/requirements.txt lambda-web/src/requirements.txt template-lint sam-config-show sam-config-path-safety-check sam-config-sync sam-config-path-check sam-config-check sam-config-guided-bootstrap sam-version-check sam-source-commit-check stamp-lambda-web-source-commit lambda-web-source-commit-check sam-deploy-version-check stamp-sam-deploy-metadata sam-storage-configure sam-status
lambda-resize/src/requirements.txt:
	poetry export --with lambda --without dev --without vm --format=requirements.txt --output lambda-resize/src/requirements.txt --without-hashes

lambda-web/src/requirements.txt:
	poetry export --with lambda-web --without dev --without lambda --without vm --format=requirements.txt --output lambda-web/src/requirements.txt --without-hashes

template-lint: .venv/pyvenv.cfg
	sam validate --lint
	@echo cfn-lint requires a valid AWS_REGION so we use us-east-1
	AWS_REGION=us-east-1 uv run cfn-lint template.yaml

sam-config-show: sam-config-sync
	@echo "SAM_CONFIG=$(SAM_CONFIG)"
	@echo "STACK_NAME=$(EFFECTIVE_STACK_NAME)"
	@echo "CONFIG_STACK_NAME=$(SAM_CONFIG_STACK_NAME)"
	@echo "DYNAMODB_TABLE_PREFIX=$(SAM_CONFIG_DYNAMODB_TABLE_PREFIX)"

sam-config-path-safety-check:
	@if [ -n "$(stack)" ] && [ -z "$(STACK)" ]; then \
		echo "Refusing to use SAM: found lowercase stack=$(stack), but this Makefile expects STACK=<name> or STACK_NAME=<name>."; \
		echo "Make variables are case-sensitive; rerun with STACK=$(stack)."; \
		exit 1; \
	fi
	@if [ -z "$(SAM_CONFIG)" ]; then \
		echo "Refusing to use SAM: SAM_CONFIG is not set."; \
		echo "Pass STACK=<name> or STACK_NAME=<name> to use $(SAM_CONFIG_DIR)/<name>.toml, or pass SAM_CONFIG=<path>."; \
		exit 1; \
	fi
	@if git ls-files --error-unmatch "$(SAM_CONFIG)" >/dev/null 2>&1; then \
		echo "Refusing to use SAM: $(SAM_CONFIG) is tracked by git."; \
		echo "SAM config files are per-stack local state and must stay out of the repo."; \
		exit 1; \
	fi
	@case "$(SAM_CONFIG)" in \
		/*) ;; \
		*) if ! git check-ignore -q "$(SAM_CONFIG)"; then \
			echo "Refusing to use SAM: $(SAM_CONFIG) is not ignored by git."; \
			echo "Use STACK=<name> or STACK_NAME=<name> for $(SAM_CONFIG_DIR)/<name>.toml, or add the local SAM config path to .gitignore."; \
			exit 1; \
		fi ;; \
	esac

sam-config-sync: sam-config-path-safety-check
	@if [ -n "$(EFFECTIVE_STACK_NAME)" ]; then \
		PREFIX="$(DYNAMODB_TABLE_PREFIX_INPUT)"; \
		if [ -z "$$PREFIX" ]; then PREFIX="$(EFFECTIVE_STACK_NAME)-"; fi; \
		uv run python etc/sam_config_writer.py --samconfig "$(SAM_CONFIG)" \
			--stack-name "$(EFFECTIVE_STACK_NAME)" --dynamodb-table-prefix "$$PREFIX"; \
	fi

sam-config-path-check: sam-config-sync
	@if [ -n "$(EFFECTIVE_STACK_NAME)" ] && [ -n "$(SAM_CONFIG_STACK_NAME)" ] && [ "$(SAM_CONFIG_STACK_NAME)" != "$(EFFECTIVE_STACK_NAME)" ]; then \
		echo "Refusing to use SAM: target stack=$(EFFECTIVE_STACK_NAME) but $(SAM_CONFIG) has stack_name=$(SAM_CONFIG_STACK_NAME)."; \
		exit 1; \
	fi
	@if [ -n "$(EFFECTIVE_STACK_NAME)" ]; then \
		REQUESTED_PREFIX="$(DYNAMODB_TABLE_PREFIX_INPUT)"; \
		if [ -z "$$REQUESTED_PREFIX" ]; then REQUESTED_PREFIX="$(EFFECTIVE_STACK_NAME)-"; fi; \
		CONFIG_PREFIX="$(SAM_CONFIG_DYNAMODB_TABLE_PREFIX)"; \
		if [ "$${REQUESTED_PREFIX%-}" != "$${CONFIG_PREFIX%-}" ]; then \
			echo "Refusing to use SAM: synchronized DYNAMODB_TABLE_PREFIX=$$REQUESTED_PREFIX but $(SAM_CONFIG) configures $$CONFIG_PREFIX."; \
			exit 1; \
		fi; \
	fi

sam-config-check: sam-config-path-check
	@if [ ! -f "$(SAM_CONFIG)" ]; then \
		echo "Refusing to use SAM: $(SAM_CONFIG) does not exist."; \
		echo "Run STACK=<name> or STACK_NAME=<name> with make sam-deploy-guided to create it, or pass SAM_CONFIG=<path>."; \
		exit 1; \
	fi

sam-config-guided-bootstrap: sam-config-path-check

stamp-sam-deploy-metadata: sam-version-check
	@if [ ! -d "$(SAM_BUILD_DIR)/LambdaResizeFunction/resize_app" ]; then \
		echo "Refusing to stamp deploy metadata: $(SAM_BUILD_DIR)/LambdaResizeFunction/resize_app is missing."; \
		echo "Run make sam-build before deploying."; \
		exit 1; \
	fi
	@DEPLOYED_AT=$$(date -u +"%Y-%m-%dT%H:%M:%SZ"); \
	METADATA_FILE="$(SAM_BUILD_DIR)/LambdaResizeFunction/resize_app/deploy_metadata.json"; \
	printf '{\n  "deployed_at": "%s",\n  "app_version": "%s"\n}\n' "$$DEPLOYED_AT" "$(APP_VERSION)" > "$$METADATA_FILE"; \
	echo "Stamped $$METADATA_FILE with deployed_at=$$DEPLOYED_AT app_version=$(APP_VERSION)."

sam-build: $(REQ)
	@# Refuse to build if there are local changes, unless HEAD is an exact tag
	@# or a branch with an upstream and no unpushed commits.
	@if ! git diff --quiet || ! git diff --cached --quiet; then \
	  echo "Refusing to run sam-build: uncommitted changes present (stash/commit first)."; \
	  exit 1; \
	fi
	@TAG=$$(git describe --exact-match --tags HEAD 2>/dev/null || true); \
	if [ -n "$$TAG" ]; then \
	  echo "Building SAM artifact from tag $$TAG"; \
	else \
	  UPSTREAM=$$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || true); \
	  if [ -z "$$UPSTREAM" ]; then \
	    echo "Refusing to run sam-build: current branch has no upstream and HEAD is not an exact tag."; \
	    exit 1; \
	  fi; \
	  if [ -n "$$(git log --oneline "$$UPSTREAM"..HEAD)" ]; then \
	    echo "Refusing to run sam-build: branch has unpushed commits."; \
	    exit 1; \
	  fi; \
	fi; \
	$(MAKE) lambda-web/src/requirements.txt
	$(MAKE) lambda-resize/src/requirements.txt
	$(MAKE) vend-lambda-web
	$(MAKE) stamp-lambda-web-source-commit
	$(MAKE) vend-lambda-resize
	uv run pylint $(PYLINT_OPTS) lambda-web/src/lambda_web
	uv run pylint $(PYLINT_OPTS) lambda-resize/src
	poetry check --lock
	uv lock --check
	finch vm start || echo AWS finch is already running
	sam validate --lint
	@echo cfn-lint requires a valid AWS_REGION so we use us-east-1
	AWS_REGION=us-east-1 uv run cfn-lint template.yaml
	@# Do not add --parallel here; SAM emits urllib3 cleanup tracebacks during parallel container builds.
	DOCKER_DEFAULT_PLATFORM=linux/arm64 sam build --use-container
	@echo "========================================"
	@echo "Checking unzipped artifact sizes..."
	@for dir in .aws-sam/build/*/ ; do \
		if [ -d "$$dir" ]; then \
			size_mb=$$(du -sm "$$dir" | cut -f1); \
			echo "Size of $$dir is $${size_mb}MB"; \
			if [ "$$size_mb" -ge 250 ]; then \
				echo "ERROR: $$dir exceeds the AWS Lambda 250MB unzipped limit!"; \
				exit 1; \
			fi; \
		fi; \
	done
	@echo "Size check passed! All functions are under 250MB."

sam-audit-size:
	@echo "========================================"
	@echo "Top 20 largest items in SAM build directories (sizes in MB):"
	@if [ ! -d ".aws-sam/build" ]; then \
		echo "ERROR: .aws-sam/build not found. Run 'make sam-build' first."; \
		exit 1; \
	fi
	@for dir in .aws-sam/build/*/ ; do \
		if [ -d "$$dir" ]; then \
			echo "----------------------------------------"; \
			echo "Analyzing: $$dir"; \
			du -sm "$$dir"* | sort -nr | head -n 20; \
		fi; \
	done
	@echo "========================================"

sam-version-check:
	@if [ -z "$(APP_VERSION)" ]; then \
		echo "Refusing to deploy: could not read version from pyproject.toml."; \
		exit 1; \
	fi
	@echo "Application version check passed for version $(APP_VERSION)."

sam-source-commit-check:
	@SOURCE_COMMIT=$$(git rev-parse --verify HEAD 2>/dev/null || true); \
	if ! printf '%s\n' "$$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$$'; then \
		echo "Refusing to build or deploy: could not determine a full source commit SHA."; \
		exit 1; \
	fi; \
	echo "Source commit check passed for $$SOURCE_COMMIT."

stamp-lambda-web-source-commit: sam-source-commit-check
	@METADATA_FILE="lambda-web/src/app/build_metadata.py"; \
	if [ ! -f "$$METADATA_FILE" ]; then \
		echo "Refusing to stamp source commit: $$METADATA_FILE is missing."; \
		echo "Run make vend-lambda-web first."; \
		exit 1; \
	fi; \
	SOURCE_COMMIT=$$(git rev-parse --verify HEAD); \
	printf '"""Build-time metadata for this Lambda artifact."""\n\nGIT_COMMIT = "%s"\n' "$$SOURCE_COMMIT" > "$$METADATA_FILE"; \
	echo "Stamped $$METADATA_FILE with git_commit=$$SOURCE_COMMIT."

lambda-web-source-commit-check: vend-lambda-web stamp-lambda-web-source-commit
	@PYTHONPATH=lambda-web/src uv run python -c 'from app.constants import git_commit; assert len(git_commit()) == 40, git_commit()'

sam-deploy-version-check: sam-config-check sam-version-check sam-source-commit-check
	@if [ -z "$(EFFECTIVE_STACK_NAME)" ]; then \
		echo "Refusing to deploy: stack_name is not set in $(SAM_CONFIG)."; \
		exit 1; \
	fi
	@APP_URL=$$(aws cloudformation describe-stacks --stack-name "$(EFFECTIVE_STACK_NAME)" --query 'Stacks[0].Outputs[?OutputKey==`ApplicationUrl`].OutputValue | [0]' --output text 2>/dev/null || true); \
	if [ -z "$$APP_URL" ] || [ "$$APP_URL" = "None" ]; then \
		DNS=$$(aws cloudformation describe-stacks --stack-name "$(EFFECTIVE_STACK_NAME)" --query 'Stacks[0].Outputs[?OutputKey==`LambdaDnsName`].OutputValue | [0]' --output text 2>/dev/null || true); \
		if [ -n "$$DNS" ] && [ "$$DNS" != "None" ]; then \
			APP_URL="https://$$DNS/"; \
		fi; \
	fi; \
	if [ -z "$$APP_URL" ] || [ "$$APP_URL" = "None" ]; then \
		echo "WARNING: could not resolve deployed URL for $(EFFECTIVE_STACK_NAME); allowing deploy."; \
	else \
			VERSION_URL="$${APP_URL%/}/api/ver"; \
			VERSION_BODY=$$(curl -fsS --max-time 10 "$$VERSION_URL" 2>/dev/null || true); \
			DEPLOYED_VERSION=$$(uv run python -c 'import json,sys; print(json.load(sys.stdin).get("__version__", ""))' 2>/dev/null <<< "$$VERSION_BODY" || true); \
			DEPLOYED_STACK=$$(uv run python -c 'import json,sys; print(json.load(sys.stdin).get("stack_name", ""))' 2>/dev/null <<< "$$VERSION_BODY" || true); \
			if [ -z "$$DEPLOYED_VERSION" ]; then \
				echo "WARNING: could not read deployed version from $$VERSION_URL; allowing deploy."; \
			elif [ "$$DEPLOYED_VERSION" = "$(APP_VERSION)" ] && [ "$(SAM_DEPLOY_ALLOW_SAME_VERSION)" != "1" ]; then \
				echo "Refusing to deploy $(EFFECTIVE_STACK_NAME): deployed stack already reports version $(APP_VERSION) at $$VERSION_URL."; \
				echo "Deployed endpoint stack_name: $${DEPLOYED_STACK:-unavailable}."; \
				echo "Bump pyproject.toml before deploying again."; \
				echo "This matters for Lambda SnapStart: lambda-web snapshots published versions, so each normal deploy should publish a deliberately new application version."; \
				echo "For an intentional same-version redeploy, set SAM_DEPLOY_ALLOW_SAME_VERSION=1."; \
				exit 1; \
			else \
				echo "Deploy version check passed for $(EFFECTIVE_STACK_NAME): deployed=$$DEPLOYED_VERSION local=$(APP_VERSION) endpoint_stack=$${DEPLOYED_STACK:-unavailable}."; \
			fi; \
		fi

sam-deploy: $(REQ)
ifeq ($(AWS_REGION),local)
	@echo cannot deploy to local. Please specify AWS_REGION.  && exit 1
endif
	$(MAKE) sam-deploy-version-check
	$(MAKE) stamp-sam-deploy-metadata
	aws sts get-caller-identity --no-cli-pager
	sam deploy --config-file "$(SAM_CONFIG)" --stack-name "$(EFFECTIVE_STACK_NAME)" --no-confirm-changeset --capabilities CAPABILITY_IAM
	$(MAKE) sam-storage-configure
	$(MAKE) sam-status
	$(MAKE) sam-deployed-workflow-test

sam-deploy-guided: $(REQ)
ifeq ($(AWS_REGION),local)
	@echo cannot deploy to local. Please specify AWS_REGION.  && exit 1
endif
	$(MAKE) sam-version-check
	$(MAKE) sam-config-guided-bootstrap
	@if [ -n "$(SAM_CONFIG_STACK_NAME)" ] && [ -n "$(SAM_CONFIG_DYNAMODB_TABLE_PREFIX)" ]; then \
		$(MAKE) sam-deploy-version-check; \
	fi
	$(MAKE) stamp-sam-deploy-metadata
	aws sts get-caller-identity --no-cli-pager
	@echo ===============================
	@echo use one of these S3 buckets:
	aws s3 ls
	sam deploy --config-file "$(SAM_CONFIG)" --guided $(if $(EFFECTIVE_STACK_NAME),--stack-name "$(EFFECTIVE_STACK_NAME)",) --capabilities CAPABILITY_IAM
	$(MAKE) sam-storage-configure
	$(MAKE) sam-status
	$(MAKE) sam-deployed-workflow-test

sam-course-create: sam-config-check
ifeq ($(AWS_REGION),local)
	@echo cannot initialize a deployed stack course with AWS_REGION=local. Please specify AWS_REGION. && exit 1
endif
	@if [ -z "$(EFFECTIVE_STACK_NAME)" ]; then \
		echo "Refusing to create course: stack_name is not set in $(SAM_CONFIG)."; \
		exit 1; \
	fi
	@DDB_PREFIX=$$(aws cloudformation describe-stacks --stack-name "$(EFFECTIVE_STACK_NAME)" --query 'Stacks[0].Parameters[?ParameterKey==`DynamoDBTablePrefix`].ParameterValue | [0]' --output text); \
	APP_URL=$$(aws cloudformation describe-stacks --stack-name "$(EFFECTIVE_STACK_NAME)" --query 'Stacks[0].Outputs[?OutputKey==`ApplicationUrl`].OutputValue | [0]' --output text); \
	if [ -z "$$APP_URL" ] || [ "$$APP_URL" = "None" ]; then \
		DNS=$$(aws cloudformation describe-stacks --stack-name "$(EFFECTIVE_STACK_NAME)" --query 'Stacks[0].Outputs[?OutputKey==`LambdaDnsName`].OutputValue | [0]' --output text); \
		APP_URL="https://$$DNS/"; \
	fi; \
	MAILER_DRY_RUN_STACK=$$(aws cloudformation describe-stacks --stack-name "$(EFFECTIVE_STACK_NAME)" --query 'Stacks[0].Parameters[?ParameterKey==`MailerDryRun`].ParameterValue | [0]' --output text); \
	if [ -z "$$DDB_PREFIX" ] || [ "$$DDB_PREFIX" = "None" ]; then \
		echo "Refusing to create course: stack $(EFFECTIVE_STACK_NAME) did not report DynamoDBTablePrefix."; \
		exit 1; \
	fi; \
	if [ -z "$$APP_URL" ] || [ "$$APP_URL" = "https://None/" ]; then \
		echo "Refusing to create course: stack $(EFFECTIVE_STACK_NAME) did not report ApplicationUrl or LambdaDnsName."; \
		exit 1; \
	fi; \
	if [ -z "$$MAILER_DRY_RUN_STACK" ] || [ "$$MAILER_DRY_RUN_STACK" = "None" ]; then \
		MAILER_DRY_RUN_STACK=false; \
	fi; \
	echo "Creating or verifying course for stack $(EFFECTIVE_STACK_NAME) using DYNAMODB_TABLE_PREFIX=$$DDB_PREFIX and endpoint $$APP_URL"; \
	env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ENDPOINT_URL_S3 \
		DYNAMODB_TABLE_PREFIX="$$DDB_PREFIX" MAILER_DRY_RUN="$$MAILER_DRY_RUN_STACK" \
		uv run python $(DBUTIL) create-course --send-email --planttracer_endpoint "$$APP_URL" $(COURSE_CREATE_FLAGS)

sam-storage-configure: sam-config-check
ifeq ($(AWS_REGION),local)
	@echo cannot configure deployed storage with AWS_REGION=local. Please specify AWS_REGION. && exit 1
endif
	@BUCKET=$$(aws cloudformation describe-stacks --stack-name "$(EFFECTIVE_STACK_NAME)" --query 'Stacks[0].Parameters[?ParameterKey==`ImageBucketName`].ParameterValue | [0]' --output text); \
	if [ -z "$$BUCKET" ] || [ "$$BUCKET" = "None" ]; then \
		echo "Refusing to configure storage: stack $(EFFECTIVE_STACK_NAME) did not report ImageBucketName."; \
		exit 1; \
	fi; \
	echo "Configuring and verifying CORS and EventBridge delivery for $$BUCKET"; \
	uv run python -m app.s3_presigned "$$BUCKET"; \
	$(MAKE) PLANTTRACER_S3_BUCKET="$$BUCKET" CONFIRM_BUCKET="$$BUCKET" s3-eventbridge-enable

s3-eventbridge-status:
	@if [ -z "$(PLANTTRACER_S3_BUCKET)" ]; then \
		echo "PLANTTRACER_S3_BUCKET must be set."; \
		exit 1; \
	fi
	uv run s3_upload_trigger

s3-eventbridge-enable:
	@if [ -z "$(PLANTTRACER_S3_BUCKET)" ]; then \
		echo "PLANTTRACER_S3_BUCKET must be set."; \
		exit 1; \
	fi
	@if [ "$(CONFIRM_BUCKET)" != "$(PLANTTRACER_S3_BUCKET)" ]; then \
		echo "Refusing to modify bucket notifications. Set CONFIRM_BUCKET=$(PLANTTRACER_S3_BUCKET)."; \
		exit 1; \
	fi
	uv run s3_upload_trigger --apply --confirm-bucket "$(CONFIRM_BUCKET)"

# After deploy: verify Lambda URLs. Use curl -s (no -f) so we capture and show body on 4xx/5xx.
# Simplified by Simson
sam-status: sam-config-check sam-source-commit-check
	@echo "Checking Lambda status...";\
	APP_URL="https://$(EFFECTIVE_STACK_NAME).planttracer.com/"; \
	echo APP_URL=$$APP_URL; \
	BASE_URL="$${APP_URL%/}"; \
	VERSION_URL="$$BASE_URL/api/ver"; \
	VERSION_BODY=$$(curl -f -s --max-time 10 "$$VERSION_URL"); \
	DEPLOYED_COMMIT=$$(printf '%s' "$$VERSION_BODY" | uv run python -c 'import json,sys; print(json.load(sys.stdin).get("git_commit", ""))'); \
	EXPECTED_COMMIT=$$(git rev-parse --verify HEAD); \
	if [ "$$DEPLOYED_COMMIT" != "$$EXPECTED_COMMIT" ]; then \
		echo "Deployed source commit mismatch: expected=$$EXPECTED_COMMIT actual=$${DEPLOYED_COMMIT:-unavailable}."; \
		exit 1; \
	fi; \
	echo "Deployment source commit verified: $$DEPLOYED_COMMIT."; \
	printf '%s\n200\n' "$$VERSION_BODY"

sam-deployed-workflow-test: sam-config-check
	@DDB_PREFIX=$$(aws cloudformation describe-stacks --stack-name "$(EFFECTIVE_STACK_NAME)" --query 'Stacks[0].Parameters[?ParameterKey==`DynamoDBTablePrefix`].ParameterValue | [0]' --output text); \
	BUCKET=$$(aws cloudformation describe-stacks --stack-name "$(EFFECTIVE_STACK_NAME)" --query 'Stacks[0].Parameters[?ParameterKey==`ImageBucketName`].ParameterValue | [0]' --output text); \
	if [ -z "$$DDB_PREFIX" ] || [ "$$DDB_PREFIX" = "None" ] || [ -z "$$BUCKET" ] || [ "$$BUCKET" = "None" ]; then \
		echo "Refusing workflow test: stack parameters are incomplete."; \
		exit 1; \
	fi; \
	env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ENDPOINT_URL_S3 \
		DYNAMODB_TABLE_PREFIX="$$DDB_PREFIX" PLANTTRACER_S3_BUCKET="$$BUCKET" \
		PLANTTRACER_STACK_NAME="$(EFFECTIVE_STACK_NAME)" \
		uv run deployed_workflow_test \
			--endpoint "https://$(EFFECTIVE_STACK_NAME).planttracer.com/"

# Shared resolution of Lambda function name (FUNC) and start time (START) for log targets.
# Used by sam-logs, sam-logs-simple, sam-logs-simple-tail.
define SAM_LOGS_RESOLVE
	FUNC=$$(aws cloudformation describe-stacks --stack-name "$(EFFECTIVE_STACK_NAME)" --query 'Stacks[0].Outputs[?OutputKey==`$(SAM_LOGS_FUNCTION_OUTPUT)`].OutputValue' --output text 2>/dev/null); \
	if [ -z "$$FUNC" ]; then \
	  FUNC=$$(aws cloudformation describe-stack-resources --stack-name "$(EFFECTIVE_STACK_NAME)" --query "StackResources[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId" --output text 2>/dev/null | tr '\t' '\n' | head -1); \
	fi; \
	if [ -z "$$FUNC" ]; then \
	  for NESTED in $$(aws cloudformation describe-stack-resources --stack-name "$(EFFECTIVE_STACK_NAME)" --query "StackResources[?ResourceType=='AWS::CloudFormation::Stack'].PhysicalResourceId" --output text 2>/dev/null); do \
	    FUNC=$$(aws cloudformation describe-stack-resources --stack-name "$$NESTED" --query "StackResources[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId" --output text 2>/dev/null | tr '\t' '\n' | head -1); \
	    [ -n "$$FUNC" ] && break; \
	  done; \
	fi; \
	if [ -z "$$FUNC" ]; then echo "No Lambda function found for stack $(EFFECTIVE_STACK_NAME)"; exit 1; fi; \
	START=$$(($$(date +%s) - $(SAM_LOGS_MINUTES) * 60))000
endef

SAM_LOGS_FUNCTION_OUTPUT ?= LambdaWebFunction

# Last N Lambda CloudWatch log events. Resolves function from Outputs or nested stack (SAM deploys Lambda in child stack).
# Note: filter-log-events returns oldest-first; we request more than LIMIT then keep only the newest LIMIT so recent
# activity (e.g. EventBridge-triggered runs) is included. Request 5x limit so that after tail we have the most recent N.
sam-logs: sam-config-check
	@$(SAM_LOGS_RESOLVE); \
	REQ=$$(( $(SAM_LOGS_LIMIT) * 5 )); \
	echo "Last $(SAM_LOGS_LIMIT) log events (past $(SAM_LOGS_MINUTES) min) for /aws/lambda/$$FUNC (stack=$(EFFECTIVE_STACK_NAME))..."; \
	aws logs filter-log-events --log-group-name "/aws/lambda/$$FUNC" --start-time "$$START" --limit $$REQ --output text 2>/dev/null | tail -n $(SAM_LOGS_LIMIT) || true

# Same as sam-logs but output only timestamp (ISO) and message (no event IDs, no extra columns).
# Optional: make sam-logs-simple SAM_LOGS_TAIL=1 to stream (same as sam-logs-simple-tail).
sam-logs-simple: sam-config-check
	@$(SAM_LOGS_RESOLVE); \
	if [ -n "$(SAM_LOGS_TAIL)" ]; then \
	  (aws logs tail "/aws/lambda/$$FUNC" --follow --format short $(SAM_LOGS_OPTIONS) || true) ; \
	else \
	  REQ=$$(( $(SAM_LOGS_LIMIT) * 5 )); \
	  aws logs filter-log-events --log-group-name "/aws/lambda/$$FUNC" --start-time "$$START" --limit $$REQ $(SAM_LOGS_OPTIONS) \
	    --query 'events[].[timestamp,message]' --output text 2>/dev/null | tail -n $(SAM_LOGS_LIMIT) | while IFS=$$'\t' read -r ts msg; do \
	    [ -n "$$ts" ] && printf '%s\t%s\n' "$$(uv run python -c "import datetime; print(datetime.datetime.fromtimestamp($$ts/1000).strftime('%Y-%m-%d %H:%M:%S'))")" "$$msg"; \
	  done || true; \
	fi

# Stream Lambda logs (timestamp + message). Sets SAM_LOGS_TAIL=1 and invokes sam-logs-simple.
sam-logs-simple-tail:
	$(MAKE) sam-logs-simple SAM_LOGS_TAIL=1

sam-logs-web:
	$(MAKE) sam-logs SAM_LOGS_FUNCTION_OUTPUT=LambdaWebFunction

sam-logs-resize:
	$(MAKE) sam-logs SAM_LOGS_FUNCTION_OUTPUT=LambdaResizeFunction

sam-logs-web-tail:
	$(MAKE) sam-logs-simple SAM_LOGS_FUNCTION_OUTPUT=LambdaWebFunction SAM_LOGS_TAIL=1

sam-logs-resize-tail:
	$(MAKE) sam-logs-simple SAM_LOGS_FUNCTION_OUTPUT=LambdaResizeFunction SAM_LOGS_TAIL=1

# Lambda log events for EventBridge-pushed asynchronous movie work.
# Use this when sam-logs is dominated by HTTP traffic.
async-work-logs: SAM_LOGS_FUNCTION_OUTPUT=LambdaResizeFunction
async-work-logs:
	@$(SAM_LOGS_RESOLVE); \
	echo "Async-work log events (past $(SAM_LOGS_MINUTES) min, limit $(SAM_LOGS_LIMIT)) for /aws/lambda/$$FUNC (stack=$(EFFECTIVE_STACK_NAME))..."; \
	aws logs filter-log-events --log-group-name "/aws/lambda/$$FUNC" --start-time "$$START" --limit $(SAM_LOGS_LIMIT) --filter-pattern '"async work"' --output text || true

# Stream Lambda logs, showing only asynchronous-work lines.
async-work-logs-tail: SAM_LOGS_FUNCTION_OUTPUT=LambdaResizeFunction
async-work-logs-tail:
	@$(SAM_LOGS_RESOLVE); \
	echo "Tailing async-work logs for /aws/lambda/$$FUNC (Ctrl-C to stop)..."; \
	aws logs tail "/aws/lambda/$$FUNC" --follow --format short --filter-pattern '"async work"' || true

sam-delete:
	@echo Deletion will begin in 10 seconds. Press Ctrl-C to cancel.
	sleep 10
	@echo "Deleting stack: $(EFFECTIVE_STACK_NAME)..."
	sam delete --stack-name "$(EFFECTIVE_STACK_NAME)" --no-prompts
	@echo "Waiting for deletion to complete..."
	aws cloudformation wait stack-delete-complete --stack-name "$(EFFECTIVE_STACK_NAME)"
	@echo "Stack $(EFFECTIVE_STACK_NAME) deleted successfully."

ssh:
	@echo "ssh is not available for Lambda-only SAM stacks."
	@exit 1

sam-reload:
	@echo "sam-reload is not available for Lambda-only SAM stacks. Use sam-build and sam-deploy."
	@exit 1

list-all-instances:
	for r in us-east-1 us-east-2 ; do echo ; echo "=== ZONE $$r ===" ; AWS_REGION=$$r aws ec2 describe-instances | etc/ifmt ; done

list-stacks:
	aws cloudformation list-stacks \
		--stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE ROLLBACK_COMPLETE \
		--query 'StackSummaries[*].[StackName, StackStatus, CreationTime, Region]' \
		--output table



################################################################
### Compile JavaScript to TypeScript

%.js: %.ts
	tsc $<
