Installation
============

Requirements and Preparation
----------------------------
* A home directory on Dreamhost (or another web hosting provider) that provides passengers, or some other wsgi-based approach for running a Python Bottle app (e.g. `mod_wsgi` on Apache).

* A MySQL database and a locally installed mysql client. 
  - You may use a pre-existing MySQL database, and if so, please prepare a mysql credentials file with three users defined:

    * `[client]` which can modify the schema
    * `[dbreader]` which can read the database
    * `[dbwriter]` which can write the database

  - Alternatively, if desired, these instructions will create a database that can be used locally, usually for development purposes. This process creates a mysql credentials file for this new database in etc/credentials.ini

* If installing on ubuntu or windows, ensure that python3.11 installed. Verify that typing 'python' gives you python3.11. If it doesn't, make sure that your PATH is up-to-date. (Python is installed automatically using brew on MacOS if not present, using the steps in this document.)

* If installing on a MacOS machine, HomeBrew must be installed prior to performing the steps below.

Installation
------------

1. Log into the user on the web provider and move the hosting directory into a different directory; we will be replacing it. In this case our directory is `demo.plantracer.com`::

    $ mv demo.planttracer.com demo-old

2. Clone the planttracer web app into the hosting directory, for example demo.planttracer.com::

    $ git clone --recurse-submodules https://github.com/Plant-Tracer/webapp.git demo.planttracer.com

3. Change to the local repository directory::

    $ cd demo.planttracer.com

4. Make or use a Python Virtual Environment (venv).

   * If you want to create a new venv to use when working with this repository::

   $ make venv

   * If you'd prefer to use a pre-existing venv (not recommended for deployment)::

   $ ln -s ~/venv/planttracer venv # or whatever location you keep your venvs

   * Active the venv::

   $ . venv/bin/activate

5. Install the prerequisites with make install-<your-os>, e.g.::

    $ make install-ubuntu

6. If using a pre-created MySQL database, copy etc/credential_template.ini to etc/credentials.ini and fill in the fields for `[client]`, `[dbreader]` and `[dbwriter]`. 

   * Do not add any other .ini files to the repo. etc/credentials.ini is blocked by the .gitignore file, but it can be overridden.

7. If not using a pre-created MySQL database, you may automatically create a new local database named actions_test::

   $ export MYSQL_ROOT_PASSWORD=testrootpass
   $ make create_localdb

8. Run the self-tests::

   $ make pytest-quiet

9. Create your first course! If you want, give it a demo account too::

   $ python dbmaint.py --create_course "My Course Name" --admin_email your_admin_email@company.com --admin_name "Your Name" [--demo_email your_demo_email@company.com]
   course_key: leact-skio-proih

   * You now have a course key! If the demo account is made, you have that too.

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

