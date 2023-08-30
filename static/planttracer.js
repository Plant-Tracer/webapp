// Combined
// https://stackoverflow.com/questions/5448545/how-to-retrieve-get-parameters-from-javascript

function register_func() {
    let email = $('#email').val();
    if (email=='') {
        $('#message').html("<b>Please provide an email address</b>");
        return;
    }
    let course_key = $('#course_key').val();
    if (course_key=='') {
        $('#message').html("<b>Please provide a course key</b>");
        return;
    }
    $('#message').html(`Asking to register <b>${email}</b> for course key <b>${course_key}<b>...</br>`);
    $.post('/api/register', {email:email, course_key:course_key}, function(data) {
        alert(data);
    });
};

function resend_func() {
    let email = $('#email').val();
    if (email=='') {
        $('#message').html("<b>Please provide an email address</b>");
        return;
    }
    $('#message').html(`Asking to resend registration link for <b>${email}</b>...</br>`);
    $.post('/api/resend-link', {email:email})
        .done(function(data) {
            $('#message').html('Response: ' + data['message']);
        })
        .fail(function(xhr, status, error) {
            $('#message').html(`POST error: `+xhr['responseText']);
            console.log("xhr:",xhr);
        });
};

// https://stackoverflow.com/questions/5587973/javascript-upload-file
async function upload_movie(inp)
{
    $('#message').html(`Uploading image...`);
    console.log("upload_movie inp=",inp);
    let movieFile = inp.files[0];
    if (movieFile.fileSize > MAX_FILE_UPLOAD) {
        $('#message').html(`That file is too big to upload. Please chose a file smaller than ${MAX_FILE_UPLOAD} bytes.`);
        return;
    }
    console.log('movieFile:',movieFile);
    let formData = new FormData();
    formData.append("movie",    movieFile); // the movie itself
    formData.append("api_key",  api_key); // on the upload form
    formData.append("title",       $('#movie-title').val());
    formData.append("description", $('#movie-description').val());
    console.log('formData:',formData);

    const ctrl = new AbortController();    // timeout
    const timeoutId = setTimeout(() => ctrl.abort(), 5000);

    try {
        let r = await fetch('/api/new-movie',
                            { method:"POST", body:formData, signal: ctrl.signal });
        console.log("HTTP response code=",r);
        if (r.status!=200) {
            $('#message').html(`<i>Error uploading movie: ${r.status}</i>`);
        } else{
            const body = await r.text();
            $('#message').html(`Movie successfully uploaded: ${body}`);
            $('#movie-title').val('');
            $('#movie-description').val('');
            $('#movie-file').val('');
        }
    } catch(e) {
        console.log('Error uploading movie:',e);
        $('#message').html('Error uploading movie.');
    }
}

// For the demonstration page
function add_func() {
    let a = parseFloat($('#a').val());
    let b = parseFloat($('#b').val());
    $('#sum').html( a + b );
}

// List the movies
function list_movies() {
    console.log('list_movies');
    $('#message').html('Listing movies...');

    let formData = new FormData();
    formData.append("api_key",  api_key); // on the upload form
    fetch('/api/list-movies', { method:"POST", body:formData })
        .then((response) => response.json())
        .then((data) => {
            console.log("data:",data);
        })
        .catch(console.error)
    console.log('list_movies done');
}


// Wire up whatever happens to be present
$( document ).ready( function() {
    $('#adder_button').click( add_func );
    $('#register_button').click( register_func );
    $('#resend_button').click( resend_func );
});
