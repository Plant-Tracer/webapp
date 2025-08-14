Setting Up Plant-Tracer webapp on Ubuntu 24.04
==============================================

- Install ubuntu server (example from `ARM 24.04.2 LTS <https://cdimage.ubuntu.com/releases/24.04/release/>` (on UTM on MacOS)) then::

    sudo apt update
    sudo apt upgrade
    sudo apt install git gh python3.11 python3.11-venv make openjdk-17-jdk awscli
    git config --global --edit #set Git name and username/email for commits
    gh auth login # generate Personal Access Token if necessary
    git clone https://github.com/Plant-Tracer/webapp.git webapp
    cd webapp
    make install-ubuntu

- You might install these for making your developer time easier::

    sudo apt install zsh
    sudo apt-get install -y nodejs
    sudo apt install net-tools
    sudo apt install spice-vdagent
    sudo apt install chromium-browser
    sudo apt-get install lynx
    sudo apt install slim
    sudo apt install ubuntu-desktop
    # Ubuntu 24.01 ships with python3.10. We need python 3.11 or greater.

-  Add [client] and [smtp] and [imap] sections to deploy/etc/credential-localhost.ini then::

    export PLANTTRACER_CREDENTIALS=deploy/etc/credential-localhost.ini
    make start_local_minio
    make start_local_dynamodb
    make make-local-bucket
    make make-local-demo
    make run-local-debug

- This will output a URL to login to the demo course that allows editing -- of the form::

    *****
    ***** Login with http://localhost:8080/list?api_key=ab3bc1e2673a647e08d8b1283e8484293
    *****

- To stop the Plant Tracer server, Ctrl-C out of it.

- To stop the local DynamoDB and Minio, and delete the database entirely::

    make delete-local

- There is some more information in :doc:`DeveloperSetup` document.
