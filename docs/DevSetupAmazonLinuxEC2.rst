Developer Setup on Amazon Linux 2023 on AWS EC2
===============================================

For more complete instructions, Simson Garfinkel has generously provided us with lab notes from one of his Harvard Extension courses.

See `CSCI E-11 Spring 2025 Lab #1 <https://docs.google.com/document/d/1bSqXSuKfL3TWN_RDS-hhkt9NVz8eRDuSaLUcGVvCeGg/edit?tab=t.0>` to create an AWS account, and to startup and configure an EC2 instance, and to install git.

See `CSCI E-11 Spring 2025 Lab #3 <https://docs.google.com/document/d/1R_HqlwB-O1QHPdMWNxx9ZjYSsL4CDSmpvTK4fE8Xmyk/edit?tab=t.0#heading=h.rv7641iuwu2>` to further configure the EC2 VM, install Apache Server, create and install an SSL certificate, and create an empty webapp.

These two labs have information that form the foundation of how Plant-Tracer/webapp is currently deployed on EC2, and thus we can follow the lab instructions to set up an EC2 instance to use for either development or deployment. Of course, skip the few steps that are specific to the goals and infrastructure of that course, such as -- in Lab 1, Steps 15 and 16 that concern doing an aws s3 cp command, and the end part about finding an access hack.

Lab 1 Summary and Modifications
-------------------------------

To summarize the instance setup described in Lab #1, once the EC2 instance is running and we have ssh'd into the instance, do:

.. code-block::

    sudo yum -y install git
    sudo yum -y install emacs # optional
    # edit /etc/systemd/journald.conf so that MaxRetentionSec=6month
    sudo systemctl restart systemd-journald

Lab 3 Summary and Modifications
-------------------------------

* Modify your instance's Security Group to allow inbound HTTP and HTTPS IPv4 traffic from anywhere (0.0.0.0).

* set the hostname to something, perhaps your-userid.planttracer.com::

    sudo hostnamectl hostname your-userid.planttracer.com

* Install Apache HTTP Server

.. code-block::

    sudo dnf -y install httpd mod_ssl sqlite #we aren't using sqlite, maybe don't do this?
    sudo systemctl enable httpd.service
    sudo systemctl start httpd.service
    sudo systemctl status httpd.service

* Test Apache HTTP Server by browsing to http://your-instances-public-IPv4-address. Should see "It Works!" page.

* Install a Let's Encrypt certificate::

    sudo mkdir /home/ec2-user/www
    sudo chown ec2-user /home/ec2-user/www

* Create /etc/httpd/conf.d/your-username.conf with contents::

<VirtualHost *:80>
    ServerName your-username.planttracer.com
    DocumentRoot /home/ec2-user/www
</VirtualHost>

* Next::

    sudo systemctl restart httpd.service


