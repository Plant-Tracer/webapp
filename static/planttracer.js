"use strict";
/* jshint esversion: 8 */
/*global api_key */
/*global admin */
/*global user_id */
/*global user_primary_course_id */
/*global planttracer_endpoint */
/*global MAX_FILE_UPLOAD */
/*global user_demo */


const PLAY_LABEL = 'play original';
const PLAY_TRACKED_LABEL = 'play tracked';
const UPLOAD_TIMEOUT_SECONDS = 20;

////////////////////////////////////////////////////////////////
// For the demonstration page
function add_func() {
    let a = parseFloat($('#a').val());
    let b = parseFloat($('#b').val());
    $('#sum').html( a + b );
}

////////////////////////////////////////////////////////////////
///  page: /register
///  page: /resend

// Implements the registration web page
function register_func() {
    const email = $('#email').val().toLowerCase();
    if (email=='') {
        $('#message').html("<b>Please provide an email address</b>");
        return;
    }
    let course_key = $('#course_key').val();
    if (course_key=='') {
        $('#message').html("<b>Please provide a course key</b>");
        return;
    }
    let name = $('#name').val();
    if (name=='') {
        $('#message').html("<b>Please provide a name</b>");
        return;
    }
    $('#message').html(`Asking to register <b>${email}</b> for course key <b>${course_key}<b>...</br>`);
    $.post('/api/register', {email:email, course_key:course_key, planttracer_endpoint:planttracer_endpoint, name:name})
        .done( function(data) {
            console.log("register data=",data);
            if (data.error){
                $('#message').html(`<b>Error: ${data.message}`);
            } else {
                $('#message').html(`<b>${data.message}</b>`);
            }})
        .fail( function(xhr, _status, _error) {
            $('#message').html("POST error: "+xhr.responseText);
            console.log("xhr:",xhr);
        });
}

// Implements the resend a link web page
function resend_func() {
    let email = $('#email').val().toLowerCase();
    if (email=='') {
        $('#message').html("<b>Please provide an email address</b>");
        return;
    }
    $('#message').html(`Asking to resend registration link for <b>${email}</b>...</br>`);
    $.post('/api/resend-link', {email:email, planttracer_endpoint:planttracer_endpoint})
        .done(function(data) {
            $('#message').html('Response: ' + data.message);
        })
        .fail(function(xhr, status, error) {
            $('#message').html(`POST error: `+xhr.responseText);
            console.log("xhr:",xhr,"status:",status,"error:",error);
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

// This is an async function, which uses async functions.
// You get the results with
//        var sha256 = await computeSHA256(file);
async function computeSHA256(file) {
    // Read the file as an ArrayBuffer
    const arrayBuffer = await file.arrayBuffer();

    // Compute the SHA-256 hash
    const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);

    // Convert the hash to a hexadecimal string
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    return hashHex;
}

// Uploads a movie using a presigned post. See:
// https://aws.amazon.com/blogs/compute/uploading-to-amazon-s3-directly-from-a-web-or-mobile-application/
// https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html
async function upload_movie_post(movie_title, description, movieFile, showMovie)
{
    var movie_data_sha256 = await computeSHA256(movieFile);
    let formData = new FormData();
    formData.append("api_key",     api_key);   // on the upload form
    formData.append("title",       movie_title);
    formData.append("description", description);
    formData.append("movie_data_sha256",  movie_data_sha256);
    formData.append("movie_data_length",  movieFile.fileSize);
    console.log("sending:",formData);
    let r = await fetch('/api/new-movie', { method:"POST", body:formData});
    console.log("App response code=",r);
    let obj = await r.json();
    console.log('new-movie obj=',obj);
    if (obj.error){
        $('#message').html(`Error getting upload URL: ${obj.message}`);
        return;
    }

    // https://stackoverflow.com/questions/13782198/how-to-do-a-put-request-with-curl
    // https://stackoverflow.com/questions/15234496/upload-directly-to-amazon-s3-using-ajax-returning-error-bucket-post-must-contai/15235866#15235866
    try {
        const pp = obj.presigned_post;
        console.log("pp:",pp)
        const formData = new FormData();
        for (const field in pp.fields) {
            formData.append(field, pp.fields[field]);
        }
        formData.append("file", movieFile); // order matters!

        const ctrl = new AbortController();    // timeout
        setTimeout(() => ctrl.abort(), UPLOAD_TIMEOUT_SECONDS*1000);
        const r = await fetch(pp.url, {
            method: "POST",
            body: formData,
        });
        console.log("uploaded movie. r=",r);
        if (!r.ok) {
            $('#message').html(`Error uploading movie status=${r.status} ${r.statusText}`);
            console.log("r.text()=",await r.text());
            return;
        }
        showMovie(movie_title,obj.movie_id);
    } catch(e) {
        console.log('Error uploading movie to S3:',e);
        $('#message').html(`Timeout uploading movie -- timeout is currently ${UPLOAD_TIMEOUT_SECONDS} seconds`);
    }
}

function show_movie(movie_title, movie_id)
{
    let first_frame = `/api/get-frame?api_key=${api_key}&movie_id=${movie_id}&frame_number=0&format=jpeg`;
    $('#message').html(`<p>Movie ${movie_id} successfully uploaded.</p>`+
                       `<p>First frame:</p> <img src="${first_frame}">`+
                       `<p><a href='/analyze?movie_id=${movie_id}'>Track uploaded movie '${movie_title}' (${movie_id})</a><br/>`+
                       `<a href='/list?api_key=${api_key}'>List all movies</a></p>`);
    // Clear the movie uploaded
    $('#movie-title').val('');
    $('#movie-description').val('');
    $('#movie-file').val('');
    check_upload_metadata(); // disable the button
};


/* Finally the function that is called when a movie is picked */
function upload_movie()
{
    const movie_title = $('#movie-title').val();
    const description = $('#movie-description').val();
    const movieFile = $('#movie-file').prop('files')[0];
    console.log("movieFile=",movieFile);

    if (movie_title.length < 3) {
        $('#message').html('<b>Movie title must be at least 3 characters long');
        return;
    }

    if (description.length < 3) {
        $('#message').html('<b>Movie description must be at least 3 characters long');
        return;
    }

    if (movieFile.fileSize > MAX_FILE_UPLOAD) {
        $('#message').html(`That file is too big to upload. Please chose a file smaller than ${MAX_FILE_UPLOAD} bytes.`);
        return;
    }
    $('#message').html(`Uploading image...`);

    upload_movie_post(movie_title, description, movieFile, show_movie);
}


////////////////////////////////////////////////////////////////
/// page: /list


// special buttons
const PUBLISH_BUTTON='PUBLISH';
const UNPUBLISH_BUTTON='UNPUBLISH';
const DELETE_BUTTON='DELETE';
const UNDELETE_BUTTON='UNDELETE';

// sounds for buttons
var SOUNDS = [];
SOUNDS[DELETE_BUTTON]   = new Audio('static/pop-up-something-160353.mp3');
SOUNDS[UNDELETE_BUTTON] = new Audio('static/soap-bubbles-pop-96873.mp3');

////////////////
// PLAYBACK
// callback when the play button is clicked
function play_clicked( e, movie_id ) {
    console.log('play_clicked=',e,'movie_id=',movie_id);
    const url = `/api/get-movie-data?api_key=${api_key}&movie_id=${movie_id}`;
    //const movie_id = e.getAttribute('x-movie_id');
    const rowid    = e.getAttribute('x-rowid'); // so we can make it visible
    $(`#tr-${rowid}`).show();
    const td = $(`#td-${rowid}`);

    // Delete any existing video player
    td.html('');
    // Create a new video player
    td.html(`<video class='movie_player' id='video-${rowid}' controls playsinline><source src='${url}' type='video/mp4'></video>` +
            `<input class='hide' x-movie_id='${movie_id}' x-rowid='${rowid}' type='button' value='hide' onclick='hide_clicked(this)'>`);
    td.show();
    const video = $(`#video-${rowid}`).show();
    const vid   = video.attr('id');
    //console.log('url=',url);
    //console.log('rowid=',rowid,'movie_id=',movie_id,'tr=',tr,'td=',td,'video=',video,'vid=',vid);
    //video.attr('src',url);
    //video.html(``);
    console.log('video=',video);
    document.getElementById( vid ).play();
}

function hide_clicked( e ) {
    let rowid = e.getAttribute('x-rowid');
    let video = $(`#video-${rowid}`);
    video.hide();
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
    console.log(`set_property(${user_id}, ${movie_id}, ${property}, ${value})`);
    let formData = new FormData();
    formData.append("api_key",  api_key); // on the upload form
    if (user_id) formData.append("set_user_id", user_id);
    if (movie_id) formData.append("set_movie_id", movie_id);
    formData.append("property", property);
    formData.append("value", value);
    fetch('/api/set-metadata', { method:"POST", body:formData})
        .then((response) => response.json())
        .then((data) => {
            if (data.error!=false){
                $('#message').html('error: '+data.message);
            } else {
                list_movies();
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
    const t = document.getElementById(target);       // element of the target
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
const TABLE_HEAD = "<tr> <th>id</th> <th>user</th>  <th>uploaded</th> <th>title</th> <th>description</th> <th>Size</th> <th>status and action</th> </tr>";

function list_movies_data( movies ) {
    const PUBLISHED = 'published';
    const UNPUBLISHED = 'unpublished';
    const DELETED = 'deleted';
    const COURSE = 'course';

    let tid = 0;  // Every <td> on the page has a unique id
    let rowid = 0;// Every row on the page has a unique number

    // movies_fill_div() - creates the
    // This fills in the given table with a given list
    function movies_fill_div( div, which, mlist) {
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
                var r = `<td> <span id='${tid}' x-movie_id='${movie_id}' x-property='${property}'> ${text} </span>`;
                // check to see if this is editable;
                if ((admin || user_id == m.user_id) && user_demo==0) {
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

            // Get the metadata for the movie
            const movieDate = new Date(m.date_uploaded * 1000);
            const play      = `<input class='play'    x-rowid='${rowid}' x-movie_id='${movie_id}' type='button' value='${PLAY_LABEL}' onclick='play_clicked(this,${movie_id})'>`;
            let playt = '';
            let analyze_label = 'analyze';
            if (m.tracked_movie_id){
                playt     = `<input class='play'    x-rowid='${rowid}' x-movie_id='${m.tracked_movie_id}' type='button' value='${PLAY_TRACKED_LABEL}' onclick='play_clicked(this,${m.tracked_movie_id})'>`;
                analyze_label = 're-analyze';
            }
            const analyze   = m.orig_movie ? '' : `<input class='analyze' x-rowid='${rowid}' x-movie_id='${movie_id}' type='button' value='${analyze_label}' onclick='analyze_clicked(this)'>`;
            const up_down   = movieDate.toLocaleString().replace(' ','<br>').replace(',','');

            const you_class = (m.user_id == user_id) ? "you" : "";

            let rows = `<tr class='${you_class}'>` +
                `<td> ${movie_id} </td> <td class='${you_class}'> ${m.name} </td> <td> ${up_down} </td>` + // #1, #2, #3
                make_td_text( "title", m.title, "<br/>" + play + playt + analyze ) + make_td_text( "description", m.description, '') + // #4 #5
                `<td> frame: ${m.width} x ${m.height} Kbytes: ${Math.floor(m.total_bytes/1000)} ` +
                `<br> fps: ${m.fps} frames: ${m.total_frames} </td> `;  // #6

            rows += "<td> Status: "; // #7
            if (m.deleted) {
                rows += "<i>Deleted</i>";
            } else {
                rows += m.published ? "<b>Published</b> " : "Not published";
            }
            rows += "<br/>";

            // below, note that 'admin' is set by the page before this runs

            // Create the action buttons if not user demo
            if (user_demo) {
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
                if ((m.published==0) && ((which==COURSE && admin))){
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

        // Offser to upload movies if not in demo mode.
        if (!user_demo) {
            h += '<tr><td colspan="6"><a href="/upload">Click here to upload a movie</a></td></tr>';
        }

        h += "</tbody>";
        h += "</table>";
        div.html(h);
    }
    // Create the four tables
    movies_fill_div( $('#your-published-movies'),
                     PUBLISHED, movies.filter( m => (m.user_id==user_id && m.published==1 && !m.orig_movie)));
    movies_fill_div( $('#your-unpublished-movies'),
                     UNPUBLISHED, movies.filter( m => (m.user_id==user_id && m.published==0 && m.deleted==0 && !m.orig_movie)));
    movies_fill_div( $('#course-movies'),
                     COURSE, movies.filter( m => (m.course_id==user_primary_course_id && m.user_id!=user_id && !m.orig_movie)));
    movies_fill_div( $('#your-deleted-movies'),
                     DELETED, movies.filter( m => (m.user_id==user_id && m.published==0 && m.deleted==1 && !m.orig_movie)));
    $('.movie_player').hide();
}

// Gets the list from the server of every movie we can view and displays it in the HTML element
// It's called from the document ready function and after a movie change request is sent to the server.
// The functions after this implement the interactivity
//
function list_movies() {
    console.log("list_movies");
    $('#message').html('Listing movies...');

    let formData = new FormData();
    formData.append("api_key",  api_key); // on the upload form
    fetch('/api/list-movies', { method:"POST", body:formData })
        .then((response) => response.json())
        .then((data) => {
            if (data.error!=false){
                $('#message').html('error: '+data.message);
            } else {
                // Make a map of each movie_id to its position in the array
                var movie_map = new Array()
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
        var d1 = user.first ? new Date(user.first * 1000).toString() : "n/a";
        var d2 = user.last ? new Date(user.last  * 1000).toString() : "n/a";
        var ret = '';
        if (current_course != user.primary_course_id) {
            ret += `<tr><td colspan='4'>&nbsp;</td></tr>\n`;
            ret += `<tr><th colspan='4'>Primary course: ${course_array[user.primary_course_id].course_name} (${user.primary_course_id})</th></tr>\n`;
            ret += '<tr><th>Name</th><th>Email</th><th>First Seen</th><th>Last Seen</th></tr>\n';
            current_course = user.primary_course_id;
        }
        ret +=  `<tr><td>${user.name} (${user.user_id}) </td><td>${user.email}</td><td>${d1}</td><td>${d2}</td></tr>\n`;
        return ret;
    }
    users.forEach( user => ( h+= user_html(user) ));
    h += '</tbody>';
    div.html(h);
}

function list_users()
{
    $('#message').html('Listing users...');
    let formData = new FormData();
    formData.append("api_key",  api_key); // on the upload form
    fetch('/api/list-users', { method:"POST", body:formData })
        .then((response) => response.json())
        .then((data) => {
            if (data.error!=false){
                $('#message').html('error: '+data.message);
                return;
            }
            var course_array = [];
            data.courses.forEach( course => (course_array[course.course_id] = course ));
            list_users_data( data.users, course_array);
        });
}


// Wire up whatever happens to be present
// audit and list are wired with their own ready functions
$( document ).ready( function() {
    $('#load_message').html('');       // remove the load message
    $('#adder_button').click( add_func );
    $('#register_button').click( register_func );
    $('#resend_button').click( resend_func );
});
