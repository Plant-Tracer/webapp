import pytest
import configparser
import logging
import threading
import localmail
import time
import sys
import os
from os.path import join,dirname,abspath

import app.auth as auth

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
    logging.info("imap=%s",imap)
    logging.info("http=%s",http)
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
        if 'localmail' not in localmail_config:
            logging.warning('[localmail] not found in config.')

        smtp_port = int(localmail_config['localmail']['smtp_port'])
        imap_port = int(localmail_config['localmail']['imap_port'])
        try:
            http_port = int(localmail_config['localmail']['http_port'])
        except KeyError:
            http_port = None
        try:
            mailbox = localmail_config['localmail']['mailbox']
        except KeyError:
            http_port = None
        logging.info("smtp_port=%s imap_port=%s http_port=%s mailbox=%s",
                     smtp_port,imap_port,http_port,mailbox)

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
