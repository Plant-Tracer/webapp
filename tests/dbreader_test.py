import sys
import os
import logging
import uuid

import pytest
import pymysql

import app.dbmaint as dbmaint
import app.paths as paths
import app.dbfile as dbfile
import app.db as db
from app.auth import credentials_file,config,get_dbreader,get_dbwriter,smtp_config

if sys.version < '3.11':
    raise RuntimeError("Requires python 3.11 or above.")

def test_dbreader():
    dbreader = get_dbreader()
    assert dbreader is not None


# Make sure we can make a database connection
def test_db_connection():
    dbreader = get_dbreader()
    try:
        logging.debug("dbreader=%s",dbreader)
        v = dbfile.DBMySQL.csfr(dbreader, "select version()")
    except pymysql.err.OperationalError as e:
        print("operational error: ",str(e),file=sys.stderr)
        print("dbreader: ",str(dbreader),file=sys.stderr)
        raise
    logging.info("MySQL Version %s",v[0][0])
    logging.info("dbreader: %s",dbreader)

    dbwriter = get_dbreader()
    try:
        logging.debug("dbwriter=%s",dbwriter)
        v = dbfile.DBMySQL.csfr(dbwriter, "select version()")
    except pymysql.err.OperationalError as e:
        print("operational error: ",str(e),file=sys.stderr)
        print("dbreader: ",str(dbreader),file=sys.stderr)
        print("dbreader password: ",dbreader.password,file=sys.stderr)
        raise
    logging.info("MySQL Version %s",v[0][0])
    logging.info("dbwriter: %s",dbwriter)


    # Test the dumping
    dumpdir = '/tmp/dump' + str(uuid.uuid4())
    dbmaint.dump(config(), dumpdir)
    dbmaint.sqlbackup(config(), dumpdir + "/sqlbackup.sql", all_databases=True)

    with pytest.raises(FileExistsError):
        dbmaint.dump(config(), dumpdir)
