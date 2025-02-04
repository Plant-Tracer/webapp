Setting Up Plant-Tracer webapp on Ubuntu 24
===========================================

- Install ubuntu server (example from ARM 24.01 LTS (on UTM on MacOS))::

    sudo apt update
    sudo apt upgrade
    sudo apt install git
    sudo apt install zsh
    sudo apt install curl
    sudo apt-get install -y nodejs
    sudo apt install python3
    sudo apt install gh
    sudo apt install spice-vdagent
    sudo apt install chromium-browser
    sudo apt-get install lynx
    sudo apt install slim
    sudo apt install ubuntu-desktop
    sudo apt install make
    sudo apt install python3.10-venv
    sudo apt install mysql-server -y
    sudo systemctl enable mysql
    sudo systemctl start mysql
    sudo systemctl status mysql
    sudo mysql_secure_installation
    sudo mysql -uroot
    sudo apt-get install python3.11
    sudo apt install python3.11-venv
    # Ubuntu 24.01 ships with python3.10. We need python 3.11 or greater.
    # this all left mysql root only available via local sudo (auth_socket plugin), and our Makefile wants command line
    # access with a root password, so set that up:
    sudo mysql -uroot
    FLUSH PRIVILEGES;
    ALTER USER 'root'@'localhost' IDENTIFIED BY 'password' PASSWORD EXPIRE NEVER;
    ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY 'password';
    # because it kept saying my password failed validation checks but so far as I could tell it shouldn't have.
    UNINSTALL COMPONENT 'file://component_validate_password';
    quit;
    sudo systemctl stop mysql
    sudo systemctl start mysql

- Edit Makefile so that make venv uses python3.11 rather than python3

- Now proceed with the relevant :doc: `DeveloperSetup` steps::

    make venv
    . venv/bin/activate
    make create_localdb
    make pytest-quiet
    python dbutil.py --create_course "Dev" --admin_email sbarber2+admin@gmail.com --admin_name "Steve Admin Barber"
    creating course...
    course_key: cb6c-40d7

-  add [client] and [smtp] and [imap] sections to deploy/etc/credential-localhost.ini then::

    make run-local

