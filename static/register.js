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
    $.post('/api/resend', {email:email}, function(data) {
        alert(data);
    });
};

$( document ).ready( function() {
    $('#register_button').click( register_func );
    $('#resend_button').click( resend_func );
});
