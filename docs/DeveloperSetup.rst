Developer Setup
===============

Requirements and Preparation
----------------------------

* MySQL 8.0. See :doc:`MySQLSetup`

* Python3.11. Verify that typing 'python' gives you python3.11. If it doesn't, make sure that your PATH is up-to-date.

* HomeBrew. If installing on a MacOS machine, `HomeBrew <https://brew.sh>`_ must be installed prior to performing the steps below.

Setup Steps
-----------

1. Clone the Plant Tracer webapp into a directory that will be the local repository, for example::

    $ git clone --recurse-submodules https://github.com/Plant-Tracer/webapp.git webapp

2. Change to the local repository directory::

    $ cd webapp

3. Make a Python Virtual Environment (venv)::

    $ make venv

4. Activate the venv::

   $ . venv/bin/activate

5. Install the prerequisites with make install-<your-os>, e.g.::

    $ make install-macos

6. Create a new local database, which will be named actions_test::

   $ export MYSQL_ROOT_PASSWORD=testrootpass
   $ make create_localdb

7. Run the self-tests::

   $ make pytest-quiet

8. Create your first course! If you want, give it a demo account too::

.. code-block::

   $ PLANTTRACER_CREDENTIALS=etc/credentials.ini python dbmaint.py --create_course "My Course Name" --admin_email your_admin_email@company.com --admin_name "Your Name" [--demo_email your_demo_email@company.com]
   course_key: leact-skio-proih

9. You now have a course key! If the demo account is made, you have that too.

10. In order run a non-demo instance, a mailer must be configured in the credentials ini file, for example:

.. code-block::

    [smtp]
    SMTP_USERNAME=plantadmin@mycompany.com
    SMTP_PASSWORD=MyPassword
    SMTP_PORT=587
    SMTP_HOST=smtp.mycompany.com
       
    [imap]
    IMAP_USERNAME=plantadmin@mycompany.com
    IMAP_PASSWORD=MyPassword
    IMAP_HOST=imap.mycompany.com
    IMAP_PORT=993

11. To run a Plant-Tracer/webapp server process locally, examine the debug-* targets in Makefile. The general form is::

.. code-block::

    $ PLANTTRACER_CREDENTIALS=${MY_INI_FILES}/credentials-myconfig.ini python bottle_app.py [arguments]

12. A specific case: running with movies stored in MySQL rather than S3::

.. code-block::

    $ PLANTTRACER_CREDENTIALS=${MY_INI_FILES}/credentials-myconfig.ini python bottle_app.py --storelocal

13. Another case: running in demo mode, with movies stored in MySQL rather than S3::

.. code-block::

    $ PLANTTRACER_CREDENTIALS=${MY_INI_FILES}/credentials-myconfig.ini PLANTTRACER_DEMO_MODE_AVAILABLE=1 python bottle_app.py --storelocal
