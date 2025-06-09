# Makefile for Planttracer web application
# - Creates CI/CD environment in GitHub
# - Manages deployemnt to AWS Linux
# - Updated to handle virtual environment
# - Simple CRUD management of local database instance for developers

PYLINT_THRESHOLD=9.5
TS_FILES := $(wildcard *.ts */*.ts)
JS_FILES := $(TS_FILES:.ts=.js)

################################################################
# Create the virtual enviornment for testing and CI/CD
REQ = venv/pyvenv.cfg
PYTHON=venv/bin/python
PIP_INSTALL=venv/bin/pip install --no-warn-script-location
ROOT_ETC=etc
DEPLOY_ETC=deploy/etc
APP_ETC=$(DEPLOY_ETC)
DBMAINT=dbutil.py

venv:
	@echo install venv for the development environment
	python3 -m venv venv
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements.txt ]; then $(PIP_INSTALL) -r requirements.txt ; fi
	if [ -r deploy/requirements.txt ]; then $(PIP_INSTALL) -r deploy/requirements.txt ; fi
	if [ -r tests/requirements.txt ]; then $(PIP_INSTALL) -r tests/requirements.txt ; fi
	if [ -r docs/requirements.txt ]; then $(PIP_INSTALL) -r docs/requirements.txt ; fi

$(REQ):
	make venv

.PHONY: venv


################################################################
# SAM Commands - for deploying on AWS Lambda

sam-deploy:
	sam validate
	DOCKER_DEFAULT_PLATFORM=linux/arm64 sam build
	sam deploy --no-confirm-changeset
	sam logs --tail


################################################################
#
# By default, PYLINT generates an error if your code does not rank 10.0.
# This makes us tolerant of minor problems.

all:
	@echo verify syntax and then restart
	make pylint

check:
	make pylint
	make pytest

################################################################
## Program testing
##
## Static Analysis

PYLINT_OPTS:=--output-format=parseable --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose
pylint: $(REQ)
	$(PYTHON) -m pylint $(PYLINT_OPTS) deploy tests *.py


pylint-tests: $(REQ)
	$(PYTHON) -m pylint $(PYLINT_OPTS) --init-hook="import sys;sys.path.append('tests');import conftest" tests

mypy:
	mypy --show-error-codes --pretty --ignore-missing-imports --strict .

black:
	black --line-length 127 .

black-check:
	black --line-length 127 . --check
	@echo "If this fails, simply run: make black"

isort:
	isort . --profile=black

isort-check:
	isort --check . --profile=black

flake:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 . --count --exit-zero --max-complexity=55 --max-line-length=127 --statistics --ignore F403,F405,E203,E231,E252,W503

localmail-config:
	if [ -z "$${PLANTTRACER_CREDENTIALS}" ]; then echo PLANTTRACER_CREDENTIALS is not set; exit 1; fi
	grep -q '\[smtp\]' $${PLANTTRACER_CREDENTIALS} || cat tests/etc/localmail.ini-stub >> $${PLANTTRACER_CREDENTIALS}

################################################################
##
## Dynamic Analysis
## If you are testing just one thing, put it here!
#
# In the tests below, we always test the database connectivity first
# It makes no sense to run the tests otherwise


# Set these during development to speed testing of the one function you care about:
TEST1MODULE=tests/movie_tracker_test.py
TEST1FUNCTION="-k test_movie_tracking"
pytest1:
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=DEBUG --maxfail=1 $(TEST1MODULE) $(TEST1FUNCTION)

pytest:  $(REQ) localmail-config
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=INFO .

pytest-selenium:
	$(PYTHON) -m pytest -v --log-cli-level=INFO tests/sitetitle_test.py

pytest-debug: localmail-config
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=DEBUG

pytest-app-framework:
	@echo validate app framework
	$(PYTHON) -m pytest -x --log-cli-level=DEBUG tests/app_test.py -k test_templates

pytest-quiet: localmail-config
	@echo quietly make pytest and stop at the firt error
	$(PYTHON) -m pytest --log-cli-level=ERROR tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest --log-cli-level=ERROR

pytest-coverage: $(REQ) localmail-config
	$(PIP_INSTALL) codecov pytest pytest_cov
	$(PYTHON) -m pytest -v --cov=. --cov-report=xml tests

################################################################
### Debug targets run running locally

run-local:
	@echo run bottle locally, storing new data in database
	$(PYTHON) standalone.py --storelocal

run-local-demo:
	@echo run bottle locally in demo mode, using local database
	DEMO_MODE=1 $(PYTHON) standalone.py --storelocal

DEBUG:=$(PYTHON) standalone.py --loglevel DEBUG
debug:
	make debug-local

debug-local:
	@echo run bottle locally in debug mode, storing new data in database
	$(DEBUG) --storelocal

debug-single:
	@echo run bottle locally in debug mode single-threaded
	$(DEBUG)

debug-multi:
	@echo run bottle locally in debug mode multi-threaded
	$(DEBUG) --multi

debug-dev:
	@echo run bottle locally in debug mode, storing new data in S3, with the dev.planttracer.com database
	@echo for debugging Python and Javascript with remote database
	$(DEBUG)

debug-dev-api:
	@echo Debug local JavaScript with remote server.
	@echo run bottle locally in debug mode, storing new data in S3, with the dev.planttracer.com database and API calls
	PLANTTRACER_API_BASE=https://dev.planttracer.com/ $(DEBUG)

tracker-debug:
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
# Installations are used by the CI pipeline and by local developers
# $(REQ) gets made by the virtual environment installer, but you need to have python installed first.
# See https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html for info about DynamoDB (local version)

## DynamoDB Local (Provided by AWS)
.PHONY: install_local_dynamodb
DDBL_DOWNLOAD_URL:=https://d1ni2b6xgvw0s0.cloudfront.net/v2.x/dynamodb_local_latest.zip
install_local_dynamodb: $(REQ)
	test -f dynamodb_local_latest.zip || curl $(DDBL_DOWNLOAD_URL) -o dynamodb_local_latest.zip
	test -f dynamodb_local_latest.zip || (echo could not download $(DDBL_DOWNLOAD_URL); exit 1)
	unzip -uq dynamodb_local_latest.zip DynamoDBLocal.jar 'DynamoDBLocal_lib/*'

run_local_dynamodb:
	bash local_dynamodb_control.bash start

stop_local_dynamodb:
	bash local_dynamodb_control.bash stop

remove_localdb:
	@echo Removing local database using $(ROOT_ETC)/github_actions_mysql_rootconfig.ini
	$(PYTHON) $(DBMAINT) --rootconfig $(ROOT_ETC)/github_actions_mysql_rootconfig.ini --dropdb $(PLANTTRACER_LOCALDB_NAME)

list_tables:
	aws dynamodb list-tables --endpoint-url http://localhost:8010

## S3 Local (Minio)
install-profile:
	echo "[minio]" >> $HOME/.aws/credentials
	echo "aws_access_key_id = admin" >> $HOME/.aws/credentials
	echo "aws_secret_access_key = password" >> $HOME/.aws/credentials

list-local-buckets:
	aws s3 --profile=minio --endpoint-url http://localhost:9000 ls

make-local-bucket:
	aws s3 --profile=minio --endpoint-url http://localhost:9000 mb s3://planttracer-local/


################################################################

install-chromium-browser-ubuntu: $(REQ)
	sudo apt-get install -y chromium-browser
	chromium --version

install-chromium-browser-macos: $(REQ)
	brew install chromium --no-quarantine

# Includes ubuntu dependencies
install-ubuntu: $(REQ)
	echo on GitHub, we use this action instead: https://github.com/marketplace/actions/setup-ffmpeg
	which ffmpeg || sudo apt install ffmpeg
	which node || sudo apt-get install nodejs
	which npm || sudo apt-get install npm
	npm ci
	if [ -r requirements-ubuntu.txt ]; then $(PIP_INSTALL) -r requirements-ubuntu.txt ; fi

# Install for AWS Linux for running SAM
# Start with:
# sudo dfn install git && git clone --recursive https://github.com/Plant-Tracer/webapp && (cd webapp; make aws-install)
install-aws:
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

# Includes MacOS dependencies managed through Brew
install-macos:
	brew update
	brew upgrade
	brew install python3
	brew install ffmpeg
	brew install node
	brew install npm
	npm ci
	npm install -g typescript webpack webpack-cli
	make $(REQ)
	if [ -r requirements-macos.txt ]; then $(PIP_INSTALL) -r requirements-macos.txt ; fi

# Includes Windows dependencies
# restart the shell after installs are done
# choco install as administrator
install-windows: $(REQ)
	choco install -y make
	choco install -y ffmpeg
	choco install -y nodejs
	npm ci
	npm install -g typescript webpack webpack-cli
	make $(REQ)
	if [ -r requirements-windows.txt ]; then $(PIP_INSTALL) -r requirements-windows.txt ; fi

################################################################
### Cleanup

clean:
	find . -name '*~' -exec rm {} \;
	/bin/rm -rf __pycache__ */__pycache__

################################################################
### Compile JavaScript to TypeScript

%.js: %.ts
	tsc $<
