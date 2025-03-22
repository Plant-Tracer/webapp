Developer Setup
===============

Requirements and Preparation
----------------------------

* GitHub: In order to commit to the `Plant-Tracer/webapp <https://github.com/Plant-Tracer/webapp>` GitHub repository, you must first have a GitHub account. Then your GitHub account must be added as a member of the Plant-Tracer Organization. You may ask any of the Organization owners to do that, or send an email request to plantadmin@planttracer.com.
 
* While there are multiple ways to authenticate a login to  GitHub, it has proven to be convenient for development purposes to use a Personal Access Token for acccess via a command line. See `<https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens>` and `<https://github.com/settings/personal-access-tokens>` for more details. (Specific token settings not yet fully documented, but you want Read and Write access to Contents. Depending on your role and your own toolset, you may also want access to Actions, Discussions, Pages, and Pull Requests, but also consider whether all those permissions should exist in the same PAT.)

* Select your development platform. This will likely have to do with the machines that are available for your use. Plant-Tracer/webapp is being deployed on a Linux host, so that's going to be the best place for runtime debugging. MacOS works well. Windows is not favored, but may work. This file was developed on MacOS Sonoma but should be fine for Ubuntu and other Linuxes. See other doc files such as :doc: `DevSetupUbuntu` and :doc: `WindowsDevSetup` for more detail on setting up on those platforms.

* Install the following things on your development machine, in roughly the order presented, if they aren't already there. How to do that is beyond the scope of this document.

* Chrome web browser. While you can use most web browsers with Plant-Tracer/webapp, only Google Chrome and Chromium are used for application testing. So when dealing with development issues, make sure that work on Chrome before getting concerned about other browsers.

* Package installer. Have a package installer.
    * Homebrew. If installing on a MacOS machine, `HomeBrew <https://brew.sh>`_ must be installed prior to performing the steps below.
    * Chocolatey. If installing on a Windows machine, the Chocolatey package manager is recommended.
    * For Linux, use whatever is the favored package manager for that distro. For Ubuntu, it will be apt.

* Python3.11. Verify that typing 'python' gives you python3.11. If it doesn't, make sure that your PATH is up-to-date.

   * On ubuntu, sudo apt install python3.11-venv (if venv not available by default)

* make

* git and gh

* MySQL 8.0. See :doc:`MySQLSetup`
    
Setup Steps
-----------
#. Set your Git Hub name and username::
    git config --global --edit

#. Authenticate to GitHub. This steps to do this differs per platform, but probably involves install the gh (GitHub) CLI. See the platform specific Dev setup instructions for details of how to install gh. For example::

    gh auth login
    [ec2-user@dev-seb webapp]$ gh auth login
    ? Where do you use GitHub? GitHub.com
    ? What is your preferred protocol for Git operations on this host? HTTPS
    ? Authenticate Git with your GitHub credentials? Yes
    ?How would you like to authenticate GitHub CLI? Paste an authentication token
    ? Tip: you can generate a Personal Access Token here https://github.com/settings/tokens
    ? The minimum required scopes are 'repo', 'read:org', 'workflow'.
    ? Paste your authentication token: ***************************************************- gh - - gh config set -h github.com git_protocol https
    ✓ Configured git protocol
    ! Authentication credentials saved in plain text
    ✓ Logged in as yourusername

#. Clone the Plant Tracer webapp into a directory that will be the local repository, for example::

    git clone https://github.com/Plant-Tracer/webapp.git webapp

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
       export PLANTTRACER_CREDENTIALS=deploy/etc/credentials-localhost.ini
       make create_localdb

#. Run the self-tests:

   .. code-block::

    make pytest-quiet

#. Create your first course! If you want, give it a demo account too:

   * "My Course Name" is the name of the course you are creating. A course in PlantTracer is for a specific delivery of a course, or perhaps a section of a course. PlantTracer assets published in a course are available to all course members.

   * --admin-email is the email address for the first course administrator. It is useful to have a unique email address for the administrator role. For example, if your email address is joecool@company.com, then an admin email address might be joecool+admin@company.com

   * --admin-name "Your Name" should be unique for each admin registration. This is not absolutely necessary but it is helpful to tell under which account you have logged in when using PlantTracer.

   * --demo_email is the email address for a demo user. A demo user is logged in by default when the PlantTracer server is started in demo mode. Omit this parameter if there is no need to use this course in demo mode.

   .. code-block::

    python dbutil.py --create_course "My Course Name" --admin_email your_admin_email@company.com --admin_name "Your Name" [--demo_email your_demo_email@company.com]
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

#. Run Plant-Tracer/webapp locally using the database created above and the credentials file already specified in the PLANTTRACER_CREDENTIALS environment variable

   .. code-block::

    make run-local # Ctrl-C to quit

#. To run a Plant-Tracer/webapp server process locally, examine the debug-* targets in Makefile. The general form is:

   .. code-block::

    python standalone.py [arguments]

#. A specific case: running with movies stored in MySQL rather than S3:

   .. code-block::

    python standalone.py --storelocal

#. Another case: running in demo mode, with movies stored in MySQL rather than S3:

   * Note: there must be no user logged in for demo mode to take effect. May have to clear browser cookies.

   .. code-block::

       DEMO_MODE=1 python standalone.py --storelocal

#. Sometimes, it is necessary to manually clear the cookies that Plant-Tracer/webapp creates in a browser. These cookies are of the form "api_key-"+my_database_name. Here is an example:

.. image:: media/PlantTracerCookieExample.png
