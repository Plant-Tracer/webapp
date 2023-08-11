import sys
import os
import uuid
import logging

from os.path import abspath,dirname

sys.path.append( dirname(dirname(abspath(__file__))))

import mailer
import time

from jinja2.nativetypes import NativeEnvironment


MSG="""to: {{ to_addr }}
from: {{ from_addr }}
subject: This is a test subject {{ guid }}

This is a test message.
"""

guid = str(uuid.uuid4())

# https://realpython.com/python-sleep/#adding-a-python-sleep-call-with-decorators

def test_send_message():
    msg_env = NativeEnvironment().from_string( MSG )
    msg = msg_env.render( to_addr='simsong@acm.org',
                          from_addr='plantadmin@planttracer.com',
                          guid = guid)

    DRY_RUN = False
    TO_ADDRS = ['plantadmin@planttracer.com', 'simsong@acm.org']
    smtp_config = mailer.smtp_config_from_environ()
    smtp_config['SMTP_DEBUG'] = True
    mailer.send_message( from_addr = 'do-not-reply@planttracer.com',
                         to_addrs  = TO_ADDRS,
                         smtp_config = smtp_config,
                         dry_run     = DRY_RUN,
                         msg         = msg
                        )

    # Now let's see if the message got delivered evey 100 msec and then delete it
    # Wait for up to 5 seconds
    def cb( num, M ):
        if guid in M['subject']:
            return mailer.DELETE

    for i in range(50):
        deleted = mailer.imap_inbox_scan( mailer.imap_config_from_environ(), cb )
        if deleted>0:
            break

        logging.warning("response %s not found. Sleep again count %d",guid,i)
        time.sleep(0.1)
    if deleted==0:
        raise RuntimeError("Could not delete test message")


if __name__=="__main__":
    # Test program for listing, deleting a message by number, or deleting all messages in imap box
    import argparse
    parser = argparse.ArgumentParser(description='IMAP cli',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--list',action='store_true')
    parser.add_argument('--delete_all',action='store_true')
    args = parser.parse_args()

    def m_lister(num, M):
        print(num, M['subject'])

    def m_delete_all(num, M):
        print("will delete", num, M['subject'])
        return mailer.DELETE

    if args.list:
        func = m_lister
    elif args.delete_all:
        func = m_delete_all
    else:
        raise RuntimeError("specify an action")
    mailer.imap_inbox_scan( mailer.imap_config_from_environ(), func)
