Demo Mode
=========

Goals
-----

- Allows anyone on the web to anonymously use some aspects of the Plant Tracer web app. Specifically:

  - View the list of movies

  - Play a movie without tracking

  - Click on 'analyze' to show the user interface for playing a movie that has stored tracks.

  - Download a spreadsheet

- Will not allow:

  - No uploading of videos

  - No deleting of videos

  - No renaming of titles, descriptions

  - No deleting or adding trackpoints

  - No editing any text

Required in the database
------------------------

- Demo mode user with their own API key and course

- Tracked movies in the demo mode user's course

Implementation
--------------

- Only checks for demo mode if ``PLANTTRACER_DEMO_MODE_AVAILABLE`` environment variable is set to 1

- If ``PLANTTRACER_DEMO_MODE_AVAILABLE`` is set and there is no user logged in, then we are in DEMO_MODE

- If we are in DEMO_MODE

  - auth.get_user_api_key()

    - If there is a user logged in, we get that user

    - If there is no user logged in, we get the demo user

    - Once we get the demo user, the web browser's API_KEY cookie will be set to the demo user. So logging out will remove it and the immediately set back it

    - (To get out of demo mode, you'll need to click on a link that has a different API key)

- ``demo`` JavaScript global variable set to ``true`` (if in demo mode)

- ``demo`` Jinja2 variable will get set to ``true`` (otherwise it is ``false``)

Troubleshooting/Development Note
--------------------------------

Plant-Tracer webapp creates an api_key-<database name> cookie in order to tracker
the login state of a session. Sometimes this cookie does not clear itself upon logout
and it is necessary to manually delete the cookie, especially in order to have a valid
demo mode enabled.

Here is an example of such a cookie:

.. image:: media/PlantTracerCookieExample.png
