#
# Note: when this runs on Dreamhost, we need to use the python in $HOME/opt/bin
#

PYLINT_FILES=$(shell /bin/ls *.py  | grep -v bottle.py | grep -v app_wsgi.py)
PYTHON=python3
PIP_INSTALL=$(PYTHON) -m pip install --no-warn-script-location --user

# By default, PYLINT generates an error if your code does not rank 10.0.
# This makes us tolerant of minor problems.
PYLINT_THRESHOLD=9.5

all:
	@echo verify syntax and then restart
	make pylint
	make touch

check:
	make pylint
	make pytest

touch:
	touch tmp/restart.txt

pylint:
	pylint --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose $(PYLINT_FILES)

flake8:
	flake8 $(PYLINT_FILES)

#
# In the tests below, we always test the database connectivity first
# It makes no sense to run the tests otherwise
pytest-db:
	$(PYTHON) -m pytest --log-cli-level=DEBUG tests/dbreader_test.py
	@echo dbreader_test is successful

pytest:
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

pytest-quiet:
	@echo quietly make pytest and stop at the firt error
	make touch
	$(PYTHON) -m pytest --log-cli-level=ERROR tests/dbreader_test.py
	@echo dbreader_test is successful
	$(PYTHON) -m pytest --log-cli-level=ERROR

create_localdb:
	@echo Creating local database and writing results to etc/credentials.ini using etc/github_actions_mysql_rootconfig.ini
	$(PYTHON) dbmaint.py --rootconfig etc/github_actions_mysql_rootconfig.ini --createdb actions_test --writeconfig etc/credentials.ini

remove_localdb:
	@echo Removing local database using etc/github_actions_mysql_rootconfig.ini
	$(PYTHON) dbmaint.py --rootconfig etc/github_actions_mysql_rootconfig.ini --dropdb actions_test --writeconfig etc/credentials.ini
	/bin/rm -f etc/credentials.ini

coverage:
	$(PYTHON) -m pip install --upgrade pip
	$(PIP_INSTALL) codecov pytest pytest_cov
	$(PYTHON) -m pytest -v --cov=. --cov-report=xml tests

debug:
	python bottle_app.py

clean:
	find . -name '*~' -exec rm {} \;


tracker-demo:
	/bin/rm -f outfile.mp4
	$(PYTHON) tracker.py --moviefile="tests/data/2019-07-12 circumnutation.mp4" --outfile=outfile.mp4
	open outfile.mp4

################################################################
# Installations are used by the CI pipeline:
# Generic:
install-python-dependencies:
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements.txt ]; then $(PIP_INSTALL) -r requirements.txt ; else echo no requirements.txt ; fi

install-chromium-browser-ubuntu:
	sudo apt-get install -y chromium-browser
	chromium --version

install-chromium-browser-macos:
	brew install chromium --no-quarantine

# Includes ubuntu dependencies
install-ubuntu:
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
	brew install libmagic
	brew install ffmpeg
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements-macos.txt ]; then $(PIP_INSTALL) -r requirements-macos.txt ; else echo no requirements-ubuntu.txt ; fi
	if [ -r requirements.txt ];       then $(PIP_INSTALL) -r requirements.txt ; else echo no requirements.txt ; fi

# Includes Windows dependencies
install-windows:
	$(PYTHON) -m pip install --upgrade pip
	if [ -r requirements-windows.txt ]; then $(PIP_INSTALL) -r requirements-windows.txt ; else echo no requirements-ubuntu.txt ; fi
	if [ -r requirements.txt ];         then $(PIP_INSTALL) -r requirements.txt ; else echo no requirements.txt ; fi
