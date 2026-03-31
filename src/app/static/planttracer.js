"use strict";
/* jshint esversion: 8 */
import { $ } from "./utils.js";



// special buttons
const PUBLISH_BUTTON='PUBLISH';
const UNPUBLISH_BUTTON='UNPUBLISH';
const DELETE_BUTTON='DELETE';
const UNDELETE_BUTTON='UNDELETE';
const PLAY_LABEL = 'play';
const PLAY_TRACKED_LABEL = 'play tracked';
const UPLOAD_TIMEOUT_SECONDS = 600;  // 10 minutes for large files on slow connections

// sounds for buttons
var SOUNDS = [];
if (typeof Audio !== 'undefined') {
  SOUNDS[DELETE_BUTTON] = new Audio('https://planttracer.com/pop-up-something-160353.mp3');
  SOUNDS[UNDELETE_BUTTON] = new Audio('https://planttracer.com/soap-bubbles-pop-96873.mp3');
} else {
  // Provide fallbacks or empty mock objects for testing
  SOUNDS[DELETE_BUTTON] = { play: () => {} };
  SOUNDS[UNDELETE_BUTTON] = { play: () => {} };
}



////////////////////////////////////////////////////////////////
// For the demonstration page
function add_func() {
  const a = parseFloat($('#a').val());
  const b = parseFloat($('#b').val());
  $('#sum').html( a + b );
}

////////////////////////////////////////////////////////////////
///  page: /register
///  page: /resend

// Implements the registration web page
function register_func() {
  const email = $('#email').val().toLowerCase();
  if (email == '') {
    $('#message').html("<b>Please provide an email address</b>");
    return;
  }
  let course_key = $('#course_key').val();
  if (course_key == '') {
    $('#message').html("<b>Please provide a course key</b>");
    return;
  }
  let name = $('#name').val();
  if (name == '') {
    $('#message').html("<b>Please provide a name</b>");
    return;
  }

  $('#message').html(`Asking to register <b>${email}</b> for course key <b>${course_key}</b>...</br>`);

  const payload = {
      email: email,
      course_key: course_key,
      planttracer_endpoint: planttracer_endpoint,
      name: name
  };

  $.post(`${API_BASE}api/register`, payload)
    .done((data) => {
      if (data.error) {
        // Warning: using .html() with server data can be an XSS risk.
        $('#message').html('<b>Error:</b> ' + data.message);
      } else {
        $('#message').html('<b>Success:</b> ' + data.message);
      }
    })
    .fail((error) => {
      $('#message').html("POST error: " + (error.responseText || "Network error"));
      console.error("Register error:", error);
    });
}

// Implements the resend a link web page
function resend_func() {
  let email = $('#email').val().toLowerCase();
  if (email == '') {
    $('#message').html("<b>Please provide an email address</b>");
    return;
  }

  $('#message').html(`Asking to resend registration link for <b>${email}</b>...</br>`);

  const payload = {
      email: email,
      planttracer_endpoint: planttracer_endpoint
  };

  $.post(`${API_BASE}api/resend-link`, payload)
    .done((data) => {
      $('#message').html('Response: ' + data.message);
    })
    .fail((error) => {
      $('#message').html("POST error: " + (error.responseText || "Network error"));
      console.error("Resend error:", error);
    });
}

////////////////////////////////////////////////////////////////
/// page: /upload
/// Enable the movie-file upload when we have at least 3 characters of title and description
/// We also allow uploading other places
function check_upload_metadata()
{
  const title = $('#movie-title').val();
  const description = $('#movie-description').val();
  const movie_file = $('#movie-file').val();
  $('#upload-button').prop('disabled', (title.length < 3 || description.length < 3 || movie_file.length<1));
}

function sync_attribution_ui() {
  if ($('#research-use-checkbox').get(0) == null) {
    return;
  }
  const researchChecked = $('#research-use-checkbox').prop('checked');
  if (researchChecked) {
    $('#attribution-group').show();
    $('#attribution-name-group').show();
    const creditChecked = $('#credit-by-name-checkbox').prop('checked');
    const nameInput = $('#attribution-name');
    if (creditChecked) {
      nameInput.prop('disabled', false);
      nameInput.attr('placeholder', '');
    } else {
      nameInput.prop('disabled', true);
      nameInput.attr('placeholder', 'In the text');
    }
  } else {
    $('#attribution-group').hide();
    $('#attribution-name-group').hide();
    $('#credit-by-name-checkbox').prop('checked', false);
    $('#attribution-name').val('').prop('disabled', true).attr('placeholder', 'In the text');
  }
}

// This is an async function, which uses async functions.
// You get the results with
//        var sha256 = await computeSHA256(file);
async function computeSHA256(file) {
  const arrayBuffer = await file.arrayBuffer();

  // Compute the SHA-256 hash
  const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);

  // Convert the hash to a hexadecimal string
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  return hashHex;
}

/*
 * Get the first frame URL from lambda-resize (get-frame API). Uses LAMBDA_API_BASE.
 * Use size=analysis so the server resizes to the analysis max (e.g. 640x480).
 */
function first_frame_url(movie_id)
{
  return `${LAMBDA_API_BASE}resize-api/v1/first-frame?api_key=${api_key}&movie_id=${movie_id}`;
}

/*
 * Check Lambda status (GET LAMBDA_API_BASE + 'status'). Resolves with true if ok, false otherwise.
 * If LAMBDA_API_BASE is not set, resolves with true (skip check).
 */
async function checkLambdaStatus() {
  try {
    const r = await fetch(LAMBDA_API_BASE + 'resize-api/v1/ping', { method: 'GET' });
    if (!r.ok) return false;
    const data = await r.json();
    return data && data.status === 'ok';
  } catch (e) {
    console.warn('Lambda status check failed', e);
    return false;
  }
}

/*
 * Tell Lambda to start processing the uploaded movie (POST start-processing).
 * If LAMBDA_API_BASE is not set, resolves without calling (local dev).
 */
async function startLambdaProcessing(movie_id) {
  // Processing currently handled on the VM; Lambda control-plane API is disabled for now.
  console.log(`startLambdaProcessing(${movie_id});`);
  return;
}

/*
 *
 * Uploads a movie using a presigned post. See:
 * https://aws.amazon.com/blogs/compute/uploading-to-amazon-s3-directly-from-a-web-or-mobile-application/
 * https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html
 *
 * Presigned post is provided by the /api/new-movie call (see below)
 */
async function upload_movie_post(movie_title, description, movieFile, research_use, credit_by_name, attribution_name)
{
  // If Lambda is configured, ensure it is healthy before starting upload
  if (typeof LAMBDA_API_BASE !== 'undefined' && LAMBDA_API_BASE) {
    const lambdaOk = await checkLambdaStatus();
    if (!lambdaOk) {
      $('#upload_message').html('Processing service is not available. Please try again in a moment.');
      return;
    }
  }
  // Get a new movie_id
  const movie_data_sha256 = await computeSHA256(movieFile);
  const formData = new FormData();
  formData.append("api_key",     api_key);
  formData.append("title",       movie_title);
  formData.append("description", description);
  formData.append("movie_data_sha256",  movie_data_sha256);
  formData.append("movie_data_length",  movieFile.size);
  formData.append("research_use", research_use ? "1" : "0");
  formData.append("credit_by_name", credit_by_name ? "1" : "0");
  formData.append("attribution_name", attribution_name || "");
  const r = await fetch(`${API_BASE}api/new-movie`, { method:"POST", body:formData});
  const obj = await r.json();
  console.log('new-movie obj=',obj);
  if (obj.error){
    $('#message').html(`Error getting upload URL: ${obj.message}`);
    return;
  }
  const movie_id = window.movie_id = obj.movie_id;

  // The new movie_id came with the presigned post to upload the form data.
  // pp.fields includes signed x-amz-meta-* so metadata is set on the S3 object.
  try {
    const pp = obj.presigned_post;
    // #region agent log
    const fieldOrder = Object.keys(pp.fields);
    console.log("[DEBUG]", JSON.stringify({hypothesisId:"H2_H3_H4_H5",location:"planttracer.js:presigned_post",message:"S3 POST params",data:{urlHost:pp.url ? new URL(pp.url).host : null,fieldOrder,fieldCount:fieldOrder.length,fileType:movieFile && movieFile.type,fileName:movieFile && movieFile.name,fileSize:movieFile && movieFile.size},timestamp:Date.now()}));
    // #endregion
    const s3FormData = new FormData();
    for (const field in pp.fields) {
      s3FormData.append(field, pp.fields[field]);
    }
    s3FormData.append("file", movieFile); // order matters!
    // #region agent log
    console.log("[DEBUG]", JSON.stringify({hypothesisId:"H1",location:"planttracer.js:form_built",message:"Form built file last",data:{fieldOrder,fileIsLast:true},timestamp:Date.now()}));
    // #endregion

    const ctrl = new AbortController();
    const startTime = Date.now();
    const timeoutId = setTimeout(() => ctrl.abort(), UPLOAD_TIMEOUT_SECONDS * 1000);
    const formatTime = (sec) => {
      const m = Math.floor(sec / 60);
      const s = Math.floor(sec % 60);
      return `${m}:${s.toString().padStart(2, "0")}`;
    };
    const updateTimer = () => {
      const elapsed = (Date.now() - startTime) / 1000;
      const remaining = Math.max(0, UPLOAD_TIMEOUT_SECONDS - elapsed);
      $('#upload_message').html(
        `Uploading… Elapsed: ${formatTime(elapsed)}, Time left: ${formatTime(remaining)}`
      );
    };
    updateTimer();
    const intervalId = setInterval(updateTimer, 1000);

    let r;
    try {
      r = await fetch(pp.url, {
        method: "POST",
        body: s3FormData,
        signal: ctrl.signal,
      });
    } finally {
      clearInterval(intervalId);
      clearTimeout(timeoutId);
    }
    // #region agent log
    console.log("[DEBUG]", JSON.stringify({hypothesisId:"H3",location:"planttracer.js:after_fetch",message:"S3 response",data:{ok:r.ok,status:r.status,statusText:r.statusText,redirected:r.redirected,url:r.url},timestamp:Date.now()}));
    // #endregion
    if (!r.ok) {
      $('#upload_message').html(`Error uploading movie status=${r.status} ${r.statusText}`);
      return;
    }
    // Phase 2: tell Lambda to start processing (sets date_uploaded etc. so get-frame works)
    await startLambdaProcessing(movie_id);
    // Brief delay so DynamoDB is updated before we poll for first frame
    await new Promise(resolve => setTimeout(resolve, 250));
  } catch (e) {
    // #region agent log
    console.log("[DEBUG]", JSON.stringify({hypothesisId:"H_all",location:"planttracer.js:catch",message:"Upload catch",data:{name:e.name,message:e.message,cause:e.cause?String(e.cause):null},timestamp:Date.now()}));
    // #endregion
    const msg = (e.name === 'AbortError')
          ? `Timeout uploading movie (${UPLOAD_TIMEOUT_SECONDS}s). Try a smaller file or check your connection.`
          : `Upload failed: ${e.message || String(e)}. If you see "Failed to fetch" or connection reset, check that the S3 bucket CORS is set (bootstrap) and the bucket is in the same region as the server (AWS_REGION).`;
    $('#upload_message').html(msg);
    console.log("error: ", e);
    return;
  }
  // Movie was uploaded. Show first frame and rotation on this page; user clicks "Process movie" to go to processing.
  showUploadPreviewAfterUpload(movie_id, movie_title, description);
}

/**
 * Show the upload preview (first frame, rotate, process button) after a successful upload.
 * Does not redirect; user clicks "Process movie" to go to /processing.
 */
function showUploadPreviewAfterUpload(movie_id, movie_title, description) {
  $('#upload_message').html('');
  $('#upload-form-title').html('Movie uploaded');
  $('#upload-instructions').hide();
  $('#uploaded_movie_title').text(description ? `${movie_title} — ${description}` : movie_title);
  $('#movie_id').text(movie_id);
  $('#process_movie_link').attr('href', `/analyze?movie_id=${movie_id}`);
  $('#track_movie_link').attr('href', `/analyze?movie_id=${movie_id}`);
  $('#upload-preview').show();

  const img = $('#image-preview').get(0);
  const statusEl = $('#image-preview-status');
  statusEl.show().text('Loading first frame…');

  const maxAttempts = 12;
  const delayMs = 500;
  let attempt = 0;

  function tryLoadFirstFrame() {
    attempt += 1;
    const url = first_frame_url(movie_id);
    img.onerror = () => {
      if (attempt < maxAttempts) {
        statusEl.text(`First frame not ready (${attempt}/${maxAttempts})…`);
        setTimeout(tryLoadFirstFrame, delayMs);
      } else {
        statusEl.text('First frame could not be loaded. You can click Analyze.');
      }
    };
    img.onload = () => {
      statusEl.text('').hide();
    };
    img.src = url;
  }

  tryLoadFirstFrame();
}

/* Finally the function that is called when the upload_movie button is clicked */
function upload_movie()
{
  const movie_title = $('#movie-title').val();
  const description = $('#movie-description').val();
  const movieFileInput = $('#movie-file');
  const movieFile = movieFileInput.prop('files')[0];
  const research_use = $('#research-use-checkbox').prop('checked');
  const credit_by_name = $('#credit-by-name-checkbox').prop('checked');
  const attribution_name = research_use && credit_by_name ? ($('#attribution-name').val() || '').trim() : '';

  if (movie_title.length < 3) {
    $('#message').html('<b>Movie title must be at least 3 characters long');
    return;
  }

  if (description.length < 3) {
    $('#message').html('<b>Movie description must be at least 3 characters long');
    return;
  }

  if (!movieFile) {
    $('#message').html('<b>Please select a movie file to upload');
    return;
  }

  if (movieFile.size > MAX_FILE_UPLOAD) {
    $('#message').html(`That file is too big to upload. Please chose a file smaller than ${MAX_FILE_UPLOAD} bytes.`);
    return;
  }
  // Hide the form immediately so the user sees that something is happening.
  $('#upload-movie-form').hide();
  $('#upload-button').prop('disabled', true);
  $('#upload_message').html(`Uploading movie ...`);

  upload_movie_post(movie_title, description, movieFile, research_use, credit_by_name, attribution_name);
}

async function _get_movie_metadata(movie_id){
  let formData = new FormData();
  formData.append("api_key",     api_key);   // on the upload form
  formData.append("movie_id",    movie_id);
  const r = await fetch(`${API_BASE}api/get-movie-metadata`, { method:"POST", body:formData});
  if (r.ok) {
    return await r.json()['metadata'];
  }
}


//
// Rotate: debounce multiple clicks (~1s), then send one request with total rotation_steps (1–3).
// Server rotates that many 90° steps and builds the zip in the background.
const ROTATE_DEBOUNCE_MS = 1000;
let rotate_pending = 0;
let rotate_debounce_timer = null;

function rotate_movie() {
  const linkEl = $('#rotate_movie_link').get(0);
  if (!linkEl || linkEl.classList.contains('rotate-pending')) {
    return;
  }
  rotate_pending += 90;
  $('#rotate_status').text(rotate_pending);
  if (rotate_debounce_timer) {
    clearTimeout(rotate_debounce_timer);
  }
  rotate_debounce_timer = setTimeout(() => apply_rotation_and_zip(), ROTATE_DEBOUNCE_MS);
}

let current_rotation = 0;

async function apply_rotation_and_zip() {
    const movie_id = window.movie_id;
    const previewImg = $('#image-preview').get(0);
    const rotateStatus = $('#rotate_status');

    // 1. Update Visuals
    current_rotation = (current_rotation + 90) % 360;
    previewImg.style.transform = `rotate(${current_rotation}deg)`;
    rotateStatus.text(' … Saving rotation…');

    // 2. Point 'Analyze' directly to the analysis page
    $('#process_movie_link').attr('href', `/analyze?movie_id=${movie_id}`);

// 3. Update the backend via /rotate-movie
    try {
        const formData = new FormData();
        formData.append('api_key', api_key);
        formData.append('movie_id', movie_id);   // Matches get_movie_id() [cite: 355]
        formData.append('rotation', String(current_rotation)); // Matches get_int("rotation")

        const r = await fetch(`${API_BASE}api/rotate-movie`, {
            method: 'POST',
            body: formData
        });

        const resp = await r.json();
        if (resp.error) {
            rotateStatus.text(' Error: ' + resp.message);
        } else {
            rotateStatus.text(' (Rotation saved)');
        }
    } catch (e) {
        rotateStatus.text(' Network error updating rotation.');
        console.error("Rotation sync failed:", e);
    }
}

function purge_movie() {
  console.log("purge_movie()");
}

function upload_ready_function() {
  check_upload_metadata();    // disable the upload button
  sync_attribution_ui();      // show/hide attribution fields based on research checkbox
}

////////////////////////////////////////////////////////////////
/// page: /list


////////////////
// PLAYBACK
// callback when the play button is clicked in the movie list.
// Fetches playback URL via format=json so video element can load directly from S3.
function play_clicked( e ) {
  const movie_id = e.getAttribute('x-movie_id');
  const rowid = e.getAttribute('x-rowid');
  const base = (typeof LAMBDA_API_BASE !== 'undefined' && LAMBDA_API_BASE) ? LAMBDA_API_BASE.replace(/\/$/, '') : '';
  if (!base) {
    return;
  }
  // ask the movie-data service for JSON information about the movie,
  // which will be a signed S3 GET URL
  const apiUrl = `${base}/api/v1/movie-data?api_key=${api_key}&movie_id=${movie_id}&format=json`;
  $(`#tr-${rowid}`).show();
  const td = $(`#td-${rowid}`);
  td.html('<span class="loading">Loading…</span>');
  td.show();

  fetch(apiUrl)
    .then(function (resp) {
      if (!resp.ok) {
        return resp.json().then(function (body) {
          throw new Error(body.message || 'Failed to get playback URL');
        }).catch(function (err) {
          if (err.message) throw err;
          throw new Error('Failed to get playback URL (' + resp.status + ')');
        });
      }
      return resp.json();
    })
    .then(function (data) {
      const url = data && data.url;
      if (!url) {
        throw new Error('No URL in response');
      }
      td.html('');
      td.html(`<video class='movie_player' id='video-${rowid}' controls playsinline><source src='${url}' type='video/mp4'></video>` +
              `<input class='hide' x-movie_id='${movie_id}' x-rowid='${rowid}' type='button' value='hide' onclick='hide_clicked(this)'>`);
      td.show();
      const video = $(`#video-${rowid}`);
      const videoEl = video.get(0);
      if (videoEl) {
        videoEl.play();
      }
    })
    .catch(function (err) {
      td.html('<span class="error">' + (err.message || 'Playback failed') + '</span>');
    });
}

function hide_clicked( e ) {
  let rowid = e.getAttribute('x-rowid');
  $(`#video-${rowid}`).hide();
  $(`#tr-${rowid}`).hide();
  $(`#td-${rowid}`).hide();
}

function analyze_clicked( e ) {
  const movie_id = e.getAttribute('x-movie_id');
  window.location = `/analyze?movie_id=${movie_id}`;
}

////////////////
// EDIT METADATA

// This sends the data to the server and then redraws the screen
function set_property(user_id, movie_id, property, value)
{
  console.log(`set_property('${user_id}', ${movie_id}, ${property}, ${value})`);
  let formData = new FormData();
  formData.append("api_key",  api_key); // on the upload form
  if (user_id) formData.append("set_user_id", user_id);
  if (movie_id) formData.append("set_movie_id", movie_id);
  formData.append("property", property);
  formData.append("value", value);
  fetch(`${API_BASE}api/set-metadata`, { method:"POST", body:formData})
    .then((response) => response.json())
    .then((data) => {
      if (data.error!=false){
        $('#message').html('error: '+data.message);
      } else {
        list_ready_function();
      }
    })
    .catch(console.error);
}


// This is called when a checkbox in a movie table is checked. It gets the movie_id and the property and
// the old value and asks for a change. the value 'checked' is the new value, so we just send it to the server
// and then do a repaint.
function row_checkbox_clicked( e ) {
  const user_id  = e.getAttribute('x-user_id');
  const movie_id = e.getAttribute('x-movie_id');
  const property = e.getAttribute('x-property');
  const value    = e.checked ? 1 : 0;
  set_property(user_id, movie_id, property, value);
}

// This function is called when the edit pencil is chcked. It makes the corresponding span editable, sets up an event handler, and then selected it.
function row_pencil_clicked( e ) {
  console.log('row_pencil_clicked e=',e);
  const target = e.getAttribute('x-target-id'); // name of the target
  console.log('target=',target);
  const t = $(target).get(0);       // element of the target
  console.log('t=',t);
  const user_id  = t.getAttribute('x-user_id'); // property we are changing
  const movie_id = t.getAttribute('x-movie_id'); // property we are changing
  const property = t.getAttribute('x-property'); // property we are changing
  const oValue   = t.textContent;                // current content of the text
  t.setAttribute('contenteditable','true');      // make the text editable
  t.focus();                                     // give it the focus

  function finished_editing() {                  // undoes editing and sends to server
    t.setAttribute('contenteditable','false'); // no longer editable
    t.blur();                                  // no longer key
    const value = t.textContent;
    if (value != oValue){
      set_property(user_id, movie_id, property, value);
    } else {
      //console.log(`value unchanged`);
    }
  }

  // handle tab, return and escape
  t.addEventListener('keydown', function(e) {
    if (e.keyCode==9 || e.keyCode==13 ){ // tab or return pressed
      //console.log('tab or return pressed');
      finished_editing();
    } else if (e.keyCode==27){ // escape pressed
      //console.log(`escape pressed. Restore ${oValue}`);
      t.textContent = oValue; // restore the original value
      t.blur();           // does this work?
      t.setAttribute('contenteditable','false'); // no longer editable
    } else {
      // Normal keypress
    }
  });
  // Click somewhere else to finish editing
  t.addEventListener('blur', function(_e) {
    finished_editing();
  });
}

// Function called when an action button is clicked in the movies table
function action_button_clicked( e ) {
  const movie_id = e.getAttribute('x-movie_id');
  const property = e.getAttribute('x-property');
  const value    = e.getAttribute('x-value');
  const kind     = e.getAttribute('value');
  const sound = SOUNDS[ kind ];
  console.log('kind=',kind,'sound=',sound);
  if (sound) {
    sound.play();
  }
  set_property(null, movie_id, property, value);
  // If we deleted the movie, automatically unpublish it
  if (property=='deleted' && value==1){
    set_property(null, movie_id, 'published', 0);
  }
}


////////////////////////////////////////////////////////////////
//
// CREATE THE MOVIES tables
// Create the movies table
// top-level function is called to fill in all of the movies tables
// It's called with a list of movies
// https://developer.mozilla.org/en-US/docs/Web/HTML/Element/video

//                           #1          #2               #3               #4              #5                 #6                #7
const TABLE_HEAD = "<tr> <th>user</th>  <th>uploaded</th> <th>title</th> <th>description</th> <th>size</th> <th>status and action</th> </tr>";

// Phase 3: list shows processing_state. Eventually this list should be server-rendered (Jinja2).
function list_movies_data( movies ) {
  const PUBLISHED = 'published';
  const UNPUBLISHED = 'unpublished';
  const DELETED = 'deleted';
  const COURSE = 'course';

  let tid = 0;  // Every <td> on the page has a unique id
  let rowid = 0;// Every row on the page has a unique number

  // movies_fill_div() - creates the
  // This fills in the given table with a given list
  function movies_fill_div( divSelector, which, mlist) {
    // Top of table
    let h = "<table>";
    if (mlist.length > 0 ){
      h += "<thead>" + TABLE_HEAD + "</thead>";
    }
    h+= "<tbody>";

    // This produces two HTML <tr>'s for each movie of the table.
    // The first has metadata, which may be editable.
    // The second is by default hidden; it becomes visible to play the movie
    function movie_html( m ) {
      const movie_id = m.movie_id;
      rowid += 1;         // each row is separately numbered

      // This products the HTML for each <td> that has text. THe text is optionally editable.
      // If it is editable, clicking the pencil puts it in edit mode and calls row_pencil_clicked()
      // to start the enditing if the pencil is clicked.

      function make_td_text(property, text, extra) {
        // for debugging:
        // return `<td> ${text} </td>`;
        tid += 1;
        let r = `<td> <span id='${tid}' x-movie_id='${movie_id}' x-property='${property}'> ${text} </span>`;
        // check to see if this is editable;
        if ((admin || user_id == m.user_id) && !demo_mode) {
          r += `<span class='editor' x-target-id='${tid}' onclick='row_pencil_clicked(this)'> ✏️  </span> `;
        }
        r += extra + "</td>\n";
        return r;
      }
      // This products the HTML for each <td> that has a checkbox.
      // Clicking the checkbox calls row_checkbox_clicked(this) to change the property on the server
      // and initiate a redraw
      function _make_td_checkbox(property, value) {
        // for debugging:
        // return `<td> ${property} = ${value} </td>`;
        tid += 1;
        let ch = value > 0 ? 'checked' : '';
        return `<td class='check'> <input id='${tid}' x-movie_id='${movie_id}' x-property='${property}' ` +
          `type='checkbox' ${ch} onclick='row_checkbox_clicked(this)'> </td>\n`;
      }

      // action buttons are HTML buttons that when clicked change the metadata in a predictable way.
      function make_action_button( kind ) {
        let nval = undefined;
        let prop = undefined;
        if (kind==PUBLISH_BUTTON) {
          prop = 'published';
          nval = 1;
        } else if (kind==UNPUBLISH_BUTTON) {
          prop = 'published';
          nval = 0;
        } else if (kind==DELETE_BUTTON) {
          prop = 'deleted';
          nval = 1;
        } else if (kind==UNDELETE_BUTTON) {
          prop = 'deleted';
          nval = 0;
        } else {
          console.log("make_action_button: unknown button type: ",kind);
          return "ERROR";
        }
        return `<input type='button' x-movie_id='${movie_id}' x-property='${prop}' value='${kind}' x-value='${nval}' onclick='action_button_clicked(this)'>`;
      }

      // Get the metadata for the movie (date_uploaded is seconds; 0/null = not set yet / processing)
      const dateSec = m.date_uploaded && Number(m.date_uploaded);
      const movieDate = dateSec ? new Date(dateSec * 1000) : null;
      const up_down   = movieDate ? movieDate.toLocaleString().replace(' ','<br>').replace(',','') : '—';
      const play      = `<input class='play'    x-rowid='${rowid}' x-movie_id='${movie_id}' type='button' value='${PLAY_LABEL}' onclick='play_clicked(this)'>`;
      let playt = '';
      let analyze_label = 'analyze';
      if (m.tracked_movie_id){
        playt     = `<input class='play'    x-rowid='${rowid}' x-movie_id='${m.tracked_movie_id}' type='button' value='${PLAY_TRACKED_LABEL}' onclick='play_clicked(this)'>`;
        analyze_label = 're-analyze';
      }
      const analyze   = m.orig_movie ? '' : `<input class='analyze' x-rowid='${rowid}' x-movie_id='${movie_id}' type='button' value='${analyze_label}' onclick='analyze_clicked(this)'>`;

      const you_class = (m.user_id == user_id) ? "you" : "";
      const frameStr = (m.width != null && m.height != null) ? `${m.width} x ${m.height}` : '—';
      const kbytesStr = (m.total_bytes != null && m.total_bytes > 0) ? Math.floor(m.total_bytes / 1000) : '—';
      const fpsStr = (m.fps != null) ? m.fps : '—';
      const framesStr = (m.total_frames != null) ? m.total_frames : '—';

      let rows = `<tr class='${you_class}'>` +
          `<td class='${you_class}'> ${m.user_name} </td> <td> ${up_down} </td>` + // #1, #2, #3
          make_td_text( "title", m.title, "<br/>" + play + playt + analyze ) + make_td_text( "description", m.description, '') + // #4 #5
          `<td> frame: ${frameStr} Kbytes: ${kbytesStr} ` +
          `<br> fps: ${fpsStr} frames: ${framesStr} </td> `;  // #6

      rows += "<td> Status: "; // #7
      // Prefer tracking status when available; otherwise fall back to processing_state.
      let statusLabel = '';
      if (m.status) {
        statusLabel = (m.status === 'TRACKING COMPLETED') ? 'tracked' : 'tracking';
      } else if (m.processing_state) {
        statusLabel = m.processing_state;
      }
      if (statusLabel) {
        rows += `<span class='processing-state'>${statusLabel}</span> `;
      }
      if (m.deleted) {
        rows += "<i>Deleted</i>";
      } else {
        rows += m.published ? "<b>Published</b> " : "Not published";
      }
      rows += "<br/>";

      // below, note that 'admin' is set by the page before this runs

      // Create the action buttons if not user demo
      if (demo_mode) {
        rows += '<i> demo user </i>';
      } else if (m.deleted) {
        if (which==DELETED){
          // Do we create an undelete delete button?
          rows += make_action_button( UNDELETE_BUTTON );
        }
      } else {
        // Do we create an unpublish button?
        if ((m.published) && ((which==PUBLISHED || which==COURSE)) && (m.user_id==user_id || admin)){
          rows += make_action_button( UNPUBLISH_BUTTON );
        }
        // Do we create a publish button?
        if ((m.published==0) && (((which==UNPUBLISHED || which==COURSE) && admin))){
          rows += make_action_button( PUBLISH_BUTTON );
        }
        // Do we create a delete button? (users can only delete their own movies)
        if (m.user_id == user_id){
          rows += make_action_button( DELETE_BUTTON );
        }
      }
      rows += "</td></tr>\n"; // #7 end, <tr>

      // Now make the player row
      rows += `<tr    class='movie_player' id='tr-${rowid}'> `+
        `<td    class='movie_player' id='td-${rowid}' colspan='7' ></td>` +
        `</tr>\n`;
      return rows;
    }

    // main body of movies_fill_div follows

    if (mlist.length>0){
      mlist.forEach( m => ( h += movie_html(m) )); // for each movie in the array, add its HTML (which is two <tr>)
    } else {
      h += '<tr><td><i>No movies</i></td></tr>';
    }

    // Offer to upload movies if not in demo mode.
    if (!demo_mode) {
      h += '<tr><td colspan="6"><a href="/upload">Click here to upload a movie</a></td></tr>';
    }

    h += "</tbody>";
    h += "</table>";
    const divElement = document.querySelector(divSelector);
    if (divElement) {
      divElement.innerHTML = h;
    }
  }
  // Create the four tables
  movies_fill_div( '#your-published-movies',
                   PUBLISHED, movies.filter( m => (m.user_id==user_id && m.published==1 && !m.orig_movie)));
  movies_fill_div( '#your-unpublished-movies',
                   UNPUBLISHED, movies.filter( m => (m.user_id==user_id && m.published==0 && m.deleted==0 && !m.orig_movie)));
  movies_fill_div( '#course-movies',
                   COURSE, movies.filter( m => (m.course_id==user_primary_course_id && (demo_mode || (m.user_id!=user_id)) && !m.orig_movie)));
  movies_fill_div( '#your-deleted-movies',
                   DELETED, movies.filter( m => (m.user_id==user_id && m.published==0 && m.deleted==1 && !m.orig_movie)));
  document.querySelectorAll('.movie_player').forEach(el => el.style.display = 'none');
}

// Gets the list from the server of every movie we can view and displays it in the HTML element
// It's called from the document ready function and after a movie change request is sent to the server.
// The functions after this implement the interactivity
//
function list_ready_function() {
  console.log("list_ready_function()");
  $('#message').html('Listing movies...');

  let formData = new FormData();
  formData.append("api_key",  api_key); // on the upload form
  fetch(`${API_BASE}api/list-movies`, { method:"POST", body:formData })
    .then((response) => response.json())
    .then((data) => {
      if (data.error!=false){
        $('#message').html('error: '+data.message);
      } else {
        // Make a map of each movie_id to its position in the array
        let movie_map = new Array()
        for (let movie of data.movies) {
          movie_map[movie.movie_id] = movie;
        }
        // Now for each movie that is tracked, set the property .tracked_movie_id in the source movie
        for (let movie of data.movies) {
          if (movie.orig_movie) {
            movie_map[movie.orig_movie].tracked_movie_id = movie.movie_id;
          }
        }

        list_movies_data( data.movies );
        $('#message').html('');
      }
    })
    .catch(console.error);
}

////////////////////////////////////////////////////////////////
/// page: /users



function list_users_data( users, course_array ) {
  let current_course = null;
  let div = $('#your-users');
  let h = '<table>';
  h += '<tbody>';
  function user_html(user) {
    let d1 = user.first ? new Date(user.first * 1000).toString() : "n/a";
    let d2 = user.last ? new Date(user.last  * 1000).toString() : "n/a";
    let ret = '';
    if (current_course != user.primary_course_id) {
      ret += `<tr><td colspan='4'>&nbsp;</td></tr>\n`;
      ret += `<tr><th colspan='4'>Primary course: ${course_array[user.primary_course_id].course_name} (${user.primary_course_id})</th></tr>\n`;
      ret += '<tr><th>Name</th><th>Email</th><th>First Seen</th><th>Last Seen</th></tr>\n';
      current_course = user.primary_course_id;
    }
    ret +=  `<tr><td>${user.user_name} (${user.user_id}) </td><td>${user.email}</td><td>${d1}</td><td>${d2}</td></tr>\n`;
    return ret;
  }
  users.forEach( user => ( h+= user_html(user) ));
  h += '</tbody>';
  div.html(h);
}

function list_users()
{
  let formData = new FormData();
  formData.append("api_key",  api_key); // on the upload form
  fetch(`${API_BASE}api/list-users`, { method:"POST", body:formData })
    .then((response) => response.json())
    .then((data) => {
      if (data.error!=false){
        $('#message').html('error: '+data.message);
        return;
      }
      let course_array = [];
      data.courses.forEach( course => (course_array[course.course_id] = course ));
      list_users_data( data.users, course_array);
    });
}

window.helpers = {
  upload_movie,
  rotate_movie,
  play_clicked,
  hide_clicked,
  analyze_clicked,
  row_pencil_clicked,
  action_button_clicked};
// Expose page-ready functions so inline scripts in list.html and upload.html can call them
window.list_ready_function = list_ready_function;
window.upload_ready_function = upload_ready_function;
window.check_upload_metadata = check_upload_metadata;
window.sync_attribution_ui = sync_attribution_ui;
// Expose handlers used by onclick in list.html and upload.html (must be on window for inline handlers)
window.upload_movie = upload_movie;
window.purge_movie = purge_movie;
window.rotate_movie = rotate_movie;
window.play_clicked = play_clicked;
window.analyze_clicked = analyze_clicked;
window.row_pencil_clicked = row_pencil_clicked;
window.action_button_clicked = action_button_clicked;
window.hide_clicked = hide_clicked;

// Wire up whatever happens to be present
// audit, list and upload are wired with their own ready functions
$( document ).ready( function() {
  $('#load_message').html('');       // remove the load message
  $('#adder_button').click( add_func );
  $('#register_button').click( register_func );
  $('#resend_button').click( resend_func );
});

if (typeof module != 'undefined'){
  module.exports = {
    add_func,
    checkLambdaStatus,
    check_upload_metadata,
    computeSHA256,
    first_frame_url,
    list_movies_data,
    list_users,
    list_users_data,
    purge_movie,
    register_func,
    resend_func,
    row_checkbox_clicked,
    set_property,
    upload_movie_post,
    upload_ready_function
  }
}
