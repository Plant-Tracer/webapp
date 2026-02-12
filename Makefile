# Makefile for Planttracer web application
# - Local development
# - Creates CI/CD environment in GitHub
# - Manages deployemnt to AWS Linux
# - Updated to handle virtual environment
# - Simple CRUD management of local database instance for developers
#
# Environment variables:
# PLANTTRACER_CREDENTIALS - the config.ini file that includes [smtp] and [imap] configuration the your production system
#

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

# all of the tests below require a virtual python environment, LambdaDBLocal and the minio s3 emulator
# See below for the rules

REQ := .venv/pyvenv.cfg

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
    $(warning DYNAMODB_TABLE_PREFIX not set. Defaulting to demo-)
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
	make pytest
	make jscoverage

coverage:
	make pytest-coverage
	make jscoverage

tags:
	etags src/app/*.py tests/*.py tests/fixtures/*.py src/app/static/*.js

################################################################
## Program development: static analysis tools
##

## Use this targt for static analysis of the python files used for deployment
PYLINT_OPTS:=--output-format=parseable --fail-under=$(PYLINT_THRESHOLD) --verbose
lint: $(REQ)
	make pylint
	make eslint

pylint:
	poetry run pylint  $(PYLINT_OPTS) src tests *.py

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
## Program development: dynamic analysis
##

## These tests now use fixtures that automatically create in-memory configurations and DynamoDB databases.
## No environment variables need to be set.
## set LOG_LEVEL at start of CLI to change the  log level

pytest: $(REQ)
	poetry run pytest -v --log-cli-level=$(LOG_LEVEL) tests

pytest-coverage: $(REQ)
	poetry run pytest -v --log-cli-level=$(LOG_LEVEL) --cov=. --cov-report=xml --cov-report=html tests
	@echo coverage report in htmlcov/

# This doesn't work yet...
pytest-selenium:
	poetry run pytest -v --log-cli-level=$(LOG_LEVEL) tests/sitetitle_test.py

# Set these during development to speed testing of the one function you care about:
TEST1MODULE=tests/test_trackpoint_drag.py
#TEST1FUNCTION="-k test_trackpoint_drag_and_database_update"
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
	LOG_LEVEL=$(LOG_LEVEL) poetry run python  $(DBUTIL) --makelink demo@planttracer.com --planttracer_endpoint http://localhost:$(LOCAL_HTTP_PORT)
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
install-ubuntu:
	@echo install-ubuntu
	sudo apt-get update
	which aws      || sudo snap install aws-cli --classic | cat # cat suppresses TTY junk
	which pipx     || sudo apt-get install -y -qq pipx
	pipx ensurepath
	pipx install poetry --force
	which chromium || sudo apt-get install -y -qq chromium-browser chromium-chromedriver
	which curl     || sudo apt-get install -y -qq curl
	which ffmpeg   || sudo apt-get install -y -qq ffmpeg
	which lsof     || sudo apt-get install -y -qq lsof
	which node     || sudo apt-get install -y -qq nodejs
	which npm      || sudo apt-get install -y -qq npm
	which zip      || sudo apt-get install -y -qq zip
	which java     || sudo apt-get install -y -qq openjdk-21-jre-headless
	npm ci
	make $(REQ)
	@echo install-ubuntu done



# Includes MacOS dependencies managed through Brew
install-macos:
	brew update
	which aws || brew install awscli
	which chromium || brew install chromium --no-quarantine
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


sam-deploy:
	printenv | grep AWS
ifeq ($(AWS_REGION),local)
	@echo cannot deploy to local. Please specify AWS_REGION.  && exit 1
endif
	@echo validate, build and deploy sam stack...
	@echo
	sam validate --lint
	AWS_REGION=us-east-1 poetry run cfn-lint template.yaml
	poetry export --only main,lambda --format=requirements.txt \
		--output lambda-resize/requirements.txt --without-hashes
	DOCKER_DEFAULT_PLATFORM=linux/arm64 sam build
	sam deploy --no-confirm-changeset


list-all-instances:
	@echo && echo && echo
	@unset AWS_ENDPOINT_URL_DYNAMODB AWS_SECRET_ACCESS_KEY AWS_ACCESS_KEY_ID AWS_ENDPOINT_URL_S3 && (printenv | grep AWS_) && \
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
