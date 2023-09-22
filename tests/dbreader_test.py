import sys
import os

from os.path import abspath,dirname

sys.path.append( dirname(dirname(abspath(__file__))))

import db
import ctools.dbfile as dbfile

if sys.version < '3.11':
    raise RuntimeError("Requires python 3.11 or above.")

def test_dbreader():
    dbreader = db.get_dbreader()
    assert dbreader is not None
