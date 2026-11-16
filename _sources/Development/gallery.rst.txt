Gallery Of Plant Videos
=======================

This is a future feature note.

Purpose
-------

A gallery would let users browse course-visible or public movies by title,
uploader, course, date, and research-use status. Thumbnails should come from
lambda-resize first-frame responses, and playback should use signed S3 URLs.

Current Storage Model
---------------------

* Movie metadata is in DynamoDB ``movies`` rows.
* Original movies and generated artifacts are in S3/MinIO.
* Flask should return searchable metadata.
* lambda-resize should return first-frame thumbnails and signed playback URLs.
* Flask should not stream movie bytes.

Implementation Direction
------------------------

* Add or extend a Flask metadata API for gallery search.
* Reuse ``/resize-api/v1/first-frame`` for thumbnails.
* Reuse ``/resize-api/v1/movie-data?format=json`` for playback URLs.
* Respect the same access rules as ``/api/list-movies`` and direct movie access.
* Add meaningful tests against DynamoDB Local and MinIO.
