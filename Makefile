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

PYLINT_THRESHOLD := 9.5
TS_FILES := $(wildcard *.ts */*.ts)
JS_FILES := $(TS_FILES:.ts=.js)

# all of the tests below require a virtual python environment, LambdaDBLocal and the minio s3 emulator
# See below for the rules

REQ := venv/pyvenv.cfg bin/DynamoDBLocal.jar bin/minio
LOCAL_BUCKET := planttracer-local
LOCAL_HTTP_PORT := 8080
DYNAMODB_LOCAL_ENDPOINT=http://localhost:8010/
MINIO_ENDPOINT := http://localhost:9100/

AWS_ENDPOINT_URL_S3=$(MINIO_ENDPOINT)
AWS_ENDPOINT_URL_DYNAMODB=$(DYNAMODB_LOCAL_ENDPOINT)
AWS_ACCESS_KEY_ID := minioadmin
AWS_SECRET_ACCESS_KEY := minioadmin
AWS_DEFAULT_REGION=us-east-1
MINIO_VARS := AWS_ACCESS_KEY_ID=minioadmin AWS_SECRET_ACCESS_KEY=minioadmin AWS_ENDPOINT_URL_S3=$(MINIO_ENDPOINT)
DYNAMODB_VARS := AWS_ENDPOINT_URL_DYNAMODB=$(DYNAMODB_LOCAL_ENDPOINT) AWS_DEFAULT_REGION=$(AWS_DEFAULT_REGION)
LOCAL_VARS := $(MINIO_VARS) $(DYNAMODB_VARS) PLANTTRACER_S3_BUCKET=$(LOCAL_BUCKET)

################################################################
# Create the virtual enviornment for testing and CI/CD

PYTHON=venv/bin/python
PIP_INSTALL=venv/bin/pip install --no-warn-script-location
DEPLOY_ETC=deploy/etc
APP_ETC=$(DEPLOY_ETC)
DBMAINT=dbutil.py

venv/pyvenv.cfg:
	@echo install venv for the development environment
	python3 -m venv venv
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements.txt ]; then $(PIP_INSTALL) -r requirements.txt ; fi
	if [ -r deploy/requirements.txt ]; then $(PIP_INSTALL) -r deploy/requirements.txt ; fi
	if [ -r tests/requirements.txt ]; then $(PIP_INSTALL) -r tests/requirements.txt ; fi
	if [ -r docs/requirements.txt ]; then $(PIP_INSTALL) -r docs/requirements.txt ; fi


################################################################
#
# By default, PYLINT generates an error if your code does not rank 10.0.
# This makes us tolerant of minor problems.

all:
	@echo verify syntax and then restart
	make pylint
	make run-local

check:
	make pylint
	make pytest

tags:
	etags deploy/app/*.py tests/*.py tests/fixtures/*.py deploy/app/static/*.js

################################################################
## Program development: static analysis tools
##

## Use this targt for static analysis of the python files used for deployment
PYLINT_OPTS:=--output-format=parseable --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose
pylint: $(REQ)
	$(PYTHON) -m pylint $(PYLINT_OPTS) deploy *.py

## Use this to also test the tests...
pylint-tests: $(REQ)
	$(PYTHON) -m pylint $(PYLINT_OPTS) --init-hook="import sys;sys.path.append('tests');import conftest" deploy tests

## Mypy static analysis
mypy:
	mypy --show-error-codes --pretty --ignore-missing-imports --strict deploy tests

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

pytest:  $(REQ)
	$(PYTHON) -m pytest -v --log-cli-level=INFO tests

pytest-debug: $(REQ)
	$(PYTHON) -m pytest -v --log-cli-level=DEBUG tests

pytest-coverage: $(REQ)
	$(PIP_INSTALL) codecov pytest pytest_cov
	$(PYTHON) -m pytest -v --cov=. --cov-report=xml --cov-report=html tests
	@echo covreage report in htmlcov/

# This doesn't work yet...
pytest-selenium:
	$(PYTHON) -m pytest -v --log-cli-level=INFO tests/sitetitle_test.py

# Set these during development to speed testing of the one function you care about:
TEST1MODULE=tests/movie_tracker_test.py
TEST1FUNCTION="-k test_movie_tracking"
pytest1:
	$(PYTHON) -m pytest -v --log-cli-level=DEBUG --maxfail=1 $(TEST1MODULE) $(TEST1FUNCTION)

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
	make make-local-bucket
	DYNAMODB_TABLE_PREFIX=demo- $(LOCAL_VARS) $(PYTHON) dbutil.py --createdb
	$(MINIO_VARS) aws s3 ls --recursive s3://$(LOCAL_BUCKET)

run-local-debug:
	@echo run bottle locally on the demo database, but allow editing.
	LOG_LEVEL=DEBUG $(LOCAL_VARS) DYNAMODB_TABLE_PREFIX=demo- $(PYTHON) dbutil.py --makelink demo@planttracer.com --planttracer_endpoint http://localhost:$(LOCAL_HTTP_PORT)
	LOG_DEVEL=DEBUG $(LOCAL_VARS) DYNAMODB_TABLE_PREFIX=demo- LOG_LEVEL=DEBUG venv/bin/flask --debug --app deploy.app.bottle_app:app run --port $(LOCAL_HTTP_PORT) --with-threads

run-local-demo-debug:
	@echo run bottle locally in demo mode, using local database and debug mode
	@echo connect to http://localhost:$(LOCAL_HTTP_PORT)
	LOG_LEVEL=DEBUG $(LOCAL_VARS)  DYNAMODB_TABLE_PREFIX=demo- DEMO_COURSE_ID=demo-course venv/bin/flask --debug --app deploy.app.bottle_app:app run --port $(LOCAL_HTTP_PORT) --with-threads

debug-dev-api:
	@echo Debug local JavaScript with remote server.
	@echo run bottle locally in debug mode, storing new data in S3, with the dev.planttracer.com database and API calls
	@echo This makes it easy to modify the JavaScript locally with the remote API support
	PLANTTRACER_API_BASE=https://dev.planttracer.com/ $(DEBUG)

tracker-debug:
	@echo just test the tracker...
	/bin/rm -f outfile.mp4
	$(PYTHON) tracker.py --moviefile="tests/data/2019-07-12 circumnutation.mp4" --outfile=outfile.mp4
	open outfile.mp4

################################################################
### JavaScript

eslint:
	if [ ! -d deploy/app/static ]; then echo no deploy/app/static ; exit 1 ; fi
	(cd deploy/app/static;make eslint)
	if [ ! -d deploy/app/templates ]; then echo no deploy/app/templates ; exit 1 ; fi
	(cd deploy/app/templates;make eslint)

jscoverage:
	NODE_PATH=deploy/app/static npm run coverage
	NODE_PATH=deploy/app/static npm test

jstest-debug:
	NODE_PATH=deploy/app/static npm run test-debug


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
	$(DYNAMODB_VARS) aws dynamodb list-tables

dump-demo-tables:
	for tn in "demo-api_keys" "demo-course_users" "demo-courses" "demo-logs" "demo-movie_frames" "demo-movies" "demo-unique_emails" "demo-users" ; do\
		echo $$tn:; \
		$(DYNAMODB_VARS) aws dynamodb describe-table --table-name $$tn ; \
		$(DYNAMODB_VARS) aws dynamodb scan --max-items 5 --table-name $$tn ; \
		done


################################################################
# Minio (S3 clone -- see: https://min.io/)
# Installations are used by the CI pipeline and by local developers

# installation:
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
		@echo Linux amd64 ; \
		curl $(LINUX_BASE)/minio -o bin/minio ; \
		curl $(LINUX_BASE_MC)/mc -o bin/mc ; \
	fi
	if [ "$$(uname -s)" = "Linux" ] && [ "$$(uname -m)" = "x86_64" ] ; then \
		@echo Linux x86_64 ; \
		curl $(LINUX_BASE)/minio -o bin/minio ; \
		curl $(LINUX_BASE_MC)/mc -o bin/mc ; \
	fi
	if [ "$$(uname -s)" = "Linux" ] && [ "$$(uname -m)" = "aarch64" ] ; then \
		@echo Linux aarch64 ; \
		curl $(LINUX_ARM_BASE)/minio -o bin/minio ; \
		curl $(LINUX_ARM_BASE_MC)/mc -o bin/mc ; \
	fi
	if [ "$$(uname -s)" = "Linux" ] && [ "$$(uname -m)" = "arm64" ] ; then \
		@echo Linux arm64 ; \
		curl $(LINUX_ARM_BASE)/minio -o bin/minio ; \
		curl $(LINUX_ARM_BASE_MC)/mc -o bin/mc ; \
	fi
	if [ "$$(uname -s)" = "Darwin" ] ; then \
		@echo Darwin ; \
		curl $(MACOS_BASE)/minio -o bin/minio ; \
		brew install minio/stable/mc ; \
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
	$(MINIO_VARS) aws s3 --endpoint-url $(MINIO_ENDPOINT) ls

make-local-bucket:
	if $(MINIO_VARS) aws s3 ls s3://$(LOCAL_BUCKET)/ >/dev/null 2>&1; then \
	 	echo $(LOCAL_BUCKET) exists ; \
	else \
		echo creating s3://$(LOCAL_BUCKET)/ ; \
		$(MINIO_VARS) aws s3 mb s3://$(LOCAL_BUCKET)/ ; \
	fi
	@echo local buckets:
	$(MINIO_VARS) aws s3 ls


################################################################
# Includes ubuntu dependencies
install-ubuntu:
	echo on GitHub, we use this action instead: https://github.com/marketplace/actions/setup-ffmpeg
	sudo apt-get update
	sudo apt install curl
	which ffmpeg || sudo apt install -y ffmpeg
	which node || sudo apt install -y nodejs
	which npm || sudo apt install -y npm
	which chromium || sudo apt-get install -y chromium-browser
	which lsof || sudo apt-get install -y lsof
	npm ci
	make $(REQ)
	if [ -r requirements-ubuntu.txt ]; then $(PIP_INSTALL) -r requirements-ubuntu.txt ; fi

# Includes MacOS dependencies managed through Brew
install-macos:
	brew update
	brew upgrade
	which python3 || brew install python3
	which ffmpeg || brew install ffmpeg
	which node || brew install node
	which npm || brew install npm
	which lsof || brew install lsof
	which chromium || brew install chromium --no-quarantine
	which aws || brew install awscli
	npm ci
	npm install -g typescript webpack webpack-cli
	make $(REQ)
	if [ -r requirements-macos.txt ]; then $(PIP_INSTALL) -r requirements-macos.txt ; fi

# Includes Windows dependencies
# restart the shell after installs are done
# choco install as administrator
# Note: development on windows is not currently supported
install-windows:
	choco install -y make
	choco install -y ffmpeg
	choco install -y nodejs
	choco install -y chromium
	npm ci
	npm install -g typescript webpack webpack-cli
	make $(REQ)
	if [ -r requirements-windows.txt ]; then $(PIP_INSTALL) -r requirements-windows.txt ; fi


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
	if [ -r requirements-aws.txt ]; then $(PIP_INSTALL) -r requirements-ubuntu.txt ; fi

sam-deploy:
	sam validate
	DOCKER_DEFAULT_PLATFORM=linux/arm64 sam build
	sam deploy --no-confirm-changeset
	sam logs --tail

################################################################
### Compile JavaScript to TypeScript

%.js: %.ts
	tsc $<
