# Makefile for Planttracer web application
# - Creates CI/CD environment in GitHub
# - Manages deployemnt to AWS Linux
# - Updated to handle virtual environment
# - Simple CRUD management of local database instance for developers

PYLINT_FILES=$(shell /bin/ls *.py  | grep -v bottle.py | grep -v app_wsgi.py)
PYLINT_THRESHOLD=9.5
TS_FILES := $(wildcard *.ts */*.ts)
JS_FILES := $(TS_FILES:.ts=.js)

################################################################
# Manage the virtual environment.
# THis is only used for virtual testing and under Zappo
ACTIVATE   = . venv/bin/activate
REQ = venv/pyvenv.cfg
PY=python3.11
PYTHON=$(ACTIVATE) ; $(PY)
PIP_INSTALL=$(PYTHON) -m pip install --no-warn-script-location
venv/pyvenv.cfg:
	$(PY) -m venv venv

venv:
	$(PY) -m venv venv

################################################################
# SAM Commands

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

pylint: $(REQ)
	$(PYTHON) -m pylint --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose $(PYLINT_FILES)

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

#
# In the tests below, we always test the database connectivity first
# It makes no sense to run the tests otherwise

##
## Dynamic Analysis

pytest-db: $(REQ)
	if [ -z "$${PLANTTRACER_CREDENTIALS}" ]; then echo PLANTTRACER_CREDENTIALS is not set; exit 1; fi
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful

pytest:  $(REQ)
	if [ -z "$${PLANTTRACER_CREDENTIALS}" ]; then echo PLANTTRACER_CREDENTIALS is not set; exit 1; fi
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=INFO .

# Set these during development to speed testing of the one function you care about:
TEST1MODULE=tests/app_test.py
TEST1FUNCTION="-k test_templates"
pytest1:
	if [ -z "$${PLANTTRACER_CREDENTIALS}" ]; then echo PLANTTRACER_CREDENTIALS is not set; exit 1; fi
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=DEBUG --maxfail=1 $(TEST1MODULE) $(TEST1FUNCTION)

pytest-selenium:
	if [ -z "$${PLANTTRACER_CREDENTIALS}" ]; then echo PLANTTRACER_CREDENTIALS is not set; exit 1; fi
	$(PYTHON) -m pytest -v --log-cli-level=INFO tests/sitetitle_test.py

pytest-debug:
	if [ -z "$${PLANTTRACER_CREDENTIALS}" ]; then echo PLANTTRACER_CREDENTIALS is not set; exit 1; fi
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=DEBUG

pytest-debug1:
	if [ -z "$${PLANTTRACER_CREDENTIALS}" ]; then echo PLANTTRACER_CREDENTIALS is not set; exit 1; fi
	@echo run in debug mode but stop on first error
	$(PYTHON) -m pytest --log-cli-level=DEBUG --maxfail=1 tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=DEBUG -k test_new_movie tests/movie_test.py

pytest-app-framework:
	if [ -z "$${PLANTTRACER_CREDENTIALS}" ]; then echo PLANTTRACER_CREDENTIALS is not set; exit 1; fi
	@echo validate app framework
	$(PYTHON) -m pytest -x --log-cli-level=DEBUG tests/app_test.py -k test_templates

pytest-quiet:
	if [ -z "$${PLANTTRACER_CREDENTIALS}" ]; then echo PLANTTRACER_CREDENTIALS is not set; exit 1; fi
	@echo quietly make pytest and stop at the firt error
	$(PYTHON) -m pytest --log-cli-level=ERROR tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest --log-cli-level=ERROR

test-schema-upgrade:
	$(PYTHON) dbmaint.py --rootconfig etc/mysql-root-localhost.ini --dropdb test_db1 || echo database does not exist
	$(PYTHON) dbmaint.py --rootconfig etc/mysql-root-localhost.ini --createdb test_db1 --schema etc/schema_0.sql
	$(PYTHON) dbmaint.py --rootconfig etc/mysql-root-localhost.ini --upgradedb test_db1
	$(PYTHON) dbmaint.py --rootconfig etc/mysql-root-localhost.ini --dropdb test_db1

################################################################
### Database management for testing and CI/CD

PLANTTRACER_LOCALDB_NAME ?= actions_test

create_localdb:
	@echo Creating local database, exercise the upgrade code and write credentials to etc/credentials.ini using etc/github_actions_mysql_rootconfig.ini
	@echo etc/credentials.ini will be used automatically by other tests
	$(PYTHON) dbmaint.py --create_client=$$MYSQL_ROOT_PASSWORD --writeconfig etc/github_actions_mysql_rootconfig.ini
	$(PYTHON) dbmaint.py --rootconfig etc/github_actions_mysql_rootconfig.ini  --createdb $(PLANTTRACER_LOCALDB_NAME) --schema etc/schema_0.sql --writeconfig etc/credentials.ini
	PLANTTRACER_CREDENTIALS=etc/credentials.ini $(PYTHON) dbmaint.py --upgradedb --loglevel DEBUG
	PLANTTRACER_CREDENTIALS=etc/credentials.ini $(PYTHON) -m pytest -x --log-cli-level=DEBUG tests/dbreader_test.py

remove_localdb:
	@echo Removing local database using etc/github_actions_mysql_rootconfig.ini
	$(PYTHON) dbmaint.py --rootconfig etc/github_actions_mysql_rootconfig.ini --dropdb $(PLANTTRACER_LOCALDB_NAME) --writeconfig etc/credentials.ini
	/bin/rm -f etc/credentials.ini

coverage:
	$(PYTHON) -m pip install --upgrade pip
	$(PIP_INSTALL) codecov pytest pytest_cov
	$(PYTHON) -m pytest -v --cov=. --cov-report=xml tests

run-local:
	@echo run bottle locally, storing new data in database
	PLANTTRACER_CREDENTIALS=etc/credentials.ini $(PY) bottle_app.py --storelocal

run-local-demo:
	@echo run bottle locally in demo mode, using local database
	PLANTTRACER_CREDENTIALS=etc/credentials.ini PLANTTRACER_DEMO_MODE_AVAILABLE=1 $(PY) bottle_app.py --storelocal

debug:
	make debug-local

DEBUG:=$(PY) bottle_app.py --loglevel DEBUG
debug-local:
	@echo run bottle locally in debug mode, storing new data in database
	PLANTTRACER_CREDENTIALS=etc/credentials-localhost.ini $(DEBUG) --storelocal

debug-single:
	@echo run bottle locally in debug mode single-threaded
	PLANTTRACER_CREDENTIALS=etc/credentials-localhost.ini $(DEBUG)

debug-multi:
	@echo run bottle locally in debug mode multi-threaded
	PLANTTRACER_CREDENTIALS=etc/credentials-localhost.ini $(DEBUG)   --multi

debug-dev:
	@echo run bottle locally in debug mode, storing new data in S3, with the dev.planttracer.com database
	@echo for debugging Python and Javascript with remote database
	PLANTTRACER_CREDENTIALS=etc/credentials-aws-dev.ini $(DEBUG)

debug-dev-api:
	@echo Debug local JavaScript with remote server.
	@echo run bottle locally in debug mode, storing new data in S3, with the dev.planttracer.com database and API calls
	PLANTTRACER_CREDENTIALS=etc/credentials-aws-dev.ini PLANTTRACER_API_BASE=https://dev.planttracer.com/ $(DEBUG)

freeze:
	$(PYTHON) -m pip freeze > requirements.txt

clean:
	find . -name '*~' -exec rm {} \;
	/bin/rm -rf __pycache__ */__pycache__

tracker-debug:
	/bin/rm -f outfile.mp4
	$(PYTHON) tracker.py --moviefile="tests/data/2019-07-12 circumnutation.mp4" --outfile=outfile.mp4
	open outfile.mp4

eslint:
	(cd static;make eslint)
	(cd templates;make eslint)

jscoverage:
	npm run coverage
	npm test
################################################################
# Installations are used by the CI pipeline:
# Generic:
install-python-dependencies: $(REQ)
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements.txt ]; then $(PIP_INSTALL) -r requirements.txt ; else echo no requirements.txt ; fi

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
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements-ubuntu.txt ]; then $(PIP_INSTALL) -r requirements-ubuntu.txt ; else echo no requirements-ubuntu.txt ; fi
	if [ -r requirements.txt ];        then $(PIP_INSTALL) -r requirements.txt ; else echo no requirements.txt ; fi

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
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements-macos.txt ]; then $(PIP_INSTALL) -r requirements-macos.txt ; else echo no requirements-macos.txt ; fi
	if [ -r requirements.txt ];       then $(PIP_INSTALL) -r requirements.txt ; else echo no requirements.txt ; fi

# Includes Windows dependencies
install-windows:
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements-windows.txt ]; then $(PIP_INSTALL) -r requirements-windows.txt ; else echo no requirements-ubuntu.txt ; fi
	if [ -r requirements.txt ];         then $(PIP_INSTALL) -r requirements.txt ; else echo no requirements.txt ; fi

################################################################
## Python maintenance and Zappa deployment

# https://stackoverflow.com/questions/24764549/upgrade-python-packages-from-requirements-txt-using-pip-command
update-python:
	cat requirements.txt | cut -f1 -d= | xargs pip install -U

update-dev:
	$(ACTIVATE) && pip freeze > requirements.txt
	$(ACTIVATE) && zappa update dev

update-prod:
	$(ACTIVATE) && pip freeze > requirements.txt
	$(ACTIVATE) && zappa update production

update-demo:
	$(ACTIVATE) && pip freeze > requirements.txt
	$(ACTIVATE) && zappa update demo

%.js: %.ts
	tsc $<
