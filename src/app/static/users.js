"use strict";
/* jshint esversion: 8 */
/* global user_primary_course_id */


////////////////////////////////////////////////////////////////
// page: /users

function bulk_register_users() {
    const email_addresses = $('#br_email_addresses').val();
    if (email_addresses.trim() == '') {
        $('#message').html("<b>Please provide a list of email addresses</b>");
        return;
    }
    let formData = new FormData();
    formData.append("api_key",  api_key); // on the upload form
    // ToDo: planttracers_endpoint value should be a parameter or something so we can unit test this function
    formData.append("planttracer_endpoint", window.origin + "");
    formData.append("course_id", user_primary_course_id);
    formData.append("email-addresses", email_addresses);
    console.log("before fetch");
    fetch(`${API_BASE}api/bulk-register`, { method: "POST", body: formData })
        .then((response) => response.json())
        .then((data) => {
            if (data.error != false){
                $('#message').html('error: '+ data.message);
                return;
            } else {
                $('#message').html(data.message);
            }
        }
    );
    console.log("after fetch");
    //TODO: seems to hang jest testing: window.location.reload();
    console.log("after reload");
}

function bulk_register_setup() {
    $('#register-emails-button').on('click', () => {bulk_register_users();});
}

// export {}
if (typeof module != 'undefined'){
    module.exports = { bulk_register_setup, bulk_register_users}
    }
