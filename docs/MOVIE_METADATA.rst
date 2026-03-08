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

- Researchers can determine which videos may be used in studies and under
  what attribution (by name or anonymous).
- Choices are stored both in the application database (DynamoDB) and as
  object metadata on the uploaded file in S3, so that the same terms travel
  with the data and can be audited later.
- The presigned S3 upload includes these metadata fields in the signature, so
  the client cannot change attribution or research-use after the server has
  issued the upload; the object stored in S3 matches what was consented to.

The two main choices are:

1. **Research use** — Whether the uploaded movie may be used in academic
   research. If not selected, the video is for course use only and is not
   intended for research.
2. **Credit by name** — If research use is allowed, whether the student wants
   to be credited by name. If yes, a "Name for attribution" value is stored.
   If no, the video may still be used in research but anonymously.

Implementation
==============

Upload form
-----------

- **Checkbox 1:** "The uploaded movie may be used in academic research."
  When unchecked, the video is not for research use; the second checkbox and
  name field are hidden.

- **Checkbox 2:** Shown only when checkbox 1 is checked. "I would like credit
  by name for the use of this video in research." If unchecked, the video may
  be used in research anonymously; the "Name for attribution" field is disabled
  and shows the placeholder "In the text."

- **Name for attribution:** Text field, shown when research use is allowed.
  Enabled only when "credit by name" is checked; otherwise disabled with
  placeholder "In the text."

UI logic is implemented in ``sync_attribution_ui()`` in ``src/app/static/planttracer.js``,
with the form markup in ``src/app/templates/upload.html``.

API and database
----------------

- **Endpoint:** ``POST /api/new-movie`` accepts (in addition to existing
  parameters) form fields: ``research_use`` (``"1"`` or omitted), ``credit_by_name``
  (``"1"`` or omitted), and ``attribution_name`` (string).

- **Storage:** The movie record in DynamoDB (see ``schema.Movie`` and
  ``odb.create_new_movie``) stores:

  - ``research_use``: 0 or 1
  - ``credit_by_name``: 0 or 1
  - ``attribution_name``: string or null (only meaningful when ``credit_by_name == 1``)

- **Validation:** ``credit_by_name == 0`` forces ``attribution_name`` to
  null on the server. Existing movies without these fields are treated as
  default 0 / null (see ``schema.Movie`` defaults and ``fix_movie_prop_value``).

Presigned S3 upload and object metadata
---------------------------------------

- **Presigned post:** ``s3_presigned.make_presigned_post()`` takes
  ``research_use``, ``credit_by_name``, and ``attribution_name`` (as strings
  for the form). These are added to both ``Fields`` and ``Conditions`` so that
  the presigned POST signature binds the client to those exact values.

- **S3 object metadata:** The same values are sent as S3 user metadata in the
  POST body using the keys:

  - ``x-amz-meta-research-use`` (e.g. ``"0"`` or ``"1"``)
  - ``x-amz-meta-credit-by-name`` (e.g. ``"0"`` or ``"1"``)
  - ``x-amz-meta-attribution-name`` (string; empty when not attributed by name)

  Because they are in the presigned ``Fields``, the client must send these
  exact values when uploading; the object in S3 therefore carries the same
  research and attribution metadata as the DynamoDB record.

- **Client:** ``upload_movie_post()`` in ``planttracer.js`` sends
  ``research_use``, ``credit_by_name``, and ``attribution_name`` to
  ``/api/new-movie``. The API returns a presigned post whose ``fields``
  already contain the signed metadata; the client posts those fields (and the
  file) to S3 without modifying them.

Traceability
------------

- **DynamoDB:** Each movie row has ``research_use``, ``credit_by_name``, and
  ``attribution_name`` for queries and reporting.
- **S3:** Each object has the same information in ``x-amz-meta-*``, so that
  exports, copies, or downstream systems can enforce or display attribution
  and research-use without relying solely on the application database.
