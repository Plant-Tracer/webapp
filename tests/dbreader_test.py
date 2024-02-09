import sys
import os
import logging

from os.path import abspath, dirname

sys.path.append(dirname(dirname(abspath(__file__))))

import pymysql

from auth import credentials_file,get_dbreader,get_dbwriter,smtp_config
import db
import ctools.dbfile as dbfile

if sys.version < '3.11':
    raise RuntimeError("Requires python 3.11 or above.")

def test_credentials_file():
    os.environ['AWS'] = 'YES'
    assert credentials_file == paths.AWS_CREDENTIALS_FILE
    del os.environ['AWS']
    assert credentials_file == paths.CREDENTIALS_FILE

def test_dbreader():
    dbreader = get_dbreader()
    assert dbreader is not None

def test_smtp_config(mocker):
    mocker.path("credentials_file", return_file= os.path.join(paths.TEST_DIR,'localmain_config.ini'))
    cfg = smtp_config()
    assert cfg['smtp_host']=='127.0.0.1'


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
