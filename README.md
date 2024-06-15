[![codecov](https://codecov.io/gh/Plant-Tracer/webapp/graph/badge.svg?token=YRMITDBBJ1)](https://codecov.io/gh/Plant-Tracer/webapp)
<a href="https://scan.coverity.com/projects/plant-tracer-webapp">
  <img alt="Coverity Scan Build Status"
       src="https://scan.coverity.com/projects/29728/badge.svg"/>
</a>
# webapp
Client for web-based JavaScript app; Server for python-based backend

This repo provides the custom-written Python code to for the https://app.planttracer.com/ website.

The top-level planttracer.com website is currently a static HTML site. This repo runs in a sub-domain https://app.planttracer.com/ and provides the app that runs in a browser on a mobile phone or desktop.

The repo is designed to be check out as ~/app.planttracer.com/ on a Dreamhost user account. It runs the python application in Bottle using the Dreamhost Passenger WSGI framework. The repo can also be checked out into other domain directories for development and testing on the website. You can also check it out locally and run a local webserver.

## Linux

This application was written with Linux as the target platform, and the Makefile is Linux-specific.

## Windows
It will run on Windows but not have all the features enabled compared to when it is run on Linux.

To run bottle_app.py on Windows (assuming no POSIX-compliant command line there):
Prequisities:
- Python 3.11
- pip or pip3
```
pip install -r requirements.txt
pip install -r requirements-windows.txt
python3 bottle_app.py
```

## MacOS

Most things should just work on MacOS as well, though that's not a specifically targetted platform for either development or runtime.


Future notes:
https://ianwhitestone.work/zappa-zip-callbacks/



The error you're encountering, ImportError: libGL.so.1: cannot open shared object file: No such file or directory, indicates a missing system dependency related to graphics libraries. Unfortunately, directly installing libraries like libGL.so.1 on Amazon Lambda isn't feasible due to its limited environment.

 Here are some solutions for working with OpenCV and computer vision on Zappa and Lambda:

 1. Use opencv-python-headless:

 This version of OpenCV, available on PyPI, builds without graphics dependencies like OpenGL. Install it in your requirements.txt:

 opencv-python-headless
 This is typically the preferred solution as it reduces your Lambda deployment size and avoids unnecessary dependencies.

 2. Consider alternative libraries:

 If your application involves tasks not requiring extensive graphical processing, explore alternative libraries with smaller footprints and no graphics dependencies. Examples include:

Pillow: For basic image manipulation.
Tenserflow Lite: For deploying pre-trained machine learning models for tasks like object detection.
 3. Use AWS DeepLens instead of Lambda:

 AWS DeepLens is a specialized service designed for deploying computer vision applications. It provides a complete environment with GPU support and pre-installed necessary libraries like OpenCV.

 Additional considerations:

Ensure your environment variables and any custom code are compatible with Lambda's limitations.
Test your application thoroughly on a local machine before deploying to Lambda.
Keep your Lambda functions optimized for performance and cost.
 Remember to choose the solution that best fits your specific application requirements and constraints of the Lambda environment.


# Lambda and S3
Lamda limits returns to 6MB and uploads to around 256K. So large uploads are done with presigned POST to S3 and large downloads by putting the data into S3 and having it pulled with a presigned URL.
