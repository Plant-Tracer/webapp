////////////////////////////////////////////////////////////////
// For the demonstration page
function add_func() {
    let a = parseFloat($('#a').val());
    let b = parseFloat($('#b').val());
    $('#sum').html( a + b );
}

////////////////////////////////////////////////////////////////
///  registration and resend pages

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
        .done(function(data) {
            console.log("done data=",data);
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
// Upload pages
// Enable the movie-file upload when we have at least 3 characters of title and description
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
                $('#message').html(`Movie ${body.movie_id} successfully uploaded. <a href='/list?api_key=${api_key}'>List movies</a>`);
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
// List movie page


////////////////
// PLAYBACK
// callback when the play button is clicked
function play_clicked( e ) {
    console.log('play_clicked=',e);
    const movie_id = e.getAttribute('x-movie_id');
    const rowid    = e.getAttribute('x-rowid');
    const url = `/api/get-movie?api_key=${api_key}&movie_id=${movie_id}`;
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
    formData.append("set_user_id", user_id);
    formData.append("set_movie_id", movie_id);
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
    //console.log("set_property done");
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
    t = document.getElementById(target);       // element of the target
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



// CREATE THE MOVIES tables
// Create the movies table
// top-level function is called to fill in all of the movies tables
// It's called with a list of movies
// https://developer.mozilla.org/en-US/docs/Web/HTML/Element/video
function list_movies_data( movies ) {
    // This fills in the given table with a given list
    let tid = 0;
    let rowid = 0;
    function movies_fill_div( div, mlist ) {
        let h = "<table>";
        h += "<tr> <th>id</th> <th>user</th>  <th>uploaded</th> <th>title</th> <th>description</th> <th>published</th> <th>deleted</th> </tr>";

        // This produces the HTML for each row of the table
        function movie_html( m ) {
            // This products the HTML for each <td> that has text
            rowid += 1;
            var movie_id = m.movie_id;
            function make_td_text(property, text) {
                // for debugging:
                // return `<td> ${text} </td>`;
                tid += 1;
                return `<td> <span id='${tid}' x-movie_id='${movie_id}' x-property='${property}'> ${text} </span>` +
                    `<span class='editor' x-target-id='${tid}' onclick='row_pencil_clicked(this)'> ✏️  </span> </td>\n`;
            }
            // This products the HTML for each <td> that has a checkbox
            function make_td_checkbox(property, value) {
                // for debugging:
                // return `<td> ${property} = ${value} </td>`;
                tid += 1;
                let ch = value > 0 ? 'checked' : '';
                return `<td> <input id='${tid}' x-movie_id='${movie_id}' x-property='${property}' ` +
                    `type='checkbox' ${ch} onclick='row_checkbox_clicked(this)'> </td>\n`;
            }
            //console.log("m=",m,'rowid=',rowid,'movie_id=',movie_id);
            var movieDate = new Date(m.date_uploaded * 1000); //
            //var download  = `<input class='download' x-movie_id='${movie_id}' type='button' value='download' onclick='download_clicked(this)'>`;
            var download = '';
            var play      = `<input class='play'     x-rowid='${rowid}' x-movie_id='${movie_id}' type='button' value='play' onclick='play_clicked(this)'>`;
            var up_down  = movieDate.toLocaleString().replace(' ','<br>').replace(',','') + download;

            return '<tr>'
                + `<td rowspan='2'> ${movie_id} </td> <td rowspan='2'> ${m.name} <br> ${play} </td> <td> ${up_down} </td>`
                + make_td_text(      "title", m.title) + make_td_text( "description", m.description)
                + make_td_checkbox(  "published", m.published) + make_td_checkbox( "deleted", m.deleted)
                + "</tr>\n"
                + `<tr    class='movie_player' id='tr-${rowid}'> `
                + `<td    class='movie_player' id='td-${rowid}' colspan='6' >`
                + `<video class='movie_player' id='video-${rowid}' controls playsinline></video>`
                + `<input class='hide' x-movie_id='${movie_id}' x-rowid='${rowid}' type='button' value='hide' onclick='hide_clicked(this)'></td>`
                + `</tr>\n`;
        }

        if (mlist.length>0){
            mlist.forEach( m => ( h += movie_html(m) ));
        } else {
            h += '<tr><td colspan="0"><i>No movies</i></td></tr>';
        }

        h += "</table>";
        div.html(h);
    }
    movies_fill_div( $('#your-published-movies'), movies.filter( m => (m['user_id']==user_id && m['published']==1)));
    movies_fill_div( $('#your-unpublished-movies'), movies.filter( m => (m['user_id']==user_id && m['published']==0 && m['deleted']==0)));
    movies_fill_div( $('#your-deleted-movies'), movies.filter( m => (m['user_id']==user_id && m['published']==0 && m['deleted']==1)));
    movies_fill_div( $('#course-movies'), movies.filter( m => (m['course_id']==user_primary_course_id)));
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
// Wire up whatever happens to be present
$( document ).ready( function() {
    $('#load_message').html('');       // remove the load message
    $('#adder_button').click( add_func );
    $('#register_button').click( register_func );
    $('#resend_button').click( resend_func );
});
