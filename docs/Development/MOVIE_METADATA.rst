========================================
Movie attribution and research metadata
========================================

This document describes how attribution and research-use permissions are
captured for student-uploaded movies, stored, and reflected in object storage
for traceability.

Philosophy
==========

Students retain control over how their uploaded videos may be used in academic
research and whether they receive credit by name. The system records these
choices at upload time so that:

**The S3 bucket outlives the stack** (it is the long-term archive of student
videos; see :doc:`S3`). Therefore metadata must live **in the MP4 file** so
that the object remains self-describing even if the DynamoDB database is gone.

- Researchers can determine which videos may be used in studies and under
  what attribution (by name or anonymous).
- Choices are stored in the application database (DynamoDB), as S3 object
  metadata (x-amz-meta-*), and **in the MP4 file** (comment atom), so that
  the same terms travel with the data and remain valid even if the database
  is removed or migrated.
- The presigned S3 upload includes these metadata fields in the signature, so
  the client cannot change attribution or research-use after the server has
  issued the upload; the object stored in S3 matches what was consented to.

The two main choices are:

1. **Research use** — Whether the uploaded movie may be used in academic
   research.
2. **Credit by name** — If research use is allowed, whether the student wants
   to be credited by name. If yes, a "Name for attribution" value is stored.
   If no, the video may still be used in research but anonymously.

Three-state model
-----------------

Each of ``research_use`` and ``credit_by_name`` is a three-state value:

- ``1`` — explicitly **Yes**
- ``0`` — explicitly **No**
- ``None`` — **not yet answered** (the user did not select a radio button,
  or the record predates the radio-button UI)

The sentinel string ``"not-answered"`` is used when either field has not been
answered in S3 object metadata and MP4 embedded metadata (where ``None`` cannot
be stored directly). Legacy records with ``0`` stored before the radio-button UI
was introduced are treated as an explicit *No* (the original checkbox was
visible to the user and they chose not to check it).

Implementation
==============

Upload form
-----------

- **Research use** — Yes/No radio group. Neither option is pre-selected,
  leaving the value as *not answered* until the student makes a choice.

- **Credit by name** — Yes/No radio group. Shown only when research use is
  **Yes**. Neither option is pre-selected by default.

- **Name for attribution:** Text field. Shown and enabled only when both
  research use is **Yes** and credit by name is **Yes**.

UI logic is implemented in ``sync_attribution_ui()`` in ``src/app/static/planttracer.js``,
with the form markup in ``src/app/templates/upload.html``.

API and database
----------------

- **Endpoint:** ``POST /api/new-movie`` accepts (in addition to existing
  parameters) form fields: ``research_use`` (``"1"``, ``"0"``, or omitted),
  ``credit_by_name`` (``"1"``, ``"0"``, or omitted), and ``attribution_name``
  (string). Omitted fields are stored as ``None`` in DynamoDB.

- **Storage:** The movie record in DynamoDB (see ``schema.Movie`` and
  ``odb.create_new_movie``) stores:

  - ``research_use``: 1, 0, or None
  - ``credit_by_name``: 1, 0, or None
  - ``attribution_name``: string or null (only meaningful when ``credit_by_name == 1``)

- **Validation:** ``credit_by_name != 1`` forces ``attribution_name`` to
  null on the server.

Presigned S3 upload and object metadata
---------------------------------------

- **Presigned post:** ``s3_presigned.make_presigned_post()`` takes
  ``research_use``, ``credit_by_name``, and ``attribution_name`` (as strings).
  These are added to both ``Fields`` and ``Conditions`` so that the presigned
  POST signature binds the client to those exact values.

- **S3 object metadata:** The same values are sent as S3 user metadata using
  the keys:

  - ``x-amz-meta-research-use`` — ``"1"``, ``"0"``, or ``"not-answered"``
  - ``x-amz-meta-credit-by-name`` — ``"1"``, ``"0"``, or ``"not-answered"``
  - ``x-amz-meta-attribution-name`` — name string, or empty string

  Because they are in the presigned ``Fields``, the client must send these
  exact values when uploading; the object in S3 therefore carries the same
  research and attribution metadata as the DynamoDB record.

- **Client:** ``upload_movie_post()`` in ``planttracer.js`` sends
  ``research_use`` and ``credit_by_name`` only when a radio button has been
  selected (omits the field entirely when *not answered*), and sends
  ``attribution_name`` to ``/api/new-movie``. The API returns a presigned post
  whose ``fields`` already contain the signed metadata; the client posts those
  fields (and the file) to S3 without modifying them.

Traceability
------------

- **DynamoDB:** Each movie row has ``research_use``, ``credit_by_name``, and
  ``attribution_name`` for queries and reporting.
- **S3:** Each object has the same information in ``x-amz-meta-*``, so that
  exports, copies, or downstream systems can enforce or display attribution
  and research-use without relying solely on the application database.

Capture interval (frames per minute)
====================================

The **capture interval** ``fpm`` (frames per minute) is a separate, optional
per-movie value used by the Analyze page to report results per minute of real
time (see :doc:`AnalysisResults` and issues #1056/#1053). It is distinct from the
encoded playback ``fps``.

- **DynamoDB is authoritative.** ``fpm`` is stored as a string on the movie row
  (``schema.Movie.fpm``; ``odb.FPM``) and is what the application reads and edits.
  The user can set it at upload (``/api/new-movie``) or later on the Analyze page
  (``POST /api/set-movie-fpm``); editing it only rescales time/rate and never
  requires retracing.
- **S3 object metadata.** When supplied at upload, ``fpm`` is included in the
  presigned ``Fields`` as ``x-amz-meta-fpm`` (``make_presigned_post``), like the
  attribution fields.
- **MP4 file (best-effort snapshot).** When a movie is processed, the capture
  interval is written into the traced MP4 as a dedicated freeform atom
  (``----:com.planttracer:capture_fpm``; ``mp4_metadata_lib.set_fpm`` /
  ``get_fpm``), separate from the research-attribution comment atom. This is a
  best-effort archival snapshot of the value at processing time; later Analyze-page
  edits update only DynamoDB, so the embedded copy may lag the authoritative row.
  Legacy movies have no atom, which is harmless.
