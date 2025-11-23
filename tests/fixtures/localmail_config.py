import pytest
import configparser
import logging
import threading
import localmail
import time
import sys
import os
import json
from os.path import join,dirname,abspath

import app.auth as auth
from src.app.constants import C
from src.app import mailer
from src.app.mailer import SMTP_HOST, SMTP_PORT, SMTP_NO_TLS, SMTP_USERNAME, SMTP_PASSWORD, IMAP_HOST, IMAP_PORT, IMAP_NO_SSL, IMAP_USERNAME, IMAP_PASSWORD


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
        #ToDo: make sure to use ports that are actually available

        self.smtp_port = 2025
        self.imap_port = 2143
        self.http_port = 8083
        self.mailbox = 'localmail.mbox'

        self.localmail_config = configparser.ConfigParser()
        self.localmail_config.add_section('smtp')
        self.localmail_config.set('smtp',SMTP_HOST,'localhost')
        self.localmail_config.set('smtp',SMTP_PORT,str(self.smtp_port))
        self.localmail_config.set('smtp',SMTP_USERNAME,'X')
        self.localmail_config.set('smtp',SMTP_PASSWORD,'X')
        self.localmail_config.set('smtp',SMTP_NO_TLS,'Y')


        self.localmail_config.add_section('imap')
        self.localmail_config.set('imap',IMAP_HOST,'localhost')
        self.localmail_config.set('imap',IMAP_PORT,str(self.imap_port))
        self.localmail_config.set('imap',IMAP_NO_SSL,'Y')
        self.localmail_config.set('imap',IMAP_USERNAME,'X')
        self.localmail_config.set('imap',IMAP_PASSWORD,'X')

        mutex.acquire()
        thread = threading.Thread(
            target=localmail.run,
            args=( self.smtp_port, self.imap_port, self.http_port, self.mailbox, report),
            daemon=True)
        thread.start()
        mutex.acquire(timeout=MAIL_TIMEOUT)

        logging.info("*************** LAUNCHED LOCALMAIL *************")

    def dump_mailbox(self):
        logging.info("== BEGIN MAIL TRANSCRIPT ==")
        with open( self.mailbox,"r") as f:
            for line in f:
                logging.info(line.strip())
        logging.info("== END MAIL TRANSCRIPT ==")

    def clear_mailbox(self):
        with open( self.mailbox,"w") as f:
            print(f.truncate())

@pytest.fixture(scope="session")
def mailer_config():
    lm = Localmail()
    os.environ[C.SMTPCONFIG_JSON] =  json.dumps(dict(lm.localmail_config['smtp']),default=str)
    yield lm.localmail_config
    try:
        del os.environ[C.SMTPCONFIG_JSON]
    except KeyError:
        pass                    # this shouldn't happen, but it did in testing...
    lm.dump_mailbox()
    lm.clear_mailbox()
