Developer Setup
===============

Requirements and Preparation
----------------------------

* MySQL 8.0. See :doc:`MySQLSetup`

* Python3.11. Verify that typing 'python' gives you python3.11. If it doesn't, make sure that your PATH is up-to-date.

* HomeBrew. If installing on a MacOS machine, `HomeBrew <https://brew.sh>`_ must be installed prior to performing the steps below.

Setup Steps
-----------

#. Clone the Plant Tracer webapp into a directory that will be the local repository, for example::

    git clone --recurse-submodules https://github.com/Plant-Tracer/webapp.git webapp

#. Change to the local repository directory::

    cd webapp

#. Make a Python Virtual Environment (venv)::

    make venv

#. Activate the venv::

    . venv/bin/activate

#. Install the prerequisites with make install-<your-os>, e.g.::

    make install-macos

#. Create a new local database

    * The database will be named actions_test by default

    * You may override the default with the ``PLANTTRACER_LOCALDB_NAME`` environment variable

    .. code-block::

       export MYSQL_ROOT_PASSWORD="your-mysql-root-password"
       make create_localdb

#. Run the self-tests:

   .. code-block::

    PLANTTRACER_CREDENTIALS=etc/credentials.ini make pytest-quiet

#. Create your first course! If you want, give it a demo account too:

   .. code-block::

    PLANTTRACER_CREDENTIALS=etc/credentials.ini python dbmaint.py --create_course "My Course Name" --admin_email your_admin_email@company.com --admin_name "Your Name" [--demo_email your_demo_email@company.com]
    >>> course_key: leact-skio-proih #save this course_key, you will need it later!

#. You now have a course key! If the demo account is made, you have that too.

#. In order run a non-demo instance, a mailer must be configured in the credentials ini file, for example:

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

#. If you have created a demo account, that action has also added demo movies to the database. To finish setting up demo mode, run the server in non-demo mode, track all the demo movies manually, and publish them.

Running Locally Quick Start
---------------------------

#. Run Plant-Tracer/webapp locally using the database created above and the default etc/credentials.ini file

   .. code-block::

    make run-local # Ctrl-C to quit

#. To run a Plant-Tracer/webapp server process locally, examine the debug-* targets in Makefile. The general form is:

   .. code-block::

    PLANTTRACER_CREDENTIALS=${MY_INI_FILES}/credentials-myconfig.ini python bottle_app.py [arguments]

#. A specific case: running with movies stored in MySQL rather than S3:

   .. code-block::

    PLANTTRACER_CREDENTIALS=${MY_INI_FILES}/credentials-myconfig.ini python bottle_app.py --storelocal

#. Another case: running in demo mode, with movies stored in MySQL rather than S3:

   * Note: there must be no user logged in for demo mode to take effect. May have to clear browser cookies.

   .. code-block::

       PLANTTRACER_CREDENTIALS=${MY_INI_FILES}/credentials-myconfig.ini DEMO_MODE=1 python bottle_app.py --storelocal

#. Sometimes, it is necessary to manually clear the cookies that Plant-Tracer/webapp creates in a browser. These cookies are of the form "api_key-"+my_database_name. Here is an example:

.. image:: media/PlantTracerCookieExample.png
