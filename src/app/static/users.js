"use strict";
/* jshint esversion: 8 */
import { $ } from "./utils.js";


////////////////////////////////////////////////////////////////
// page: /users

function bulk_register_users() {
    const raw_input = $('#br_email_addresses').val() || "";
    if (raw_input.trim() == '') {
        $('#message').html("<b>Please provide a list of email addresses</b>");
        return;
    }

    // Parse each line as "email" or "email, name"; split only on the first comma
    const emails = [];
    const names = [];
    for (const line of raw_input.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed) { continue; }
        const comma_idx = trimmed.indexOf(',');
        if (comma_idx === -1) {
            emails.push(trimmed);
            names.push('');
        } else {
            emails.push(trimmed.slice(0, comma_idx).trim());
            names.push(trimmed.slice(comma_idx + 1).trim());
        }
    }

    const payload = {
        "api_key": api_key,
        "planttracer_endpoint": window.origin + "",
        "course_id": user_primary_course_id,
        "email-addresses": emails.join('\n'),
        "names": names.join('\n')
    };

    $.post(`${API_BASE}api/bulk-register`, payload)
        .done((data) => {
            if (data.error !== false) {
                $('#message').html('error: ' + data.message);
            } else {
                $('#message').html(data.message);
                list_users();
            }
        })
        .fail((error) => {
            $('#message').html('error: ' + (error.responseText || 'Network error'));
            console.error("Bulk register error:", error);
        });

}

function bulk_register_setup() {
    $('#register-emails-button').on('click', () => { bulk_register_users(); });
}

window.bulk_register_setup = bulk_register_setup;

if (typeof module != 'undefined'){
    module.exports = { bulk_register_setup, bulk_register_users }
}
