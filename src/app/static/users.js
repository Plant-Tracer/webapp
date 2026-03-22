"use strict";
/* jshint esversion: 8 */
import { $ } from "./utils.js";


////////////////////////////////////////////////////////////////
// page: /users

function bulk_register_users() {
    const email_addresses = $('#br_email_addresses').val();
    if (email_addresses.trim() == '') {
        $('#message').html("<b>Please provide a list of email addresses</b>");
        return;
    }

    const payload = {
        "api_key": api_key, // on the upload form
        "planttracer_endpoint": window.origin + "", // ToDo: should be a parameter for unit testing
        "course_id": user_primary_course_id,
        "email-addresses": email_addresses
    };

    console.log("before fetch");

    $.post(`${API_BASE}api/bulk-register`, payload)
        .done((data) => {
            if (data.error !== false) {
                $('#message').html('error: ' + data.message);
            } else {
                $('#message').html(data.message);
                // Safe to reload here since the request is fully completed
                // window.location.reload();
            }
        })
        .fail((error) => {
            $('#message').html('error: ' + (error.responseText || 'Network error'));
            console.error("Bulk register error:", error);
        });

    console.log("after fetch initiated");
}

function bulk_register_setup() {
    $('#register-emails-button').on('click', () => { bulk_register_users(); });
}

if (typeof module != 'undefined'){
    module.exports = { bulk_register_setup, bulk_register_users }
}
