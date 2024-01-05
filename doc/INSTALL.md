Installation
============

Requirements and Preparation
----------------------------
* A home directory on Dreamhost (or another web hosting provider) that provides passengers, or some other wsgi-based approach for running a Python Bottle app (e.g. `mod_wsgi` on Apache).
* A MySQL database with three users defined in a mysql credentials file:
  * `[client]` which can modify the schema
  * `[dbreader]` which can read the database
  * `[dbwriter]` which can write the database.
* python3.11 installed. Verify that typing 'python' gives you python3.11. If it doesn't, make sure that your PATH is up-to-date.

Installation
------------
1. Log into the user on the web provider and move the hosting directory into a different directory; we will be replacing it. In this case our directory is `demo.plantracer.com`:
    $ mv demo.planttracer.com demo-old

2. Clone the planttracer web app into the hosting directory:

    $ git clone --recurse-submodules https://github.com/Plant-Tracer/webapp.git demo.planttracer.com

3. Install the prerequisits with make install-<your-os>, e.g.:

    $ make install-ubuntu

4. Copy etc/credential_template.ini to etc/credentials.ini and fill in the fields for `[client]`, `[dbreader]` and `[dbwriter]`.

5. Now you need to create the database. This should be pretty automatic:

   $ python dbmaint.py --readconfig etc/credentials.ini --load_schema

6. Run the self-tests

   $ make pytest-quiet

7. Create your first course! If you want, give it a demo account too:

   $ python dbmaint.py --create_course "Demo Course Name" --admin_email your_admin_email@company.com --admin_name "Your Name" [--create_demo]
   course_key: leact-skio-proih
   $

8. You have a course key! If the demo account is made, you have that too.