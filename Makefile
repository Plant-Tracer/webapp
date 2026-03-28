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

SHELL := /bin/bash
PYLINT_THRESHOLD := 10.0
TS_FILES := $(wildcard *.ts */*.ts)
JS_FILES := $(TS_FILES:.ts=.js)
LOCAL_BUCKET:=planttracer-local
LOCAL_HTTP_PORT=8080
LOG_LEVEL ?= DEBUG		# default to debug unless changed
DYNAMODB_LOCAL_ENDPOINT=http://localhost:8000/
MINIO_ENDPOINT=http://localhost:9000/
DBUTIL=src/dbutil.py
export DEBIAN_FRONTEND=noninteractive

SAM_CONFIG ?= samconfig.toml
STACK_NAME := $(shell grep "stack_name" $(SAM_CONFIG) 2>/dev/null | cut -d'=' -f2 | tr -d ' "')

# Only show events from the last N minutes (filter-log-events returns ascending order, so without this we get oldest events).
SAM_LOGS_LIMIT ?= 1000
SAM_LOGS_MINUTES ?= 15

# all of the tests below require a virtual python environment, LambdaDBLocal and the minio s3 emulator
# See below for the rules

REQ := .venv/pyvenv.cfg

# files used by lambda
VEND_FILES := src/app/odb.py \
              src/app/schema.py \
              src/app/constants.py \
              src/app/mp4_metadata_lib.py \
              src/app/paths.py \
              src/app/odb_movie_data.py \
              src/app/s3_presigned.py

# if AWS_REGION is set, we use the live system. Otherwise use minio and DynamoDBlocal
ifeq ($(AWS_REGION),)
    $(warning AWS_REGION is not set. Defaulting to local MinIO/DynamoDB configuration.)
    export AWS_REGION                ?= local
endif
ifeq ($(AWS_REGION),local)
    REQ := $(REQ) bin/DynamoDBLocal.jar bin/minio
    export AWS_ACCESS_KEY_ID         := minioadmin
    export AWS_SECRET_ACCESS_KEY     := minioadmin
    export AWS_ENDPOINT_URL_DYNAMODB := $(DYNAMODB_LOCAL_ENDPOINT)
    export AWS_ENDPOINT_URL_S3       := $(MINIO_ENDPOINT)
    export PLANTTRACER_S3_BUCKET=$(LOCAL_BUCKET)
endif

ifeq ($(DYNAMODB_TABLE_PREFIX),)
    $(info DYNAMODB_TABLE_PREFIX not set. Defaulting to demo-)
    export DYNAMODB_TABLE_PREFIX=demo-
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
.PHONY: all check coverage tags

all:
	@echo verify syntax and then restart
	make lint
	make run-local

check:
	make lint
	make start_local_minio start_local_dynamodb
	AWS_REGION=local make pytest
	make jscoverage

coverage:
	AWS_REGION=local make pytest-coverage
	AWS_REGION=local make jscoverage

tags:
	etags src/app/*.py tests/*.py tests/fixtures/*.py src/app/static/*.js lambda-resize/src/resize_app/*.py

################################################################
## Program development: static analysis tools
##

## Use this targt for static analysis of the python files used for deployment
PYLINT_OPTS:=--output-format=parseable --fail-under=$(PYLINT_THRESHOLD) --verbose
lint: $(REQ)
	make pylint
	make eslint

pylint:
	make vend-lambda-resize
	poetry run pylint $(PYLINT_OPTS) lambda-resize src tests  *.py

## Mypy static analysis
mypy:
	mypy --show-error-codes --pretty --ignore-missing-imports --strict src tests

## black static analysis
black:
	black --line-length 127 .

black-check:
	black --line-length 127 . --check
	@echo "If this fails, simply run: make black"

## isort
isort:
	isort . --profile=black

isort-check:
	isort --check . --profile=black

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
## PYTHONPATH includes lambda-resize/src so tests that use resize_app (tracker, lambda_tracking_handler) can load it.
## Set LOG_LEVEL at start of CLI to change the log level.

pytest: $(REQ)
	make vend-lambda-resize
	PYTHONPATH=lambda-resize/src:$$PYTHONPATH poetry run pytest -vv --log-cli-level=$(LOG_LEVEL) tests lambda-resize/tests

pytest-coverage: $(REQ)
	make vend-lambda-resize
	PYTHONPATH=lambda-resize/src:$$PYTHONPATH poetry run pytest -vv --log-cli-level=$(LOG_LEVEL) --cov=. --cov-report=xml --cov-report=html tests lambda-resize/tests
	@echo coverage report in htmlcov/

# This doesn't work yet...
pytest-selenium:
	poetry run pytest -v --log-cli-level=$(LOG_LEVEL) tests/sitetitle_test.py

# Set these during development to speed testing of the one function you care about:
TEST1MODULE=tests/endpoint_test.py
#TEST1FUNCTION="-k test_ver1"
pytest1:
	poetry run pytest -v --log-cli-level=$(LOG_LEVEL) --maxfail=1 $(TEST1MODULE) $(TEST1FUNCTION)

################################################################
### Debug targets to develop and run locally.

wipe-local:
	@echo wiping all local artifacts and remaking the local bucket.
	bin/local_minio_control.bash stop
	bin/local_dynamodb_control.bash stop
	/bin/rm -rf var
	mkdir -p var
	bin/local_minio_control.bash start
	bin/local_dynamodb_control.bash start
	make make-local-bucket

delete-local:
	@echo deleting all local artifacts
	bin/local_minio_control.bash stop
	bin/local_dynamodb_control.bash stop
	/bin/rm -rf var

make-local-demo:
	@echo creating a local course called demo-course with the prefix demo-
	@echo assumes miniodb and dynamodb are running and the make-local-bucket already ran
	poetry run python $(DBUTIL) --createdb
	aws s3 ls --recursive s3://$(LOCAL_BUCKET)

run-local-debug:
	@echo run bottle locally on the demo database, but allow editing.
	LOG_LEVEL=$(LOG_LEVEL) poetry run python  $(DBUTIL) --makelink demouser@planttracer.com --planttracer_endpoint http://localhost:$(LOCAL_HTTP_PORT)
	LOG_LEVEL=$(LOG_LEVEL) poetry run flask  --debug --app src.app.flask_app:app run --port $(LOCAL_HTTP_PORT) --with-threads

run-local-demo-debug:
	@echo run bottle locally in demo mode, using local database and debug mode
	@echo connect to http://localhost:$(LOCAL_HTTP_PORT)
	LOG_LEVEL=$(LOG_LEVEL) DEMO_COURSE_ID=demo-course poetry run flask --debug --app src.app.flask_app:app run --port $(LOCAL_HTTP_PORT) --with-threads


debug-dev-api:
	@echo Debug local JavaScript with remote server.
	@echo run bottle locally in debug mode, storing new data in S3, with the dev.planttracer.com database and API calls
	@echo This makes it easy to modify the JavaScript locally with the remote API support
	@echo And we should not require any of the variables -but we enable them just in case
	PLANTTRACER_API_BASE=https://dev.planttracer.com/ LOG_LEVEL=$(LOG_LEVEL)  poetry run flask --debug --app src.app.flask_app:app run --port $(LOCAL_HTTP_PORT) --with-threads

tracker-debug:
	@echo just test the tracker...
	/bin/rm -f outfile.mp4
	poetry run python tracker.py --moviefile="tests/data/2019-07-12 circumnutation.mp4" --outfile=outfile.mp4
	open outfile.mp4

.PHONY: wipe-local delete-local make-local-demorun-local-debug run-local-demo-debug debut-dev-api tracker-debug

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
		poetry run python -c "from tests.js_coverage_utils import convert_browser_coverage_to_xml; from pathlib import Path; convert_browser_coverage_to_xml(Path('coverage/browser-coverage.json'), Path('coverage/browser-coverage.xml'))"; \
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
	bash bin/local_dynamodb_control.bash start

stop_local_dynamodb:  bin/DynamoDBLocal.jar
	bash bin/local_dynamodb_control.bash stop

list-tables:
	aws dynamodb list-tables

dump-demo-tables:
	for tn in "demo-api_keys" "demo-course_users" "demo-courses" "demo-logs" "demo-movie_frames" "demo-movies" "demo-unique_emails" "demo-users" ; do\
		echo $$tn:; \
		aws dynamodb describe-table --table-name $$tn ; \
		aws dynamodb scan --max-items 5 --table-name $$tn ; \
		done


.PHONY: start_local_dynamodb stop_local_dynamodb list-tables dump-demo-tables
################################################################
# Minio (S3 clone -- see: https://min.io/)
# Installations are used by the CI pipeline and by local developers

# Sources:
LINUX_BASE=https://dl.min.io/server/minio/release/linux-amd64
LINUX_BASE_MC=https://dl.min.io/client/mc/release/linux-amd64/
LINUX_ARM_BASE=https://dl.min.io/server/minio/release/linux-arm64
LINUX_ARM_BASE_MC=https://dl.min.io/client/mc/release/linux-arm64/
MACOS_BASE=https://dl.min.io/server/minio/release/darwin-arm64
bin/minio:
	@echo downloading and installing minio
	mkdir -p bin
	uname -a
	if [ "$$(uname -s)" = "Linux" ] && [ "$$(uname -m)" = "amd64" ] ; then \
		echo Linux amd64 ; curl $(LINUX_BASE)/minio -o bin/minio ; curl $(LINUX_BASE_MC)/mc -o bin/mc ; \
	elif [ "$$(uname -s)" = "Linux" ] && [ "$$(uname -m)" = "x86_64" ] ; then \
		echo Linux x86_64 ; curl $(LINUX_BASE)/minio -o bin/minio ; curl $(LINUX_BASE_MC)/mc -o bin/mc ; \
	elif [ "$$(uname -s)" = "Linux" ] && [ "$$(uname -m)" = "aarch64" ] ; then \
		echo Linux aarch64 ; curl $(LINUX_ARM_BASE)/minio -o bin/minio ; curl $(LINUX_ARM_BASE_MC)/mc -o bin/mc ; \
	elif [ "$$(uname -s)" = "Linux" ] && [ "$$(uname -m)" = "arm64" ] ; then \
		echo Linux arm64 ; curl $(LINUX_ARM_BASE)/minio -o bin/minio ; curl $(LINUX_ARM_BASE_MC)/mc -o bin/mc ; \
	elif [ "$$(uname -s)" = "Darwin" ] ; then echo Darwin ; curl $(MACOS_BASE)/minio -o bin/minio ; brew install minio/stable/mc ; \
	else \
		echo unknown os/architecture; exit 1; \
	fi
	chmod +x bin/minio
	ls -l bin/minio
	if [ "$$(uname -s)" = "Linux" ] ; then \
		chmod +x bin/mc ; \
		ls -l bin/mc ; \
	fi

# operation:
start_local_minio: bin/minio
	bash bin/local_minio_control.bash start

stop_local_minio:  bin/minio
	bash bin/local_minio_control.bash stop

list-local-buckets:
	$(AWS_VARS) aws s3 ls

make-local-bucket:
	if $(AWS_VARS) aws s3 ls s3://$(LOCAL_BUCKET)/ >/dev/null 2>&1; then \
	 	echo $(LOCAL_BUCKET) exists ; \
	else \
		echo creating s3://$(LOCAL_BUCKET)/ ; \
		$(AWS_VARS) aws s3 mb s3://$(LOCAL_BUCKET)/ ; \
	fi
	echo local buckets:
	$(AWS_VARS) aws s3 ls

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
	which npm      || sudo apt-get install -y -qq npm
	which zip      || sudo apt-get install -y -qq zip
	which java     || sudo apt-get install -y -qq openjdk-21-jre-headless
	@# npm deprecation warnings (WARN deprecated) from transitive deps can be ignored
	npm ci
	make $(REQ)
	@echo install-ubuntu done



# Includes MacOS dependencies managed through Brew
install-macos:
	brew update
	which aws || brew install awscli
	which chromium || brew install chromium
	which ffmpeg || brew install ffmpeg
	which lsof || brew install lsof
	which node || brew install node
	which npm || brew install npm
	which poetry || brew install poetry
	which python3 || brew install python3
	npm ci
	npm install -g typescript webpack webpack-cli
	make $(REQ)

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
	make $(REQ)


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

# Install lambda group so root venv can run lambda-resize lint/tests (single pyproject).
install-lambda-deps: $(REQ)
	poetry install --with lambda

# lambda-resize: lint and test from root using root venv (deps from pyproject group lambda).
# install-lambda-deps ensures av (and other lambda deps) are in the venv so pylint can import them.
lambda-resize-lint: install-lambda-deps
	make vend-lambda-resize
	poetry run ruff check --fix lambda-resize/src
	PYTHONPATH=lambda-resize/src poetry run pylint lambda-resize/src

lambda-resize-check: lambda-resize-lint
	PYTHONPATH=lambda-resize/src poetry run pytest lambda-resize/tests -q --cov=lambda-resize/src --cov-report=term -o junit_family=legacy --log-cli-level=DEBUG

.PHONY: lambda-resize/src/requirements.txt
lambda-resize/src/requirements.txt:
	poetry export --with lambda --without dev --without vm --format=requirements.txt --output lambda-resize/src/requirements.txt --without-hashes

sam-build: $(REQ)
	@# Refuse to build if there are local changes or unpushed commits.
	@if ! git diff --quiet || ! git diff --cached --quiet; then \
	  echo "Refusing to run sam-build: uncommitted changes present (stash/commit first)."; \
	  exit 1; \
	fi
	@UPSTREAM=$$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || true); \
	if [ -z "$$UPSTREAM" ]; then \
	  echo "Refusing to run sam-build: current branch has no upstream (push and set upstream first)."; \
	  exit 1; \
	fi; \
	make lambda-resize/src/requirements.txt
	make vend-lambda-resize
	poetry run pylint $(PYLINT_OPTS) lambda-resize/src
	poetry check
	poetry lock
	printenv | grep AWS
	finch vm start || echo AWS finch is already running
	sam validate --lint
	@echo cfn-lint requires a valid AWS_REGION so we use us-east-1
	AWS_REGION=us-east-1 poetry run cfn-lint template.yaml
	DOCKER_DEFAULT_PLATFORM=linux/arm64 sam build --use-container --parallel
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

sam-deploy: $(REQ)
ifeq ($(AWS_REGION),local)
	@echo cannot deploy to local. Please specify AWS_REGION.  && exit 1
endif
	aws sts get-caller-identity --no-cli-pager
	sam deploy --no-confirm-changeset --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM
	poetry run sam-config-tool --samconfig $(SAM_CONFIG) ssh-clean
	$(MAKE) sam-status

sam-deploy-guided: $(REQ)
ifeq ($(AWS_REGION),local)
	@echo cannot deploy to local. Please specify AWS_REGION.  && exit 1
endif
	aws sts get-caller-identity --no-cli-pager
	@echo ===============================
	@echo use one of these keypairs:
	aws ec2 describe-key-pairs --output json | jq -r '.KeyPairs.[].KeyName'
	@echo ===============================
	@echo use one of these S3 buckets:
	aws s3 ls
	@echo ===============================
	@echo use one of these git branches:
	git branch -v
	sam deploy --guided --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM
	poetry run sam-config-tool --samconfig $(SAM_CONFIG) ssh-clean
	$(MAKE) sam-status


# After deploy: verify Lambda status URL returns 200. Use curl -s (no -f) so we capture and show body on 4xx/5xx.
sam-status:
	@echo "Checking Lambda status..."
	@sleep 5; \
	DNS=$$(aws cloudformation describe-stacks --stack-name $(STACK_NAME) --query 'Stacks[0].Outputs[?OutputKey==`LambdaDnsName`].OutputValue' --output text 2>/dev/null); \
	URL="https://$$DNS/resize-api/v1/ping"; \
	RESP=$$(curl -s -w "\n%{http_code}" "$$URL" 2>/dev/null); \
	CODE=$$(echo "$$RESP" | tail -1); \
	BODY=$$(echo "$$RESP" | sed '$$d'); \
	VERS=$$(printf "%s" "$$BODY" | python -c 'import sys, json; \ntry:\n d=json.load(sys.stdin); v=d.get("status_version");\n print(v if v is not None else "")\nexcept Exception:\n print("")' 2>/dev/null); \
	if echo "$$BODY" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then \
	  echo "Lambda status: operational ($$URL)"; \
	else \
	  echo "Lambda status: FAIL (HTTP $$CODE) ($$URL)"; echo "  response: $$BODY"; \
	fi; \
	if [ -n "$$VERS" ]; then echo "Status version: $$VERS"; fi; \
	echo ""; \
	echo "Recent Lambda log events (newest first) for troubleshooting:"; \
	$(MAKE) sam-logs SAM_LOGS_LIMIT=40 || true; \


# Shared resolution of Lambda function name (FUNC) and start time (START) for log targets.
# Used by sam-logs, sam-logs-simple, sam-logs-simple-tail.
define SAM_LOGS_RESOLVE
	FUNC=$$(aws cloudformation describe-stacks --stack-name $(STACK_NAME) --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunction`].OutputValue' --output text 2>/dev/null); \
	if [ -z "$$FUNC" ]; then \
	  FUNC=$$(aws cloudformation describe-stack-resources --stack-name $(STACK_NAME) --query "StackResources[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId" --output text 2>/dev/null | tr '\t' '\n' | head -1); \
	fi; \
	if [ -z "$$FUNC" ]; then \
	  for NESTED in $$(aws cloudformation describe-stack-resources --stack-name $(STACK_NAME) --query "StackResources[?ResourceType=='AWS::CloudFormation::Stack'].PhysicalResourceId" --output text 2>/dev/null); do \
	    FUNC=$$(aws cloudformation describe-stack-resources --stack-name "$$NESTED" --query "StackResources[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId" --output text 2>/dev/null | tr '\t' '\n' | head -1); \
	    [ -n "$$FUNC" ] && break; \
	  done; \
	fi; \
	if [ -z "$$FUNC" ]; then echo "No Lambda function found for stack $(STACK_NAME)"; exit 1; fi; \
	START=$$(($$(date +%s) - $(SAM_LOGS_MINUTES) * 60))000
endef

# Last N Lambda CloudWatch log events. Resolves function from Outputs or nested stack (SAM deploys Lambda in child stack).
# Note: filter-log-events returns oldest-first; we request more than LIMIT then keep only the newest LIMIT so recent
# activity (e.g. SQS-triggered runs) is included. Request 5x limit so that after tail we have the most recent N.
sam-logs:
	@$(SAM_LOGS_RESOLVE); \
	REQ=$$(( $(SAM_LOGS_LIMIT) * 5 )); \
	echo "Last $(SAM_LOGS_LIMIT) log events (past $(SAM_LOGS_MINUTES) min) for /aws/lambda/$$FUNC (stack=$(STACK_NAME))..."; \
	aws logs filter-log-events --log-group-name "/aws/lambda/$$FUNC" --start-time "$$START" --limit $$REQ --output text 2>/dev/null | tail -n $(SAM_LOGS_LIMIT) || true

# Same as sam-logs but output only timestamp (ISO) and message (no event IDs, no extra columns).
# Optional: make sam-logs-simple SAM_LOGS_TAIL=1 to stream (same as sam-logs-simple-tail).
sam-logs-simple:
	@$(SAM_LOGS_RESOLVE); \
	if [ -n "$(SAM_LOGS_TAIL)" ]; then \
	  (aws logs tail "/aws/lambda/$$FUNC" --follow --format short $(SAM_LOGS_OPTIONS) || true) ; \
	else \
	  REQ=$$(( $(SAM_LOGS_LIMIT) * 5 )); \
	  aws logs filter-log-events --log-group-name "/aws/lambda/$$FUNC" --start-time "$$START" --limit $$REQ $(SAM_LOGS_OPTIONS) \
	    --query 'events[].[timestamp,message]' --output text 2>/dev/null | tail -n $(SAM_LOGS_LIMIT) | while IFS=$$'\t' read -r ts msg; do \
	    [ -n "$$ts" ] && printf '%s\t%s\n' "$$(python3 -c "import datetime; print(datetime.datetime.fromtimestamp($$ts/1000).strftime('%Y-%m-%d %H:%M:%S'))")" "$$msg"; \
	  done || true; \
	fi

# Stream Lambda logs (timestamp + message). Sets SAM_LOGS_TAIL=1 and invokes sam-logs-simple.
sam-logs-simple-tail:
	$(MAKE) sam-logs-simple SAM_LOGS_TAIL=1

# Lambda log events that mention SQS (SQS-triggered invocations and sqs_handler messages).
# Use this when sam-logs is dominated by HTTP traffic and you want only tracking-queue activity.
sqs-logs:
	@$(SAM_LOGS_RESOLVE); \
	echo "SQS-related log events (past $(SAM_LOGS_MINUTES) min, limit $(SAM_LOGS_LIMIT)) for /aws/lambda/$$FUNC (stack=$(STACK_NAME))..."; \
	aws logs filter-log-events --log-group-name "/aws/lambda/$$FUNC" --start-time "$$START" --limit $(SAM_LOGS_LIMIT) --filter-pattern "SQS" --output text || true

# Stream Lambda logs, showing only lines that contain SQS.
sqs-logs-tail:
	@$(SAM_LOGS_RESOLVE); \
	echo "Tailing SQS-related logs for /aws/lambda/$$FUNC (Ctrl-C to stop)..."; \
	aws logs tail "/aws/lambda/$$FUNC" --follow --format short --filter-pattern "SQS" || true

sam-delete:
	@echo Deletion will begin in 10 seconds. Press Ctrl-C to cancel.
	sleep 10
	@echo "Deleting stack: $(STACK_NAME)..."
	sam delete --stack-name $(STACK_NAME) --no-prompts
	@echo "Waiting for deletion to complete..."
	aws cloudformation wait stack-delete-complete --stack-name $(STACK_NAME)
	@echo "Stack $(STACK_NAME) deleted successfully."

# Clever SSH via SSM (No SSH keys or port 22 required)
ssh:
	poetry run sam-config-tool --samconfig $(SAM_CONFIG) ssh

sam-reload:
	@echo reload the VM
	ssh ubuntu@$(STACK_NAME).planttracer.com -i $$HOME/.ssh/plantadmin.pem 'cd /opt/webapp;git pull; sudo systemctl restart planttracer'

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
