Setting Up Plant-Tracer webapp on Ubuntu 24.04
==============================================

- Install ubuntu server (example from `ARM 24.04.2 LTS <https://cdimage.ubuntu.com/releases/24.04/release/>` (on UTM on MacOS)) then::

    sudo apt update
    sudo apt upgrade
    sudo apt install git gh python3.11 python3.11-venv make
    git config --global --edit #set Git name and username/email for commits
    gh auth login # generate Personal Access Token if necessary
    git clone https://github.com/Plant-Tracer/webapp.git webapp
    cd webapp
    make install-ubuntu

You maight install these for making your developer time easier::

    sudo apt install zsh
    sudo apt-get install -y nodejs
    sudo apt install net-tools
    sudo apt install spice-vdagent
    sudo apt install chromium-browser
    sudo apt-get install lynx
    sudo apt install slim
    sudo apt install ubuntu-desktop
    # Ubuntu 24.01 ships with python3.10. We need python 3.11 or greater.

-  add [client] and [smtp] and [imap] sections to deploy/etc/credential-localhost.ini then::

    export PLANTTRACER_CREDENTIALS=deploy/etc/credential-localhost.ini
    make make-local-demo
    make run-local-debug

- Now proceed with the relevant :doc:`DeveloperSetup` steps.
