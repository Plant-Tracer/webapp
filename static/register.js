// https://stackoverflow.com/questions/5448545/how-to-retrieve-get-parameters-from-javascript

function register_func() {
    let email = $('#email').val();
    if (email=='') {
        $('#message').html("<b>Please provide an email address</b>");
        return;
    }
    let course_code = $('#course_code').val();
    if (course_code=='') {
        $('#message').html("<b>Please provide a course code</b>");
        return;
    }
    $('#message').html(`Asking to regsiter <b>${email}</b> for course <b>${course_code}<b>...</br>`);
    $.post('/api/register', {email:email, course_code:course_code}, function(data) {
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
