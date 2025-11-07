"""
conftest.py shares fixtures across multiple files.
It is automatically imported at the start of all other pytest files in this directory and those below it.
There can be a conftest for each directory
See - https://stackoverflow.com/questions/34466027/what-is-conftest-py-for-in-pytest
"""

import sys
from os.path import abspath, dirname, join

MY_DIR = dirname(abspath(__file__))
GIT_ROOT = dirname(MY_DIR)

SRC_DIR = join(GIT_ROOT, "src")
sys.path.append(SRC_DIR)

APP_DIR = join(SRC_DIR, "app")
sys.path.append(APP_DIR)

print("sys.path=",sys.path)
