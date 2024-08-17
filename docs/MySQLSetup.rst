MySQL Setup for Plant Tracer
============================

Doing development on the Plant Tracer webapp currently requires a MySQL database. While we're not sure later versions of MySQL won't work, the webapp was developed against MySQL 8.0 and recommend using the latest 8.0.x available. Deployment is to and 8.0 server, so if you are making any changes to the database part of the application, it had better work with 8.0.

It's been worth having a local installation of MySQL for development so that developers don't smash into each other trying to share remote database instances that someone else has to administer. Plant Tracer's use of MySQL is fairy straightforward and there's not much admin work to do.

MacOS Development Environment
-----------------------------

Homebrew: Three of us have tried to install MySQL on MacOS with HomeBrew and were unsuccessful, so we recommend going to the MySQL.com download site and downloading a .dmg installer instead.

These instructions assume there is no existing MySQL installation on the machine. If there is, you are assumed to have facility with MySQL already, and on your own to make sure you've configured it properly or maybe having multiple versions of MySQL on your machine. That gets complicated and is beyond the scope of these instructions intended for those new to MySQL admin and development.

Download the .dmg from dev.mysql.com:
  
- Navigate to the MySQL Developer download page at https://dev.mysql.com/downloads/mysql/

- Select Version: 8.0.39 (or whatever the current 8.0.x release is)

- Select Operating System: macOS

- Select OS Version: whatever you have, presumably macOS 14 (ARM, 64 bit)
  
- Press the Download button to the right of *macOS 14 (ARM, 64-bit), DMG Archive*

- If you want, sign Up for an Oracle Web account if you don't already have one, or Login if you do

- But you can just click on the *No thanks, just start my download link underneat the big Login/Sign Up buttons

Install the DMG:

- The MySQL documentation for this procedure is quite good: https://dev.mysql.com/doc/refman/8.0/en/macos-installation-pkg.html
  The following steps are the minimal happy path for a straight installation, assuming no customization is necessary and everything Just Works.

- Double-click on the mysql-8.0.39-macos-arm64.dmg to open the dmg
  
- Double-click on mysql-8.0.39-macos-arm64.pkg to start the installation
  
- On the "The package will run a program to determine if the software can be installed. pop-up, press the Allow button
  
- Press Continue on the Introduction page
  
- Press Continue on the License page
  
- Press Agree on the To continue installing the software you must agree to the terms of the software license agreement page
  
- Press Continue to Install for all users on this computer (or choose a different option)
  
- Press Install on the Installation Type page
  
- Installation page: ???
  
- Leave User Strong Password Encryption selected and then Press Next on the Configuration page
  
- Enter a root password, leave Start MySQL Server once the installation is complete checked, and press Finish. Make sure you have a way to not forget your root password, as it is very annoying to recover from losing it
  
- Press Close on the Summary page

Verify the installation:
  
- On the MacOS System Settings app, search for MySQL
  
- Verify that the Active Instance and Installed Instances have green and not red dots to their left. Green means they are running; Red means they are stopped and if they are start them. But if they go red again, something is not good and troubleshooting is in order

- Consider (strongly consider) making sure the Start MySQL when your computer starts up checkbox is checked

- There is no need to Initialize Database. We'll make a database later when setting up webapp development

- Open a Terminal and execute::

mysqladmin -u root -p
Enter password: (enter root password here)

- If that looks successful -- no errors, great.

- Connect to the server with the mysql client::

mysql -u root -p
Enter password: (enter root password here)

- If you get a mysql> prompt, then the client is able to connect to the server. Also great.
- Enter the quit command to quit the mysql client

- If you've gotten this far, the MySQL installation is in good shape.

