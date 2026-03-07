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
   * - Mar2024
     - 0.9.5
     - March 22, 2025
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/issues?q=is%3Aissue+is%3Aclosed+milestone%3AMar2025>`__
   * - Apr2024
     - 0.9.6
     - April 30, 2025
     - `Closed Issues <https://github.com/Plant-Tracer/webapp/issues?q=is%3Aissue+is%3Aclosed+milestone%3AApr2025>`__


Release Notes
-------------

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

    * dbmaint: add --add_admin and --remove_admin commands

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
