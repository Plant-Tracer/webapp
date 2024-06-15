import localmail
import pytest
import configparser
import logging
import threading
import time
import sys
import os
from os.path import join,dirname,abspath

sys.path.append(dirname(dirname(dirname(abspath(__file__)))))
import paths

import auth

def singleton(cls):
    instances = {}
    def getinstance():
        if cls not in instances:
            instances[cls] = cls()
        return instances[cls]
    return getinstance

# We use the mail_mutex to block the main thread until the server is running
MAIL_TIMEOUT = 10
mutex = threading.Lock()

def report(smtp, imap, http):
    """do stuff with ports"""
    logging.info("smtp=%s",smtp)
    logging.info("imap=%s",smtp)
    logging.info("http=%s",smtp)
    mutex.release()
    logging.info("*************** LOCALMAIL RUNNING; MUTEX RELEASED *************")

@singleton
class Localmail():
    """Create a localmail server and return an object that has the config.
       We can't shut it down because reactor is not restartable.
    Over time, we'll implement functionality to search the mailbox.
    """
    def __init__(self):
        localmail_config = configparser.ConfigParser()
        localmail_config.read( auth.credentials_file() )
        if 'smtp' not in localmail_config:
            logging.error('LOCALMAIL FNAME: %s',FNAME)
            logging.error('LOCALMMAIL config: %s',localmail_config)
            logging.error('LOCALMAIL file: %s',open(FNAME).read())

        smtp_port = int(localmail_config['smtp']['smtp_port'])
        imap_port = int(localmail_config['imap']['imap_port'])
        try:
            http_port = int(localmail_config['localmail']['http_port'])
        except KeyError:
            http_port = None
        try:
            mailbox = localmail_config['localmail']['mailbox']
        except KeyError:
            http_port = None
        logging.info("smtp_port=%s imap_port=%s http_port=%s",
                     smtp_port,imap_port,http_port)

        mutex.acquire()
        thread = threading.Thread(
            target=localmail.run,
            args=( smtp_port, imap_port, http_port, mailbox, report),
            daemon=True)
        thread.start()
        mutex.acquire(timeout=MAIL_TIMEOUT)

        logging.info("*************** LAUNCHED LOCALMAIL *************")
        self.localmail_config = localmail_config

    def dump_mailbox(self):
        logging.info("== BEGIN MAIL TRANSCRIPT ==")
        with open( self.localmail_config['localmail']['mailbox'],"r") as f:
            for line in f:
                logging.info(line.strip())
        logging.info("== END MAIL TRANSCRIPT ==")

    def clear_mailbox(self):
        with open( self.localmail_config['localmail']['mailbox'],"w") as f:
            print(f.truncate())

@pytest.fixture
def mailer_config():
    lm = Localmail()
    yield lm.localmail_config
    lm.dump_mailbox()
    lm.clear_mailbox()
