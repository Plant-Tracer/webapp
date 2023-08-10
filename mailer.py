#!/usr/bin/env python36

"""This program implements an autoresponder. It's in the mailstats repository
because the responder does analysis of mail files."""

import sys
import smtplib
import logging

SMTP_SERVER = 'SMTP_SERVER'
SMTP_USERNAME = 'SMTP_USERNAME'
SMTP_PASSWORD = 'SMTP_PASSWORD'
SMPT_PORT = 'SMTP_PORT'
SMTP_PORT_DEFAULT = 587
SMTP_DEBUG = 'SMTP_DEBUG'
SMTP_DEBUG_DEFAULT = False

def send_message(*, from_addr : str , to_addrs : [str] , msg : str, dry_run:bool = False, use_sendmail:bool = False, smtp_config:dict ):
    # Validate types
    assert isinstance(from_addr, str)
    for to_addr in to_addrs:
        assert isinstance(to_addr, str)
    if not use_sendmail and not smtp_config:
        raise RuntimeError("Must either user_sendmail or provide a smtp_config")

    if dry_run:
        print("==== Will not send this message: ====\n{}\n====================\n".format(msg),file=sys.stderr)
        return

    if use_sendmail:
        logging.info("sending mail to %s with sendmail" ,",".join(to_addrs))
        from subprocess import Popen,PIPE
        p = Popen(['/usr/sbin/sendmail','-t'],stdin=PIPE)
        p.communicate(msg.encode('utf-8'))
        return True;

    port  = smtp_config.get(SMTP_PORT, SMTP_PORT_DEFAULT)
    debug = smtp_config.get(SMTP_DEBUG, SMTP_DEBUG_DEFAULT)

    with smtplib.SMTP( smtp_config[SMTP_HOST], port ) as smtp:
        logging.info("sending mail to %s with SMTP" ,",".join(to_addrs))
        if debug:
            smtp.set_debuglevel( 1 )
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login( smtp_config[ SMTP_USERNAME ] , smtp_config[ SMTP_PASSWORD ] )
        smtp.sendmail( from_addr, to_addrs, msg.encode('utf8'))
