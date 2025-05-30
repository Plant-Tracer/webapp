Installation
============

Requirements and Preparation
----------------------------
* A home directory on Dreamhost (or another web hosting provider) that provides passengers, or some other wsgi-based approach for running a Python Bottle app (e.g. `mod_wsgi` on Apache).

* A MySQL database with three users defined in a mysql credentials file:

    * ``[client]`` which can modify the schema
    * ``[dbreader]`` which can read the database
    * ``[dbwriter]`` which can write the database

* Ensure that python3.11 installed. Verify that typing 'python' gives you python3.11. If it doesn't, make sure that your PATH is up-to-date.

  - Python is installed automatically using brew on MacOS if not present, using the steps in this document.

Installation
------------

#. Log into the user on the web provider and move the hosting directory into a different directory; we will be replacing it. In this case our directory is `demo.plantracer.com`::

    $ mv demo.planttracer.com demo-old

#. Clone the planttracer web app into the hosting directory, for example demo.planttracer.com::

    $ git clone --recurse-submodules https://github.com/Plant-Tracer/webapp.git demo.planttracer.com

#. Change to the local repository directory::

    $ cd demo.planttracer.com

#. Make Python Virtual Environment (venv)::

   $ make venv

#. Activate the venv::

   $ . venv/bin/activate

#. Install the prerequisites with make install-<your-os>, e.g.::

    $ make install-ubuntu

#. Copy etc/credential_template.ini to etc/credentials.ini and fill in the fields for ``[client]``, ``[dbreader]`` and ``[`dbwriter]``.

   * Do not add any other .ini files to the repo. etc/credentials.ini is blocked by the .gitignore file, but it can be overridden.

#. Create a new local database (named actions_test)::

   $ export MYSQL_ROOT_PASSWORD=testrootpass
   $ make create_localdb

#. Run the self-tests::

   $ PLANTTRACER_CREDENTIALS=etc/credentials.ini make pytest-quiet

#. Create your first course! If you want, give it a demo account too:

   .. code-block::

    $ PLANTTRACER_CREDENTIALS=etc/credentials.ini python dbmaint.py --create_course "My Course Name" --admin_email your_admin_email@company.com --admin_name "Your Name" [--demo_email your_demo_email@company.com]
    course_key: leact-skio-proih

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

Push to Lambda
--------------

.. code-block::

    cd gits/webapp
    source venv/bin/activate
    zappa status dev
    make update-dev


* If this is the first time the zappa function was published, update the DNS to point to the new API Gateway URL.

  For example, this `zappa status dev` shows that dev.planttracer.com should be a CNAME for uga7dh2bxj.execute-api.us-east-1.amazonaws.com.

.. code-block::

	API Gateway URL:      https://uga7dh2bxj.execute-api.us-east-1.amazonaws.com/dev
	Domain URL:           https://dev.planttracer.com
