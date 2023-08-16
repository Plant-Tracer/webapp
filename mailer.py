#!/usr/bin/env python36

"""This program implements an autoresponder. It's in the mailstats repository
because the responder does analysis of mail files."""

import sys
import smtplib
import logging
import imaplib
import os
from email.parser import BytesParser
from email import policy


SMTP_SERVER = 'SMTP_SERVER'
SMTP_USERNAME = 'SMTP_USERNAME'
SMTP_PASSWORD = 'SMTP_PASSWORD'
SMTP_PORT = 'SMTP_PORT'
SMTP_PORT_DEFAULT = 587
SMTP_DEBUG = 'SMTP_DEBUG'
SMTP_DEBUG_DEFAULT = False

def send_message(*,
                 from_addr : str ,
                 to_addrs : [str] ,
                 msg : str,
                 dry_run:bool = False,
                 smtp_config:dict ):
    # Validate types
    assert isinstance(from_addr, str)
    for to_addr in to_addrs:
        assert isinstance(to_addr, str)

    if dry_run:
        print("==== Will not send this message: ====\n{}\n====================\n".format(msg),file=sys.stderr)
        return

    port  = smtp_config.get(SMTP_PORT,  SMTP_PORT_DEFAULT)
    debug = smtp_config.get(SMTP_DEBUG, SMTP_DEBUG_DEFAULT)

    with smtplib.SMTP( smtp_config[SMTP_SERVER], port ) as smtp:
        logging.info("sending mail to %s with SMTP" ,",".join(to_addrs))
        if debug:
            smtp.set_debuglevel( 1 )
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login( smtp_config[ SMTP_USERNAME ] , smtp_config[ SMTP_PASSWORD ] )
        smtp.sendmail( from_addr, to_addrs, msg.encode('utf8'))

def smtp_config_from_environ():
    return { SMTP_SERVER : os.environ[ SMTP_SERVER ],
             SMTP_USERNAME : os.environ[SMTP_USERNAME],
             SMTP_PASSWORD : os.environ[SMTP_PASSWORD],
             SMTP_PORT     : int(os.environ[SMTP_PORT])
            }


IMAP_SERVER   = 'IMAP_SERVER'
IMAP_USERNAME = 'IMAP_USERNAME'
IMAP_PASSWORD = 'IMAP_PASSWORD'
DELETE = "<DELETE>"

def imap_inbox_scan( imap_config, callback ):
    """Call callback on each message in the imap inbox. If callback returns DELETE, then delete the message.
    returns numbers of messages deleted.
    """
    deleted = 0
    M = imaplib.IMAP4_SSL( imap_config[IMAP_SERVER])
    M.login(imap_config[IMAP_USERNAME], imap_config[IMAP_PASSWORD] )
    M.select()
    typ, data = M.search(None, 'ALL')
    for num in data[0].split():
        typ, d2 = M.fetch(num, '(RFC822)')
        for val in d2:
            if type(val)==tuple:
                (a,b) = val
                num = a.decode('utf-8').split()[0]
                msg = BytesParser(policy=policy.default).parsebytes(b)
                if callback( num, msg ) is DELETE:
                    M.store(num, '+FLAGS', '\\Deleted')
                    deleted += 1
    try:
        M.expunge()
        M.close()
        M.logout()
    except imaplib.IMAP4. abort as e:
        print(e, file=sys.stderr)
    return deleted


def imap_config_from_environ():
    return { IMAP_SERVER : os.environ[ IMAP_SERVER ],
             IMAP_USERNAME : os.environ[IMAP_USERNAME],
             IMAP_PASSWORD : os.environ[IMAP_PASSWORD]
            }
