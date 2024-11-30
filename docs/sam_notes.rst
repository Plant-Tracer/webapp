Notes on Deploying to SAM
=========================


Commands to try:
----------------

`sam sync --stack-name planttracer-webapp --watch`
* Deploys watching your local file system; changes are reflected on the live system, but do not persist after you ^c. In testing, a change in the local file system was reflected in less than 5 seconds on the server.
