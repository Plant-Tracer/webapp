import sys
import os
import logging

from os.path import abspath, dirname

sys.path.append(dirname(dirname(abspath(__file__))))

import db
import ctools.dbfile as dbfile

if sys.version < '3.11':
    raise RuntimeError("Requires python 3.11 or above.")

def test_dbreader():
    dbreader = db.get_dbreader()
    assert dbreader is not None

# Make sure we can make a database connection
def test_db_connection():
    dbreader = db.get_dbreader()
    v = dbfile.DBMySQL.csfr(dbreader, "select version()")
    logging.info("MySQL Version %s",v[0][0])
    logging.info("dbreader: %s",dbreader)

    dbwriter = db.get_dbreader()
    v = dbfile.DBMySQL.csfr(dbwriter, "select version()")
    logging.info("MySQL Version %s",v[0][0])
    logging.info("dbwriter: %s",dbwriter)
