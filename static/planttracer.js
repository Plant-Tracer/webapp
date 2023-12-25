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
        .fail(function(xhr, status, error) {
            $('#message').html(`POST error: `+xhr['responseText']);
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
            $('#message').html('Response: ' + data['message']);
        })
        .fail(function(xhr, status, error) {
            $('#message').html(`POST error: `+xhr['responseText']);
            console.log("xhr:",xhr);
        });
}

////////////////////////////////////////////////////////////////
/// page: /upload
/// Enable the movie-file upload when we have at least 3 characters of title and description
function check_upload_metadata()
{
    const title = $('#movie-title').val();
    const description = $('#movie-description').val();

    $('#movie-file').prop('disabled', (title.length < 3 || description.length < 3));
}

// Uploads an entire movie at once using an HTTP POST
// https://stackoverflow.com/questions/5587973/javascript-upload-file
const UPLOAD_TIMEOUT_SECONDS = 20;
async function upload_movie(inp)
{
    const title = $('#movie-title').val();
    const description = $('#movie-description').val();

    console.log('title.length=',title.length);
    if (title.length < 3) {
        $('#message').html('<b>Movie title must be at least 3 characters long');
        return;
    }

    if (description.length < 3) {
        $('#message').html('<b>Movie description must be at least 3 characters long');
        return;
    }

    $('#message').html(`Uploading image...`);
    console.log("upload_movie inp=",inp);
    const movieFile = inp.files[0];
    if (movieFile.fileSize > MAX_FILE_UPLOAD) {
        $('#message').html(`That file is too big to upload. Please chose a file smaller than ${MAX_FILE_UPLOAD} bytes.`);
        return;
    }
    console.log('movieFile:',movieFile);
    let formData = new FormData();
    formData.append("movie",    movieFile); // the movie itself
    formData.append("api_key",  api_key); // on the upload form
    formData.append("title",       title);
    formData.append("description", description);

    const ctrl = new AbortController();    // timeout
    const timeoutId = setTimeout(() => ctrl.abort(), UPLOAD_TIMEOUT_SECONDS*1000);

    try {
        let r = await fetch('/api/new-movie',
                            { method:"POST", body:formData, signal: ctrl.signal });
        console.log("HTTP response code=",r);
        if (r.status!=200) {
            $('#message').html(`<i>Error uploading movie: ${r.status}</i>`);
        } else{
            const body = await r.json();
            console.log('body=',body);
            if (body.error==false ){
                $('#message').html(`<p>Movie ${body.movie_id} successfully uploaded.</p>`+
                                   `<p>First frame:</p>` +
                                   `<img src="/api/get-frame?api_key=${api_key}&movie_id=${body.movie_id}&frame_number=0&format=jpeg">`+
                                   `<p><a href='/analyze?movie_id=${body.movie_id}'>Track movie ${body.movie_id}</a>`+
                                   `   <a href='/list?api_key=${api_key}'>List all movies</a></p>`);
                $('#movie-title').val('');
                $('#movie-description').val('');
                $('#movie-file').val('');
                check_upload_metadata(); // disable the button
            } else {
                $('#message').html(`Error uploading movie. ${body.message}`);
            }
        }
    } catch(e) {
        console.log('Error uploading movie:',e);
        $('#message').html(`Timeout uploading movie -- timeout is currently ${UPLOAD_TIMEOUT_SECONDS} seconds`);
    }
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
SOUNDS[DELETE_BUTTON] = new Audio('static/pop-up-something-160353.mp3');
SOUNDS[UNDELETE_BUTTON] = new Audio('static/soap-bubbles-pop-96873.mp3');



////////////////
// PLAYBACK
// callback when the play button is clicked
function play_clicked( e ) {
    console.log('play_clicked=',e);
    const movie_id = e.getAttribute('x-movie_id');
    const rowid    = e.getAttribute('x-rowid');
    const url = `/api/get-movie-data?api_key=${api_key}&movie_id=${movie_id}`;
    var tr    = $(`#tr-${rowid}`).show();
    var td    = $(`#td-${rowid}`).show();
    var video = $(`#video-${rowid}`).show()
    var vid = video.attr('id');
    //console.log('url=',url);
    //console.log('rowid=',rowid,'movie_id=',movie_id,'tr=',tr,'td=',td,'video=',video,'vid=',vid);
    //video.attr('src',url);
    video.html(`<source src='${url}' type='video/mp4'>`);
    console.log('video=',video);
    document.getElementById( vid ).play();
}

function hide_clicked( e ) {
    var rowid = e.getAttribute('x-rowid');
    var tr    = $(`#tr-${rowid}`).hide();
    var td    = $(`#td-${rowid}`).hide();
    var video = $(`#video-${rowid}`).hide()
}

function analyze_clicked( e ) {
    const movie_id = e.getAttribute('x-movie_id');
    window.location = `/analyze?movie_id=${movie_id}`;
}

////////////////
// DOWNLOAD
// callback when the download button is clicked
function download_clicked( e ) {
    console.log("download ",e);
    const movie_id = e.getAttribute('x-movie_id');

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
            if (data['error']!=false){
                $('#message').html('error: '+data['message']);
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
    t = document.getElementById(target);       // element of the target
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
    t.addEventListener('blur', function(e) {
        finished_editing();
    });
}

////////////////////////////////////////////////////////////////
//
// CREATE THE MOVIES tables
// Create the movies table
// top-level function is called to fill in all of the movies tables
// It's called with a list of movies
// https://developer.mozilla.org/en-US/docs/Web/HTML/Element/video

// Function called when an action button is clicked
function action_button_clicked( e ) {
    const movie_id = e.getAttribute('x-movie_id');
    const property = e.getAttribute('x-property');
    const value    = e.getAttribute('x-value');
    const kind     = e.getAttribute('value');
    sound = SOUNDS[ kind ];
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


function list_movies_data( movies ) {
    const PUBLISHED = 'published';
    const UNPUBLISHED = 'unpublished'
    const DELETED = 'deleted';
    const COURSE = 'course';

    let tid = 0;  // Every <td> on the page has a unique id
    let rowid = 0;// Every row on the page has a unique number

    // movies_fill_div() - creates the
    // This fills in the given table with a given list
    function movies_fill_div( div, which, mlist ) {
        // Top of table
        let h = "<table>";
        if (mlist.length > 0 ){
            h += "<thead>";
            h += "<tr> <th>id</th> <th>user</th>  <th>uploaded</th> <th>title</th> <th>description</th> <th>status and action</th> </tr>";
            h += "</thead>";
        }
        h+= "<tbody>";

        // This produces two HTML <tr>'s for each movie of the table.
        // The first has metadata, which may be editable.
        // The second is by default hidden; it becomes visible to play the movie
        function movie_html( m ) {
            // This products the HTML for each <td> that has text
            rowid += 1;
            var movie_id = m.movie_id;
            function make_td_text(property, text) {
                // for debugging:
                // return `<td> ${text} </td>`;
                tid += 1;
                var r = `<td> <span id='${tid}' x-movie_id='${movie_id}' x-property='${property}'> ${text} </span>`;
                // check to see if this is editable;
                if (admin || user_id == m.user_id){
                    r += `<span class='editor' x-target-id='${tid}' onclick='row_pencil_clicked(this)'> ✏️  </span> </td>\n`;
                }
                return r;
            }
            // This products the HTML for each <td> that has a checkbox
            function make_td_checkbox(property, value) {
                // for debugging:
                // return `<td> ${property} = ${value} </td>`;
                tid += 1;
                let ch = value > 0 ? 'checked' : '';
                return `<td class='check'> <input id='${tid}' x-movie_id='${movie_id}' x-property='${property}' ` +
                    `type='checkbox' ${ch} onclick='row_checkbox_clicked(this)'> </td>\n`;
            }

            // action buttons are HTML buttons that when clicked change the metadata in a predictable way.
            function make_action_button( kind ) {
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

            var movieDate = new Date(m.date_uploaded * 1000);
            var play      = `<input class='play'    x-rowid='${rowid}' x-movie_id='${movie_id}' type='button' value='play' onclick='play_clicked(this)'>`;
            var analyze   = `<input class='analyze' x-rowid='${rowid}' x-movie_id='${movie_id}' type='button' value='analyze' onclick='analyze_clicked(this)'>`;
            var up_down   = movieDate.toLocaleString().replace(' ','<br>').replace(',','');

            var you       = (m.user_id == user_id) ? "you" : "";

            rows = `<tr class='${you}'>`
                + `<td> ${movie_id} </td> <td class='${you}'> ${m.name} <br> ${play} ${analyze} </td> <td> ${up_down} </td>`
                + make_td_text( "title", m.title) + make_td_text( "description", m.description);

            rows += "<td>";
            rows += "Status: ";
            if (m.deleted) {
                rows += "<i>Deleted</i>";
            } else {
                rows += m.published ? "<b>Published</b> " : "Not published";
            }
            rows += "<br/>";

            // below, note that 'admin' is set by the page before this runs

            if (m.deleted) {
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
            rows += "</td></tr>\n";

            // Now make the player row
            rows += `<tr    class='movie_player' id='tr-${rowid}'> `
                  + `<td    class='movie_player' id='td-${rowid}' colspan='6' >`
                  + `<video class='movie_player' id='video-${rowid}' controls playsinline></video>`
                  + `<input class='hide' x-movie_id='${movie_id}' x-rowid='${rowid}' type='button' value='hide' onclick='hide_clicked(this)'></td>`
                  + `</tr>\n`;
            return rows;
        }

        if (mlist.length>0){
            mlist.forEach( m => ( h += movie_html(m) ));
        } else {
            h += '<tr><td><i>No movies</i></td></tr>';
            h += '<tr><td><a href="/upload">Click here to upload a movie</a></td></tr>';
        }

        h += "</tbody>";
        h += "</table>";
        div.html(h);
    }
    movies_fill_div( $('#your-published-movies'),   PUBLISHED, movies.filter( m => (m['user_id']==user_id && m['published']==1)));
    movies_fill_div( $('#your-unpublished-movies'), UNPUBLISHED, movies.filter( m => (m['user_id']==user_id && m['published']==0 && m['deleted']==0)));
    movies_fill_div( $('#course-movies'),           COURSE, movies.filter( m => (m['course_id']==user_primary_course_id)));
    movies_fill_div( $('#your-deleted-movies'),     DELETED, movies.filter( m => (m['user_id']==user_id && m['published']==0 && m['deleted']==1)));
    $('.movie_player').hide();
}

// Gets the list from the server of every movie we can view and displays it in the HTML element
// It's called from the document ready function and after a movie change request is sent to the server.
// The functions after this implement the interactivity
//
function list_movies() {
    $('#message').html('Listing movies...');

    let formData = new FormData();
    formData.append("api_key",  api_key); // on the upload form
    fetch('/api/list-movies', { method:"POST", body:formData })
        .then((response) => response.json())
        .then((data) => {
            //console.log("data:",data);
            if (data['error']!=false){
                $('#message').html('error: '+data['message']);
            } else {
                list_movies_data( data['movies'] );
                $('#message').html('');
            }
        })
        .catch(console.error)
}

////////////////////////////////////////////////////////////////
// page: /audit
// This could fill in the table with search keys; right now we just search for everything
function build_audit_table() {
    let formData = new FormData();
    formData.append("api_key",  api_key); // on the upload form
    fetch('/api/get-logs', { method:"POST", body:formData })
        .then((response) => response.json())
        .then((data) => {
            if (data['error']!=false){
                $('#message').html('error: '+data['message']);
                return
            }
            console.log("data=",data);
            let logs = data['logs'];
            console.log("logs=",logs);
            // get the columns
            var columns = [];
            for (const key in logs[0]) {
                //console.log(`${key}: ${logs{key}}`);
                columns.push( {'data':key, 'title':key } );
            }
            // make the data displayable
            $('#audit').DataTable( {
                columns: columns,
                data: logs
            });
        });
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
    };
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
            if (data['error']!=false){
                $('#message').html('error: '+data['message']);
                return;
            }
            var course_array = [];
            data['courses'].forEach( course => (course_array[course.course_id] = course ));
            list_users_data( data['users'], course_array);
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
