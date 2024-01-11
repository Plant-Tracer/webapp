[![codecov](https://codecov.io/gh/Plant-Tracer/webapp/graph/badge.svg?token=YRMITDBBJ1)](https://codecov.io/gh/Plant-Tracer/webapp)

Deploy Dev: ![example workflow](https://github.com/github/docs/actions/workflows/deploy-dev.yml/badge.svg)
Deploy Prod: ![example workflow](https://github.com/github/docs/actions/workflows/deploy-production.yml?branch=deploy-dreamhost/badge.svg)
# webapp
Client for web-based JavaScript app; Server for python-based backend

This repo provides the custom-written Python code to for the https://app.planttracer.com/ website.

The top-level planttracer.com website is currently a static HTML site. This repo runs in a sub-domain https://app.planttracer.com/ and provides the app that runs in a browser on a mobile phone or desktop.

The repo is designed to be check out as ~/app.planttracer.com/ on a Dreamhost user account. It runs the python application in Bottle using the Dreamhost Passenger WSGI framework. The repo can also be checked out into other domain directories for development and testing on the website. You can also check it out locally and run a local webserver.

## Linux

This application was written with Linux as the target platform, and the Makefile is Linux-specific.

## Windows
It will run on Windows but not have all the features enabled compared to when it is run on Linux.

To run bottle_app.py on Windows (assuming no POSIX-compliant command line there):
Prequisities:
- Python 3.x (I think Python 3.9 is what we started with)
- pip or pip3
```
pip install -r requirements.txt
pip install -r requirements-windows.txt
python3 bottle_app.py
```

## MacOS

Most things should just work on MacOS as well, though that's not a specifically targetted platform for either development or runtime. On MacOS, libmagic must be installed:
```
brew install libmagic
```
