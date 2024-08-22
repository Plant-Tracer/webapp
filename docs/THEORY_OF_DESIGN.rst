Web app theory of design
========================

Authentication
--------------

Users are authenticated with an `api_key`:

* Generated server-side with `to_base64(rand())` and stored in the users table.

* New ones can be requested by entering an email address on a web form. The key and several URLs with the key embedded are sent to the email address.

* Generating a new api_key kills the old one.

* api_keys expire after 6 months.

* api_keys are embedded in HTML pages using the template system, making the key accessible to JavaScript running on the page. The global variable is `pt_api_key`.

Use Stories
-----------

Upload a file
^^^^^^^^^^^^^

1 - User goes to https://app.digitalcorpora.org/ and enters their email address into a text field. This sends them a new API key and a set of URLs. One of the URL is `upload a plant movie`. Another is `view uploaded movies.`

  - Requies the ability to send mail from the server that won't be trapped by anti-spam.

  - Eventually, we will also be able to log in with Google and then see the page with the URLs.

2 - User clicks the `upload a plant movie` url. This brings the user to another page that has a HTML FORM Upload with the api_key as one of the parameters. This should work for uploading any movie under 10MB. It won't give a nice progress bar unless we use a clever JavaScript uploader.

View/Edit/Delete upload files
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1 - User clicks on link with embedded API key

2 - Web page is generated server-side with template engine.
    * Upload new movie link
    * pop-up with the section that the student is in.
    * Section showing movies, with a note if it is 'playable' or 'needs review'
    * Section showing deleted movies, with days until movie is purged.

  - To delete a movie, click a check that says "delete." This moves the movie to the "deleted" section. Movies in the deleted section can't be played and are automatically deleted in 7 days, but they can be undelted as well.

  - Movie metadata is in text fields. To change it, just change the text. Making a change to the text enables a "save" button at the end of the line. If you try to navigate away from the page without saving, you get a warning. (JavaScript)

Faculty interface
^^^^^^^^^^^^^^^^^
  * Each faculty member can be in any number of sections
  * Shows all students assigned to each of their section, and all unassigned students.
  * Allows students to be moved between sections and unassigned.
  * Shows all uploaded movies for each section and allows them to be publisehd or unpublished.


API
---

Upload a file
^^^^^^^^^^^^^

1 - User goes to app.digitalcorpora.org/upload

2 - User fills out form with movie title, description, and chooses movie.

3 - Form 'onchange' fires.

  3a - JavaScript hashes movie.

  3b - /api/movie-upload-start gets api_key, title, description, sha256, movie length

  3c - bottle_app.movie_upload_start() calls db.create_movie which creats the movie entry with this sha256.

  3d - if the sha256 already exists, return to the client with 'movie_id' and 'upload_url' equal to '' and 'movie_url' being the final movie URL.

  3e - If the sha256 does not exist, return to the client with 'movie_id' and a 'upload_url' being a presigned s3 upload URL and 'movie_url' being the final movie URL.
  
  Now, if the client has an upload_url, it starts the upload with a POST.
