Plant-Tracer/webapp Releases
============================

Release History
---------------

.. list-table:: Releases
   :header-rows: 1

   * - Name
     - Version
     - Date
     - Issues
   * - Spring 2024
     - 0.9.2
     - May 19 2024
     - Not tracked yet
   * - Oct2024
     - 0.9.3
     - October 8, 2024
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/issues?q=is%3Aissue+is%3Aclosed+milestone%3AOct2024>`__
   * - Dec2024
     - 0.9.4
     - December ??, 2024
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/issues?q=is%3Aissue+is%3Aclosed+milestone%3ADec2024>`__
   * - Mar2025
     - 0.9.5
     - March 22, 2025
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/issues?q=is%3Aissue+is%3Aclosed+milestone%3AMar2025>`__
   * - Apr2025
     - 0.9.6
     - April 30, 2025
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/issues?q=is%3Aissue+is%3Aclosed+milestone%3AApr2025>`__
   * - April2026
     - 0.9.7
     - April 26, 2026
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/releases/tag/ver-0.9.7>`__
   * - May062026
     - 0.9.7.3
     - May 8, 2026
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/releases/tag/ver-0.9.7.3>`__
   * - May122026
     - 0.9.7.4
     - May 12, 2026
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/releases/tag/ver-0.9.7.4>`__
   * - May-16-2026
     - 0.9.7.5
     - May 16, 2026
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/releases/tag/ver-0.9.7.5>`__
   * - May-16-2026-2
     - 0.9.7.5.1
     - May 16, 2026
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/releases/tag/ver-0.9.7.5.1>`__
   * - May-27-2026
     - 0.9.7.6
     - May 27, 2026
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/releases/tag/ver-0.9.7.6>`__
   * - May-28-2026
     - 0.9.7.6.2
     - May 28, 2026
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/releases/tag/ver-0.9.7.6.2>`__
   * - Jun-22-2026
     - 0.9.8
     - June 22, 2026
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/releases/tag/ver-0.9.8>`__
   * - Jun-23-2026
     - 0.9.8.1
     - June 23, 2026
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/releases/tag/ver-0.9.8.1>`__
   * - Jun-29-2026
     - 0.9.8.2
     - June 29, 2026
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/releases/tag/ver-0.9.8.2>`__

Release Notes
-------------

Unreleased Summary
******************
    * Developer: add ``src/dbbackup.py`` for default full and selective Plant Tracer ``.ptb`` backups, restores, archive inspection, dry-run restore-link sending, and course migration
    * Developer: add verbose backup inspection with per-record summaries and grouped frame-trackpoint ranges
    * Developer: add ``dbbackup list-prefixes`` to discover complete DynamoDB table prefixes and report course/user/movie counts
    * Developer: make ``dbbackup list-prefixes`` offer ``aws sso login`` and retry when AWS SSO token retrieval fails
    * Test: add integration contract coverage for backup selection, default full backup, prefix discovery, restore preflight/commit/collision handling, dry-run restore links, verbose inspection, and course migration using DynamoDB Local and MinIO
0.9.8.2 Summary
***************
    * Documentation: new Calculation Reference page covering gravitropism and circumnutation statistics formulas
    * Documentation: styled to match the Plant Tracer site fonts and colors
    * Documentation: updated User Tutorial to cover 0.9.8.x features
    * Infrastructure: CloudFormation/SAM template and Makefile hardened for deployment

0.9.8.1 Summary
***************
    * Analyze: Download Trackpoints CSV now expresses position values in mm when Ruler markers are calibrated (moved off their default positions); Ruler marker columns remain in pixels
    * Analyze: Download analysis as an Excel XLSX file with marker summary and native Excel charts

0.9.8 Summary
*************
    * Analyze: aggregate trace result statistics — Gravitropism (Distance, Angle) and Circumnutation (Max Amplitude), selectable via a results control
    * Analyze: special Inflection Point marker used as the pivot for the gravitropism Angle
    * Analyze: Rate statistics, computed from a user-entered capture interval (frames/minute) set on the Upload or Analyze page
    * Analyze: trackpoints now use a bottom-left coordinate system; position graphs unflipped; lazy migration of existing movies made concurrency-safe
    * Analyze: multi-marker graphing with per-marker colors
    * Analyze/Movies: video trimming — trace and export a selected frame range
    * Movies: deleting a user also removes their course enrollments (no more ghost enrollment IDs)
    * Documentation: developer docs reorganized under docs/Development/; updated upload tutorial; corrected MOVIE_METADATA references
    * Process: release-process improvements — pre-tag make check, scripted release notes, and commit/PR issue-traceability requirements

0.9.7.6.2 Summary
*****************
    * Analyze: fix Download Trackpoints CSV — was nearly empty and opened in a browser tab instead of downloading
    * Analyze: Download Trackpoints button now correctly enabled after tracing completes
    * Analyze: movie canvas no longer resets to 100% zoom after tracing completes

0.9.7.6 Summary
****************
    * Movies: fix bug where all students could see unpublished movies of other students
    * Movies: new uploads are now Published by default
    * Movies: movie tables now sorted newest-first by default
    * Movies: sortable columns via DataTables; table style matches Marker table on Analyze page
    * Movies: added Research Use and Credit columns, editable by uploader
    * Upload: research permission changed from checkbox to Yes/No radio buttons
    * Upload: research use option now references a Contributor Agreement
    * Upload: attribution name field pre-filled with user's display name
    * Analyze: clarified RulerXXmm marker naming rules on page and in tutorial
    * Developer: Jest coverage threshold enforced locally via ``npm run coverage``
    * Developer docs: added Release Process documentation
    * Process: documentation review required when completing any Issue or PR

0.9.7.5.1 Summary
******************
    * Process: document annotated tag convention and linked issue numbers in release notes
    * Process: improve release process documentation in CLAUDE.md

0.9.7.5 Summary
***************
    * Users: fix several regressions — listing, formatting, duplicate sections, First/Last Seen columns
    * Users: add names support to bulk registration
    * Users: fix HTTP 500 error when registering a user
    * Documentation: update User Tutorial to current prod functionality
    * Documentation: update DynamoDB schema documentation; create Flask API endpoint reference
    * Email: improve login email template HTML for better client compatibility
    * Dev: add MAILER_DRY_RUN env variable and Mailpit local SMTP catcher for local email testing
    * Dev: add PostToolUse hook to auto-check Sphinx docs build after editing docs/
    * Process: document release process (milestone prep, tagging, release notes) in CLAUDE.md

0.9.7.4 Summary
***************
    * Movies: fix exceptions when editing movie name or user fields
    * Movies: show accurate movie status values
    * Users: fix ReferenceError for bulk_register_setup
    * Users: fix HTTP 500 error when registering a user
    * Analyze: fix Download Trackpoints button not enabled
    * Analyze: fix position graphs not taking up full canvas size
    * Audit: fix Internal Server Error and ReferenceError
    * Alerts: show with more spacing and yellow background
    * Copyright: extend to 2026
    * Research permission: update privacy policy

0.9.7.3 Summary
***************
    * Documentation: update User Tutorial for new instance
    * UI: match webapp look and feel to planttracer.com
    * Developer docs: move to docs/Development/ subfolder
    * Test: add canvas_tracer_controller.js unit tests

0.9.7 Summary
*************
    * Upload/Analyze: move Rotate Movie function to Upload page; fix bugs
    * Upload/Analyze: resize movie to 640x480 (max in either dimension) on upload
    * dbutil: convert to DynamoDB; add report and test-mail functions; improve register
    * Infra: move tracking code to AWS Lambda function
    * Infra: replace MySQL with Amazon DynamoDB
    * Infra: build and deploy using AWS Cloud Formation and SAM
    * Infra: make local development environment easier to work with
    * Infra: migrate to poetry and improve test coverage

0.9.6 Summary
*************
    * Analyze: move some instructions to top of page for easier visibility
    * Analyze: make it clearer in the UI that users don't have to add any new markers in order to track a movie
    * Register: trim surrounding whitespace from Course Key input
    * Movies: Course admins can now publish movies that they uploaded themselves
    * Users: implement bulk registration of users
    * dbutil: set course max_enrollment default to 50
    * Webapp: add git information to web page footer
    * Webapp: set the version (release) number in one place
    * Infra: require cronie package on Amazon Linux 2 deployments

0.9.5 Summary
*************
    * Analyze: support pixels to mm conversion
    * Analyze: populate Marker Table's Location (mm) column
    * Analyze: flip the sign of the y-position graph
    * Documentation: create the User Tutorial
    * Documentation: create (incomplete) developer setup instructions for Amazon Linux 2
    * Movie Upload: set upload limit to 150MB
    * Test: Create Jest unit tests for all planttracer.js functions
    * Webapp: migrate from Bottle to Flask
    * Infra: support deployment to Amazon Web Services (AWS) EC2 instance
    * Infra: support deployment of multiple webapp server instances to project AWS account

0.9.4 Summary
*************

    * dbmaint: add ``add-admin`` and ``remove-admin`` commands

0.9.3 Summary
*************

    * Analyze: Add two line graphs of plant motion: x vs time and y vs time
    * Analyze: *Download Trackpoints* button is fixed
    * Analyze: Default Ruler markers are at 0 and 10 mm, rather than 0 and 20 mm
    * Analyze: Add explanatory text
    * Analyze: Add *rotate movie 90°* function
    * Analyze: Fix several movie tracking errors and hangs
    * Movies list: in demo mode is consistent with demo mode capabilities -- a single list with no categories
    * Demo Mode: All functions not available in demo mode removed from the UI while in demo mode
    * Movies list: publish/unpublish control now are now described as buttons rather than checkboxes
    * Movies list: publish/unpublish/delete/undelete buttons now properly refresh the page
    * List and Analyze: Move some movie processing from server to client
    * List and Analyze: Movie playback no longer flashes
    * Users: page cleanup
    * Audit: populate Audit Log section of page; was errroneously always empty
    * Menu: Show Users page, show Register and Resend when not logged in, adjust for demo mode, add Help
    * Copyright and Terms of Use: page cleanup
    * dbmaint: help documentation cleanup
    * Documentation: converted from Markup to ReStructuredText. Index created.
    * Documentation: update and make more complete
    * Documentation: Installation steps updated
    * Documentation: Add ReleaseHistory page
