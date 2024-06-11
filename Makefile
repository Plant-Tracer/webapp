# Makefile for Planttracer web application
# - Creates CI/CD environment in GitHub
# - Manages deployemnt to AWS Linux
# - Updated to handle virtual environment.

PYLINT_FILES=$(shell /bin/ls *.py  | grep -v bottle.py | grep -v app_wsgi.py)
PYLINT_THRESHOLD=9.5
TS_FILES := $(wildcard *.ts */*.ts)
JS_FILES := $(TS_FILES:.ts=.js)


################################################################
# Manage the virtual environment
A   = . venv/bin/activate
REQ = venv/pyvenv.cfg
PY=python3.11
PYTHON=$(A) ; $(PY)
PIP_INSTALL=$(PYTHON) -m pip install --no-warn-script-location
venv/pyvenv.cfg:
	$(PY) -m venv venv

venv:
	$(PY) -m venv venv

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
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful

pytest:  $(REQ)
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=INFO .

# Set these during development to speed testing of the one function you care about:
TEST1MODULE=tests/movie_test.py
TEST1FUNCTION="-k test_movie_extract1"
pytest1:
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=DEBUG --maxfail=1 $(TEST1MODULE) $(TEST1FUNCTION)

pytest-selenium:
	$(PYTHON) -m pytest -v --log-cli-level=INFO tests/sitetitle_test.py

pytest-debug:
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=DEBUG

pytest-debug1:
	@echo run in debug mode but stop on first error
	$(PYTHON) -m pytest --log-cli-level=DEBUG --maxfail=1 tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=DEBUG -k test_new_movie tests/movie_test.py

pytest-app-framework:
	@echo validate app framework
	$(PYTHON) -m pytest -x --log-cli-level=DEBUG tests/app_test.py -k test_templates

pytest-quiet:
	@echo quietly make pytest and stop at the firt error
	$(PYTHON) -m pytest --log-cli-level=ERROR tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest --log-cli-level=ERROR

################################################################



create_localdb:
	@echo Creating local database, exercise the upgrade code and write credentials to etc/credentials.ini using etc/github_actions_mysql_rootconfig.ini
	$(PYTHON) dbmaint.py --create_client=$$MYSQL_ROOT_PASSWORD                 --writeconfig etc/github_actions_mysql_rootconfig.ini
	$(PYTHON) dbmaint.py --rootconfig etc/github_actions_mysql_rootconfig.ini  --createdb actions_test --schema etc/schema_0.sql --writeconfig etc/credentials.ini
	$(PYTHON) dbmaint.py --rootconfig etc/github_actions_mysql_rootconfig.ini  --upgradedb actions_test --loglevel DEBUG
	$(PYTHON) -m pytest -x --log-cli-level=DEBUG tests/dbreader_test.py

remove_localdb:
	@echo Removing local database using etc/github_actions_mysql_rootconfig.ini
	$(PYTHON) dbmaint.py --rootconfig etc/github_actions_mysql_rootconfig.ini --dropdb actions_test --writeconfig etc/credentials.ini
	/bin/rm -f etc/credentials.ini

coverage:
	$(PYTHON) -m pip install --upgrade pip
	$(PIP_INSTALL) codecov pytest pytest_cov
	$(PYTHON) -m pytest -v --cov=. --cov-report=xml tests

debug:
	make debug-local

DEBUG:=$(PYTHON) bottle_app.py --loglevel DEBUG
debug-single:
	@echo run bottle locally in debug mode single-threaded
	$(DEBUG)  --dbcredentials etc/credentials.ini

debug-multi:
	@echo run bottle locally in debug mode multi-threaded
	$(DEBUG)  --dbcredentials etc/credentials.ini --multi

debug-local:
	@echo run bottle locally in debug mode, storing new data in database
	$(DEBUG) --storelocal --dbcredentials etc/credentials-local.ini

debug-dev:
	@echo run bottle locally in debug mode, storing new data in S3, with the dev.planttracer.com database
	$(DEBUG) --dbcredentials etc/credentials-dev.ini

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
	npm install --save-dev jest
	npm install --save-dev babel-jest @babel/core @babel/preset-e


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
	if [ -r requirements-macos.txt ]; then $(PIP_INSTALL) -r requirements-macos.txt ; else echo no requirements-ubuntu.txt ; fi
	if [ -r requirements.txt ];       then $(PIP_INSTALL) -r requirements.txt ; else echo no requirements.txt ; fi

# Includes Windows dependencies
install-windows:
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements-windows.txt ]; then $(PIP_INSTALL) -r requirements-windows.txt ; else echo no requirements-ubuntu.txt ; fi
	if [ -r requirements.txt ];         then $(PIP_INSTALL) -r requirements.txt ; else echo no requirements.txt ; fi

update:
	$(PYTHON) pip freeze > requirements.txt
	$(PYTHON) zappa update dev

%.js: %.ts
	tsc $<
