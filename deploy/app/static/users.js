"use strict";
/* jshint esversion: 8 */
/* global api_key, user_primary_course_id */
/* global API_BASE */
/* global console,alert */
/* global $ */

////////////////////////////////////////////////////////////////
// page: /users

function bulk_register_users() {
    let br_email_addresses = $("#br_email_addresses")
    let email_addresses = br_email_addresses.val();
    let formData = new FormData();
    formData.append("api_key",  api_key); // on the upload form
    formData.append("planttracer_endpoint", window.origin + "");
    formData.append("course_id", user_primary_course_id);
    formData.append("email-addresses", email_addresses);
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
    window.location.reload();
}

function bulk_register_setup(api_key) {
    let register_emails_button = $("#register-emails-button")
    register_emails_button.on('click', () => {bulk_register_users();});
}

//$( document ).ready( function() {
//    bulk_register_users();
//});

export {bulk_register_setup, bulk_register_users}