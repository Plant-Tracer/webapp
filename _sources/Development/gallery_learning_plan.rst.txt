Gallery Learning Plan
=====================

This page is a lightweight learning path for adding or improving gallery-style
pages in the current Flask/Jinja application.

Current Framework
-----------------

Plant Tracer now uses Flask, not Bottle.

Read:

* Flask routing and blueprints: https://flask.palletsprojects.com/
* Jinja templates: https://jinja.palletsprojects.com/
* Existing page routes in ``src/app/flask_app.py``
* Existing templates in ``src/app/templates/``
* Existing browser code in ``src/app/static/planttracer.js``

Exercise
--------

1. Add a Flask route in ``src/app/flask_app.py``.
2. Add a Jinja template in ``src/app/templates/``.
3. Pass page context through ``page_dict()``.
4. Add page-specific JavaScript under ``src/app/static/`` only if needed.
5. Add meaningful Flask or browser tests.
6. Update developer and user docs if the page is user-visible.

Gallery Direction
-----------------

A future gallery should use the existing movie metadata APIs and signed S3 URLs:

* list candidate public/course-visible movies through Flask metadata APIs,
* request playback URLs through lambda-resize movie-data API,
* use lambda-resize first-frame endpoint for thumbnails,
* avoid serving movie bytes through Flask.
