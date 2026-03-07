Configuring AWS
===============

Type these commands to configure

.. code-block ::

sudo dnf install git emacs


AWS Configuration
=================

.. code-block:: bash

    simsong@Seasons-2 ~ % aws --profile=planttracer s3 ls
    2024-11-16 20:08:45 aws-cloudtrail-logs-343218180669-01fb4321
    2025-11-04 09:39:47 aws-sam-cli-managed-default-samclisourcebucket-qlylwo9umzto
    2024-11-16 18:48:10 planttracer-logs
    2025-04-06 22:15:49 planttracer-prod
    2025-12-16 20:56:09 planttracer2
    2025-11-09 22:35:18 sam-artifacts-343218180669-us-east-1


bucket planttracer-logs -- Cloud Trails logs from legacy Zappa and Lambda functions
bucket planttracer-prod -- Planttracer v1 images
bucket planttracer2     -- Planttracer v2 images, used for testing lambda functions
