import sys
import os

from os.path import abspath,dirname

sys.path.append( dirname(dirname(abspath(__file__))))

import db
import ctools.dbfile as dbfile

def test_dbreader():
    dbreader = db.get_dbreader()
    assert dbreader is not None
