Demo Mode
=========

Goals:

- Allows anyone on the web to anonymously play with the plant tracker app.
- Does not allow creation of objectionable content.
- Does not require resetting after each user
- No need to provide email addresses or obvoiusly log in.

Required:
- Reposition trackpoints and retrack movie

Limitations:
- No uploading of videos
- No deleting of videos
- No renaming of titles, descriptions.
- No deleting or adding trackpoints

Implementation:
- Demo mode template (`templates/demo.html`)
- Demo mode user, with the login template automatically have a link to log in.
- Periodically reload the database.
- A few movies pre-loaded.
- Additional text to drop into the existing templates to help out the user.
- `demo` variable set to `true` if in demo mode.
- `read_only` attribute for users which blocks writability on database metadata for users and movies.
