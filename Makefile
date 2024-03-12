# Makefile for Planttracer web application
# - Creates CI/CD environment in GitHub
# - Manages deployemnt to AWS Linux
# - Updated to handle virtual environment.

PYLINT_FILES=$(shell /bin/ls *.py  | grep -v bottle.py | grep -v app_wsgi.py)
PYLINT_THRESHOLD=9.5

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
	make touch

check:
	make pylint
	make pytest

touch:
	touch tmp/restart.txt

pylint: $(REQ)
	$(PYTHON) -m pylint --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose $(PYLINT_FILES)

#
# In the tests below, we always test the database connectivity first
# It makes no sense to run the tests otherwise

pytest-db: $(REQ)
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful

pytest:  $(REQ)
	make touch
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=INFO .

pytest-movie-test:
	make touch
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=DEBUG tests/movie_test.py -k test_movie_extract --maxfail=1

pytest-selenium:
	make touch
	$(PYTHON) -m pytest -v --log-cli-level=INFO tests/sitetitle_test.py

pytest-debug:
	make touch
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=DEBUG

pytest-debug1:
	@echo run in debug mode but stop on first error
	make touch
	$(PYTHON) -m pytest --log-cli-level=DEBUG --maxfail=1 tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest -v --log-cli-level=DEBUG

pytest-app-framework:
	@echo validate app framework
	$(PYTHON) -m pytest -x --log-cli-level=DEBUG tests/app_test.py -k test_templates

pytest-quiet:
	@echo quietly make pytest and stop at the firt error
	make touch
	$(PYTHON) -m pytest --log-cli-level=ERROR tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest --log-cli-level=ERROR

create_localdb:
	@echo Creating local database and writing results to etc/credentials.ini using etc/github_actions_mysql_rootconfig.ini
	$(PYTHON) dbmaint.py --create_client=$$MYSQL_ROOT_PASSWORD  --writeconfig etc/github_actions_mysql_rootconfig.ini
	$(PYTHON) dbmaint.py --rootconfig etc/github_actions_mysql_rootconfig.ini  --createdb actions_test --writeconfig etc/credentials.ini
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
	@echo run bottle locally in debug mode
	$(PYTHON) bottle_app.py --loglevel DEBUG --dbcredentials etc/credentials.ini

debug-local:
	@echo run bottle locally in debug mode
	$(PYTHON) bottle_app.py --loglevel DEBUG --dbcredentials etc/credentials-local.ini

freeze:
	$(PYTHON) -m pip freeze > requirements.txt

clean:
	find . -name '*~' -exec rm {} \;
	/bin/rm -rf __pycache__ */__pycache__


tracker-debug:
	/bin/rm -f outfile.mp4
	$(PYTHON) tracker.py --moviefile="tests/data/2019-07-12 circumnutation.mp4" --outfile=outfile.mp4
	open outfile.mp4

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
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements-ubuntu.txt ]; then $(PIP_INSTALL) -r requirements-ubuntu.txt ; else echo no requirements-ubuntu.txt ; fi
	if [ -r requirements.txt ];        then $(PIP_INSTALL) -r requirements.txt ; else echo no requirements.txt ; fi

# Includes MacOS dependencies managed through Brew
install-macos:
	brew update
	brew upgrade
	brew install python3
	brew install ffmpeg
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements-macos.txt ]; then $(PIP_INSTALL) -r requirements-macos.txt ; else echo no requirements-ubuntu.txt ; fi
	if [ -r requirements.txt ];       then $(PIP_INSTALL) -r requirements.txt ; else echo no requirements.txt ; fi

# Includes Windows dependencies
install-windows:
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements-windows.txt ]; then $(PIP_INSTALL) -r requirements-windows.txt ; else echo no requirements-ubuntu.txt ; fi
	if [ -r requirements.txt ];         then $(PIP_INSTALL) -r requirements.txt ; else echo no requirements.txt ; fi
