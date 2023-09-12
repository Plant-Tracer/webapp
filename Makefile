#
# Note: when this runs on Dreamhost, we need to use the python in $HOME/opt/bin
#

PYLINT_FILES=$(shell /bin/ls *.py  | grep -v bottle.py | grep -v app_wsgi.py)
PYLINT_THRESHOLD=8

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

pytest:
	make touch
	python3 -m pytest .

coverage:
	python3 -m pip install pytest pytest_cov
	python3 -m pytest -v --cov=. --cov-report=xml tests

debug:
	python bottle_app.py

clean:
	find . -name '*~' -exec rm {} \;


# These are used by the CI pipeline:
install-python-dependencies:
	python3 -m pip install --upgrade pip
	if [ -r requirements.txt ]; then python3 -m pip install --user -r requirements.txt ; else echo no requirements.txt ; fi
	python3 -m pip install --upgrade pip

install-ubuntu:
	sudo apt install ffmpeg

install-macos:
	brew update
	brew upgrade
	brew install python3
	brew install libmagic
	brew install ffmpeg

install-windows:
	echo fill something in here
